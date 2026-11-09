"""Decides what to do with a thermostat, given the zone mode and what the device reports.

This is everything between Home Assistant and the controller that needs no Home Assistant
imports, so that the simulator exercises the same code that runs in a real installation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .smoothing import ExponentialFilter
from .sun import SolarConfig, SolarProfile
from .valve import ValveWatchdog, WatchdogConfig, WatchdogResult
from .zone import ZoneConfig, ZoneController, ZoneDecision, ZoneStatus


class Mode(Enum):
    """Who is in charge of the thermostat."""

    OBSERVE = "observe"  # calculate and log only, never write to the device
    ACTIVE = "active"  # control the thermostat through its setpoint
    HANDBACK = "handback"  # give the plain target to the thermostat and leave it alone


class Problem(Enum):
    """Conditions that need the owner's attention."""

    THERMOSTAT_NOT_FOLLOWING = "thermostat_not_following"
    THERMOSTAT_CANNOT_HEAT = "thermostat_cannot_heat"
    READINGS_MISSING = "readings_missing"


class CommandKind(Enum):
    """Actions on the thermostat."""

    SET_TEMPERATURE = "set_temperature"
    SET_HEAT_MODE = "set_heat_mode"


@dataclass(frozen=True)
class Command:
    """One action for the Home Assistant layer to carry out."""

    kind: CommandKind
    temperature: float | None = None


@dataclass(frozen=True)
class ThermostatReading:
    """What the thermostat reports. Everything is None while it is unavailable."""

    temperature: float | None = None
    setpoint: float | None = None
    hvac_mode: str | None = None
    hvac_action: str | None = None
    hvac_modes: tuple[str, ...] = ()
    min_temp: float | None = None
    max_temp: float | None = None
    setpoint_step: float | None = None

    @property
    def is_heating(self) -> bool | None:
        """Return whether the relay is on, or None if unknown."""
        return None if self.hvac_action is None else self.hvac_action == "heating"


@dataclass(frozen=True)
class RunnerConfig:
    """Settings around the zone controller."""

    zone: ZoneConfig = field(default_factory=ZoneConfig)
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)
    sun: SolarConfig = field(default_factory=SolarConfig)
    heat_mode_retry_s: float = 5 * 60.0
    heat_mode_attempts: int = 3
    heating_share_time_constant_s: float = 24 * 3600.0
    min_learning_s: float = 6 * 3600.0
    seed_max_error: float = 0.5


@dataclass(frozen=True)
class LearnedState:
    """What a room has learned so far, for showing to the owner.

    `demand` is the share of time, in percent, that the valve must be open to hold the
    target at the current water temperature, or None without enough data. `source` says
    where it comes from: "controller" while it is in charge, otherwise "thermostat", from
    what the thermostat has been doing on its own. `hours` is how much data is behind it,
    and `recent_heating` the percentage of about the last day that the relay was on.
    `sun_profile` holds, for each hour, how much less heat the room needs at full sun,
    learned from `sunny_days` days. It acts once `sun_active` is set.
    """

    demand: float | None
    source: str
    hours: float
    recent_heating: float | None
    sunny_days: int
    sun_active: bool
    sun_profile: tuple[float, ...]


@dataclass(frozen=True)
class RunnerStep:
    """Result of one step."""

    mode: Mode
    decision: ZoneDecision
    commands: tuple[Command, ...]
    problems: frozenset[Problem]
    writes: int
    resends: int
    new_writes: int


class ZoneRunner:
    """Connects the zone controller, the watchdog and the mode.

    In observe mode nothing is ever written. On switching to active mode, the integral
    starts from how much the thermostat has recently been heating, but only if the room
    is near its target. A room that is cold or was just warming up says nothing about its
    steady demand, so it starts from zero.

    With a share of full sun from PV, the room learns what the sun does to it while in
    active mode, and once it has learned enough, opens the valve less while the sun shines.
    """

    def __init__(
        self,
        config: RunnerConfig | None = None,
        mode: Mode = Mode.OBSERVE,
        integral: float = 0.0,
        carry_s: float = 0.0,
        start_s: float = 0.0,
        heating_share: float | None = None,
        observed_s: float = 0.0,
        writes: int = 0,
        learned_s: float = 0.0,
        solar: dict | None = None,
    ) -> None:
        self._config = config or RunnerConfig()
        self._mode = mode
        self._controller = ZoneController(self._config.zone, integral, carry_s, start_s)
        self._watchdog = ValveWatchdog(self._config.watchdog)
        self._heating_share = ExponentialFilter(self._config.heating_share_time_constant_s)
        if heating_share is not None:
            self._heating_share.update(heating_share, 0.0)
        self._solar = SolarProfile(self._config.sun, **(solar or {}))
        self._observed_s = observed_s
        self._learned_s = learned_s
        self._writes = writes
        self._resends = 0
        self._last_step_s: float | None = None
        self._last_temperature: float | None = None
        self._last_water: float | None = None
        self._next_heat_mode_s = 0.0
        self._heat_mode_tries = 0

    @property
    def mode(self) -> Mode:
        """Return the current mode."""
        return self._mode

    @property
    def target(self) -> float:
        """Return the target temperature."""
        return self._controller.target

    @target.setter
    def target(self, value: float) -> None:
        self._controller.target = value

    @property
    def commanded(self) -> float | None:
        """Return the setpoint most recently commanded."""
        return self._watchdog.commanded

    def set_mode(self, mode: Mode) -> None:
        """Change who is in charge of the thermostat."""
        if mode is self._mode:
            return
        if mode is Mode.ACTIVE:
            seed = self._observed_integral()
            self._controller.integral = 0.0 if seed is None else seed
            self._learned_s = 0.0 if seed is None else self._observed_s
        self._mode = mode
        self._watchdog = ValveWatchdog(self._config.watchdog)
        self._heat_mode_tries = 0
        self._next_heat_mode_s = 0.0

    def reset_learning(self) -> None:
        """Forget what was learned about the room. The mode, target and counters stay."""
        self._controller.reset_learning()
        self._solar.reset()
        self._heating_share.reset()
        self._observed_s = 0.0
        self._learned_s = 0.0

    def learned(self) -> LearnedState:
        """Return what the room has learned so far."""
        config = self._config
        share = self._heating_share.value
        recent = share * 100.0 if share is not None and self._observed_s >= config.min_learning_s else None
        if self._mode is Mode.ACTIVE:
            integral, source, seconds = self._controller.integral, "controller", self._learned_s
        else:
            integral, source, seconds = self._observed_integral(), "thermostat", self._observed_s
        demand = None
        if integral is not None and seconds >= config.min_learning_s:
            scale = self._controller.gain_scale(self._controller.target, self._last_water)
            demand = min(100.0, integral * scale)
        solar = self._solar
        return LearnedState(
            demand,
            source,
            seconds / 3600.0,
            recent,
            solar.sunny_days,
            solar.active,
            solar.values,
        )

    def snapshot(self) -> dict:
        """Return the state worth keeping across a restart."""
        return {
            "mode": self._mode.value,
            "target": self._controller.target,
            "heating_share": self._heating_share.value,
            "observed_s": self._observed_s,
            "learned_s": self._learned_s,
            "writes": self._writes,
            "solar": self._solar.snapshot(),
            **self._controller.snapshot(),
        }

    def step(
        self,
        now_s: float,
        reading: ThermostatReading,
        water_temperature: float | None = None,
        sun: float | None = None,
        date: str | None = None,
        hour: int | None = None,
    ) -> RunnerStep:
        """Advance by one step and return what should be done.

        `sun` is the share of full sun from PV, and `date` and `hour` the local date and
        hour of the day, which the room needs to learn what the sun does at each hour.
        """
        dt_s = 0.0 if self._last_step_s is None else now_s - self._last_step_s
        self._last_step_s = now_s
        writes_before = self._writes
        feedforward = 0.0 if hour is None else self._solar.feedforward(hour, sun)
        self._controller.set_device_limits(reading.min_temp, reading.max_temp, reading.setpoint_step)
        decision = self._controller.step(now_s, reading.temperature, water_temperature, feedforward)
        self._track_heating(reading, water_temperature, dt_s)
        step_s = min(dt_s, self._config.zone.max_integration_step_s)
        if self._mode is Mode.ACTIVE and decision.learning:
            self._learned_s += step_s
        if self._mode is Mode.ACTIVE and date is not None and hour is not None:
            deviation = None if reading.temperature is None or decision.temperature is None else decision.temperature - self.target
            self._solar.add(date, hour, step_s, sun, deviation)

        problems: set[Problem] = set()
        if decision.status in (ZoneStatus.DEGRADED, ZoneStatus.HANDBACK):
            problems.add(Problem.READINGS_MISSING)
        commands: list[Command] = []
        if self._mode is not Mode.OBSERVE and reading.hvac_mode is not None:
            self._drive_thermostat(now_s, reading, decision, commands, problems)
        return RunnerStep(
            self._mode,
            decision,
            tuple(commands),
            frozenset(problems),
            self._writes,
            self._resends,
            self._writes - writes_before,
        )

    def _track_heating(self, reading: ThermostatReading, water_temperature: float | None, dt_s: float) -> None:
        is_heating = reading.is_heating
        if is_heating is not None:
            self._heating_share.update(1.0 if is_heating else 0.0, dt_s)
            self._observed_s += dt_s
        if reading.temperature is not None:
            self._last_temperature = reading.temperature
        if water_temperature is not None:
            self._last_water = water_temperature

    def _observed_integral(self) -> float | None:
        """Return the integral matching what the thermostat has been doing, if that says anything."""
        config = self._config
        share = self._heating_share.value
        temperature = self._last_temperature
        if share is None or temperature is None or self._observed_s < config.min_learning_s:
            return None
        if abs(self._controller.target - temperature) > config.seed_max_error:
            return None
        return share * 100.0 / self._controller.gain_scale(temperature, self._last_water)

    def _drive_thermostat(
        self,
        now_s: float,
        reading: ThermostatReading,
        decision: ZoneDecision,
        commands: list[Command],
        problems: set[Problem],
    ) -> None:
        if self._mode is Mode.ACTIVE and not self._ensure_heat_mode(now_s, reading, commands, problems):
            return
        desired = self._desired_setpoint(decision)
        if desired is None:
            return
        if desired != self._watchdog.commanded:
            if reading.setpoint != desired:
                self._send(commands, desired)
            self._watchdog.command(now_s, desired)
        else:
            verdict = self._watchdog.check(now_s, reading.setpoint, reading.is_heating, reading.temperature)
            if verdict is not WatchdogResult.OK:
                self._resends += 1
                self._send(commands, desired)
                self._watchdog.command(now_s, desired)
        if self._watchdog.mismatches >= self._config.watchdog.alert_after:
            problems.add(Problem.THERMOSTAT_NOT_FOLLOWING)

    def _ensure_heat_mode(
        self,
        now_s: float,
        reading: ThermostatReading,
        commands: list[Command],
        problems: set[Problem],
    ) -> bool:
        """Keep the thermostat switched on and heating. Return False if it cannot heat."""
        if reading.hvac_modes and "heat" not in reading.hvac_modes:
            problems.add(Problem.THERMOSTAT_CANNOT_HEAT)
            return False
        if reading.hvac_mode == "heat":
            self._heat_mode_tries = 0
            return True
        if now_s >= self._next_heat_mode_s:
            commands.append(Command(CommandKind.SET_HEAT_MODE))
            self._heat_mode_tries += 1
            self._next_heat_mode_s = now_s + self._config.heat_mode_retry_s
        if self._heat_mode_tries >= self._config.heat_mode_attempts:
            problems.add(Problem.THERMOSTAT_NOT_FOLLOWING)
        return True

    def _desired_setpoint(self, decision: ZoneDecision) -> float | None:
        if self._mode is Mode.HANDBACK or decision.status is ZoneStatus.HANDBACK:
            return self._controller.target
        if decision.status is ZoneStatus.INITIALIZING:
            return None
        return decision.setpoint

    def _send(self, commands: list[Command], setpoint: float) -> None:
        commands.append(Command(CommandKind.SET_TEMPERATURE, setpoint))
        self._writes += 1
