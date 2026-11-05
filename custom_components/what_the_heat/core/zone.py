"""Controller for one room: from a temperature reading to a thermostat setpoint."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .cycle import CycleConfig, CycleScheduler
from .pid import PidConfig, PidController
from .smoothing import ExponentialFilter
from .valve import ValveConfig, closed_setpoint, open_setpoint


class ZoneStatus(Enum):
    """Operating state of a zone."""

    INITIALIZING = "initializing"
    NORMAL = "normal"
    DEGRADED = "degraded"
    HANDBACK = "handback"


@dataclass(frozen=True)
class ZoneConfig:
    """Settings for one zone."""

    target: float = 21.0
    smoothing_s: float = 10 * 60.0
    stale_degraded_s: float = 30 * 60.0
    stale_handback_s: float = 60 * 60.0
    max_integration_step_s: float = 5 * 60.0
    reference_water_delta: float = 10.0
    floor_offset: float = 3.0
    min_water_delta: float = 3.0
    phase_offset_s: float = 0.0
    pid: PidConfig = field(default_factory=PidConfig)
    cycle: CycleConfig = field(default_factory=CycleConfig)
    valve: ValveConfig = field(default_factory=ValveConfig)


@dataclass(frozen=True)
class ZoneDecision:
    """What the zone wants at this moment."""

    status: ZoneStatus
    setpoint: float
    valve_open: bool
    duty: float
    temperature: float | None
    integral: float


class ZoneController:
    """Runs smoothing, PI control and cycle scheduling for one room.

    The buffer temperature, normally the heat pump setpoint, scales the output so that
    the same power demand gives a shorter open time when the water is hotter. Without it
    the output is used directly as duty. When readings stop, the last duty is held, and
    later the plain target goes back to the thermostat, which then regulates on its own.
    """

    def __init__(
        self,
        config: ZoneConfig | None = None,
        integral: float = 0.0,
        carry_s: float = 0.0,
        start_s: float = 0.0,
    ) -> None:
        self._config = config or ZoneConfig()
        self._target = self._config.target
        self._filter = ExponentialFilter(self._config.smoothing_s)
        self._pid = PidController(self._config.pid, integral)
        self._cycle = CycleScheduler(self._config.cycle, start_s + self._config.phase_offset_s, carry_s)
        self._last_step_s: float | None = None
        self._last_reading_s: float | None = None
        self._duty = 0.0

    @property
    def target(self) -> float:
        """Return the target temperature."""
        return self._target

    @target.setter
    def target(self, value: float) -> None:
        self._target = value

    def snapshot(self) -> dict[str, float]:
        """Return the state worth keeping across a restart."""
        return {"integral": self._pid.integral, "carry_s": self._cycle.carry_s}

    def step(
        self,
        now_s: float,
        room_temperature: float | None,
        buffer_temperature: float | None = None,
        feedforward: float = 0.0,
    ) -> ZoneDecision:
        """Advance the controller and return its decision."""
        config = self._config
        dt_s = 0.0 if self._last_step_s is None else now_s - self._last_step_s
        self._last_step_s = now_s
        if room_temperature is None:
            return self._without_reading(now_s)
        self._last_reading_s = now_s
        temperature = self._filter.update(room_temperature, dt_s)
        error = self._target - temperature
        # Outside the setpoint band the thermostat acts on its own, so the controller's
        # output has no effect and must not build up in the integral.
        in_control = abs(error) <= config.valve.authority
        output = self._pid.update(
            error,
            min(dt_s, config.max_integration_step_s) if in_control else 0.0,
            feedforward,
            self._gain_scale(temperature, buffer_temperature),
        )
        self._duty = output.duty
        return self._drive(now_s, ZoneStatus.NORMAL)

    def _gain_scale(self, temperature: float, buffer_temperature: float | None) -> float:
        config = self._config
        if buffer_temperature is None:
            return 1.0
        delta = buffer_temperature - temperature - config.floor_offset
        return config.reference_water_delta / max(config.min_water_delta, delta)

    def _without_reading(self, now_s: float) -> ZoneDecision:
        config = self._config
        if self._last_reading_s is None:
            return self._handback(ZoneStatus.INITIALIZING)
        age_s = now_s - self._last_reading_s
        if age_s >= config.stale_handback_s:
            return self._handback(ZoneStatus.HANDBACK)
        status = ZoneStatus.DEGRADED if age_s >= config.stale_degraded_s else ZoneStatus.NORMAL
        return self._drive(now_s, status)

    def _drive(self, now_s: float, status: ZoneStatus) -> ZoneDecision:
        is_open = self._cycle.step(now_s, self._duty)
        valve = self._config.valve
        setpoint = open_setpoint(self._target, valve) if is_open else closed_setpoint(self._target, valve)
        return ZoneDecision(status, setpoint, is_open, self._duty, self._filter.value, self._pid.integral)

    def _handback(self, status: ZoneStatus) -> ZoneDecision:
        return ZoneDecision(status, self._target, False, self._duty, self._filter.value, self._pid.integral)
