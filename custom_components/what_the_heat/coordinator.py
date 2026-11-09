"""Connects a zone runner to Home Assistant: reads states, runs the step, carries out commands."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_STEP,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import PowerConverter

from .const import (
    CONF_PHASE_OFFSET,
    CONF_TARGET,
    CONF_THERMOSTAT,
    DEFAULT_PHASE_OFFSET,
    DEFAULT_TARGET,
    DOMAIN,
    LEGACY_SETTINGS,
    MAX_LOG_STEP_S,
    SAVE_INTERVAL_S,
    STORAGE_VERSION,
    UPDATE_INTERVAL_S,
)
from .core.daily import DailyLog
from .core.sun import solar_time
from .core.runner import (
    Command,
    CommandKind,
    LearnedState,
    Mode,
    Problem,
    RunnerConfig,
    RunnerStep,
    ThermostatReading,
    ZoneRunner,
)
from .core.zone import ZoneConfig
from .settings import GlobalSettings

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

LOGGER = logging.getLogger(__package__)

PROBLEM_TEXT = {
    Problem.THERMOSTAT_NOT_FOLLOWING: "The thermostat is not following commands.",
    Problem.THERMOSTAT_CANNOT_HEAT: "The thermostat cannot heat. Check its summer mode.",
    Problem.READINGS_MISSING: "Room temperature readings are missing.",
}


@dataclass(frozen=True)
class ZoneData:
    """The latest state of a room, for the entities."""

    step: RunnerStep
    reading: ThermostatReading
    water: float
    outdoor: float | None
    sun: float | None
    today: dict[str, Any] | None
    learned: LearnedState
    colder_than_usual: float | None


def merged_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return the entry's settings, with options replacing the initial values.

    Settings from older versions are left out.
    """
    config = {**entry.data, **entry.options}
    for key in LEGACY_SETTINGS:
        config.pop(key, None)
    return config


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _is_available(state: State | None) -> bool:
    return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


def read_thermostat(state: State | None) -> ThermostatReading:
    """Translate a climate entity's state. Everything is empty while it is unavailable."""
    if not _is_available(state):
        return ThermostatReading()
    attributes = state.attributes
    action = attributes.get(ATTR_HVAC_ACTION)
    return ThermostatReading(
        temperature=_number(attributes.get(ATTR_CURRENT_TEMPERATURE)),
        setpoint=_number(attributes.get(ATTR_TEMPERATURE)),
        hvac_mode=state.state,
        hvac_action=None if action is None else str(action),
        hvac_modes=tuple(str(mode) for mode in attributes.get(ATTR_HVAC_MODES) or ()),
        min_temp=_number(attributes.get(ATTR_MIN_TEMP)),
        max_temp=_number(attributes.get(ATTR_MAX_TEMP)),
        setpoint_step=_number(attributes.get(ATTR_TARGET_TEMP_STEP)),
    )


class ZoneCoordinator(DataUpdateCoordinator[ZoneData]):
    """Runs one room every minute. Failures are logged and retried, never raised."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, settings: GlobalSettings) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_S),
        )
        self._config = merged_config(entry)
        self._global = settings
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._thermostat: str = self._config[CONF_THERMOSTAT]
        self.runner: ZoneRunner
        self.log: DailyLog
        self._last_step_s: float | None = None
        self._last_save_s = dt_util.utcnow().timestamp()
        self._notified: frozenset[Problem] = frozenset()

    async def async_load(self) -> None:
        """Restore the state saved before a restart."""
        stored = await self._store.async_load() or {}
        state = stored.get("runner", {})
        now_s = dt_util.utcnow().timestamp()
        target = state.get("target", self._config.get(CONF_TARGET, DEFAULT_TARGET))
        phase_minutes = self._config.get(CONF_PHASE_OFFSET, DEFAULT_PHASE_OFFSET)
        self.runner = ZoneRunner(
            RunnerConfig(zone=ZoneConfig(target=target, phase_offset_s=phase_minutes * 60.0)),
            Mode(state.get("mode", Mode.ACTIVE.value)),
            integral=state.get("integral", 0.0),
            carry_s=state.get("carry_s", 0.0),
            start_s=now_s,
            heating_share=state.get("heating_share"),
            observed_s=state.get("observed_s", 0.0),
            writes=state.get("writes", 0),
            learned_s=state.get("learned_s", 0.0),
            solar=state.get("solar"),
            outdoor=state.get("outdoor"),
        )
        self.log = DailyLog(**stored.get("log", {}))

    def snapshot(self) -> dict[str, Any]:
        """Return everything worth keeping across a restart."""
        return {"runner": self.runner.snapshot(), "log": self.log.snapshot()}

    async def _async_update_data(self) -> ZoneData:
        now_s = dt_util.utcnow().timestamp()
        reading = read_thermostat(self.hass.states.get(self._thermostat))
        water = self._global.water_temperature
        outdoor = self._read_number(self._global.outdoor_entity)
        pv_w = self._read_power(self._global.pv_entity)
        sun = self._global.sun_share(pv_w, now_s)
        # The sun is learned by solar time, which does not jump when the clocks change.
        solar_date, solar_hour = solar_time(now_s, self.hass.config.longitude)
        step = self.runner.step(now_s, reading, water, sun, solar_date, solar_hour, outdoor)
        decision = step.decision
        LOGGER.debug(
            "%s: mode=%s status=%s room=%s filtered=%s setpoint=%s hvac=%s/%s water=%s sun=%s outdoor=%s "
            "duty=%.1f sun_correction=%.1f outdoor_correction=%.1f integral=%.1f valve_open=%s requested=%s commands=%d",
            self._thermostat,
            step.mode.value,
            decision.status.value,
            reading.temperature,
            decision.temperature,
            reading.setpoint,
            reading.hvac_mode,
            reading.hvac_action,
            water,
            sun,
            outdoor,
            decision.duty,
            decision.sun,
            decision.outdoor,
            decision.integral,
            decision.valve_open,
            decision.setpoint,
            len(step.commands),
        )
        for command in step.commands:
            await self._async_execute(command)
        dt_s = 0.0 if self._last_step_s is None else min(now_s - self._last_step_s, MAX_LOG_STEP_S)
        self._last_step_s = now_s
        self.log.add(
            dt_util.now().date().isoformat(),
            dt_s,
            target=self.runner.target,
            temperature=reading.temperature,
            is_heating=reading.is_heating,
            is_active=step.mode is Mode.ACTIVE,
            outdoor=outdoor,
            water=water,
            writes=step.new_writes,
            pv_w=pv_w,
            sun_correction=None if sun is None else decision.sun,
            outdoor_correction=None if outdoor is None else decision.outdoor,
        )
        self._update_notification(step.problems)
        # A delayed save restarts its timer on each call, so it is only called when due.
        if now_s - self._last_save_s >= SAVE_INTERVAL_S:
            self._last_save_s = now_s
            self._store.async_delay_save(self.snapshot, 1)
        return ZoneData(
            step, reading, water, outdoor, sun, self.log.today, self.runner.learned(), self.runner.colder_than_usual
        )

    def _available_state(self, entity_id: str | None) -> State | None:
        state = self.hass.states.get(entity_id) if entity_id else None
        return state if _is_available(state) else None

    def _read_number(self, entity_id: str | None) -> float | None:
        state = self._available_state(entity_id)
        return None if state is None else _number(state.state)

    def _read_power(self, entity_id: str | None) -> float | None:
        """Return the power in watts, whatever unit the sensor reports it in."""
        state = self._available_state(entity_id)
        value = None if state is None else _number(state.state)
        unit = None if state is None else state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if value is None or unit in (None, UnitOfPower.WATT):
            return value
        try:
            return PowerConverter.convert(value, unit, UnitOfPower.WATT)
        except HomeAssistantError:
            return None

    async def _async_execute(self, command: Command) -> None:
        if command.kind is CommandKind.SET_TEMPERATURE:
            service = SERVICE_SET_TEMPERATURE
            data = {ATTR_TEMPERATURE: command.temperature}
        else:
            service = SERVICE_SET_HVAC_MODE
            data = {ATTR_HVAC_MODE: "heat"}
        LOGGER.info("%s: %s %s", self._thermostat, service, data)
        try:
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                service,
                {ATTR_ENTITY_ID: self._thermostat, **data},
                blocking=True,
            )
        except (HomeAssistantError, ValueError, vol.Invalid) as err:
            # The watchdog sees that the thermostat did not change, and sends it again.
            LOGGER.warning("Command to %s failed: %s", self._thermostat, err)

    def _update_notification(self, problems: frozenset[Problem]) -> None:
        if problems == self._notified:
            return
        self._notified = problems
        notification_id = f"{DOMAIN}_{self.config_entry.entry_id}"
        if not problems:
            LOGGER.info("%s: no more problems", self._thermostat)
            persistent_notification.async_dismiss(self.hass, notification_id)
            return
        LOGGER.warning("%s: problems: %s", self._thermostat, sorted(problem.value for problem in problems))
        persistent_notification.async_create(
            self.hass,
            "\n".join(PROBLEM_TEXT[problem] for problem in sorted(problems, key=lambda item: item.value)),
            title=f"What the Heat: {self.config_entry.title}",
            notification_id=notification_id,
        )

    async def async_set_mode(self, mode: Mode) -> None:
        """Change who is in charge of the thermostat, and act on it right away."""
        LOGGER.info("%s: mode %s -> %s", self._thermostat, self.runner.mode.value, mode.value)
        if self.runner.mode is Mode.ACTIVE and mode is Mode.OBSERVE:
            # Observe mode writes nothing, so the thermostat would stay on its band setpoint.
            await self._async_execute(Command(CommandKind.SET_TEMPERATURE, self.runner.target))
        self.runner.set_mode(mode)
        await self._async_apply_change()

    async def async_set_target(self, target: float) -> None:
        """Change the target temperature, and act on it right away."""
        LOGGER.info("%s: target %s -> %s", self._thermostat, self.runner.target, target)
        self.runner.target = target
        await self._async_apply_change()

    async def async_reset_learning(self) -> None:
        """Forget what the room has learned, and act on it right away."""
        LOGGER.info("%s: learning reset", self._thermostat)
        self.runner.reset_learning()
        await self._async_apply_change()

    async def _async_apply_change(self) -> None:
        await self.async_refresh()
        await self._store.async_save(self.snapshot())

    async def async_release(self) -> None:
        """Stop controlling the thermostat, leaving it with the plain target."""
        if self.runner.mode is Mode.ACTIVE:
            await self._async_execute(Command(CommandKind.SET_TEMPERATURE, self.runner.target))
        await self._store.async_save(self.snapshot())
        persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{self.config_entry.entry_id}")
