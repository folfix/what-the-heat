"""A room as one thermostat entity, for dashboards: temperature, target and mode in one place."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MAX_TARGET, MIN_TARGET, TARGET_STEP
from .coordinator import ZoneCoordinator
from .core.runner import Mode
from .entity import ZoneEntity

ACTIONS = {"heating": HVACAction.HEATING, "idle": HVACAction.IDLE, "off": HVACAction.OFF}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the thermostat entity of a room."""
    async_add_entities([ZoneClimate(entry.runtime_data)])


class ZoneClimate(ZoneEntity, ClimateEntity):
    """Shows the real thermostat's readings, and changes the room's target and mode.

    The presets are the integration's modes. There is no off mode, because it would
    suggest that heating stops, while the real thermostat would carry on.
    """

    _attr_name = None
    _attr_hvac_mode = HVACMode.HEAT
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_max_temp = MAX_TARGET
    _attr_min_temp = MIN_TARGET
    _attr_preset_modes = [mode.value for mode in Mode]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    _attr_target_temperature_step = TARGET_STEP
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        super().__init__(coordinator, "zone")

    @property
    def current_temperature(self) -> float | None:
        """Return the room temperature."""
        return self.coordinator.data.reading.temperature

    @property
    def target_temperature(self) -> float:
        """Return the target."""
        return self.coordinator.runner.target

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return what the real thermostat is doing."""
        return ACTIONS.get(self.coordinator.data.reading.hvac_action)

    @property
    def preset_mode(self) -> str:
        """Return the integration's mode."""
        return self.coordinator.runner.mode.value

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Change the target."""
        await self.coordinator.async_set_target(kwargs[ATTR_TEMPERATURE])

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Change the integration's mode."""
        await self.coordinator.async_set_mode(Mode(preset_mode))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Do nothing, since heat is the only mode."""
