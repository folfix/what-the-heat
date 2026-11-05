"""The target temperature of a room."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MAX_TARGET, MIN_TARGET, TARGET_STEP
from .coordinator import ZoneCoordinator
from .entity import ZoneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the target of a room."""
    async_add_entities([TargetNumber(entry.runtime_data)])


class TargetNumber(ZoneEntity, NumberEntity):
    """The temperature the room should have."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_TARGET
    _attr_native_max_value = MAX_TARGET
    _attr_native_step = TARGET_STEP
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        super().__init__(coordinator, "target")

    @property
    def native_value(self) -> float:
        """Return the target."""
        return self.coordinator.runner.target

    async def async_set_native_value(self, value: float) -> None:
        """Change the target."""
        await self.coordinator.async_set_target(value)
