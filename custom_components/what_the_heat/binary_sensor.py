"""Binary sensors for a room: what the controller asks of the valve, and whether anything is wrong."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ZoneCoordinator
from .entity import ZoneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the binary sensors of a room."""
    coordinator: ZoneCoordinator = entry.runtime_data
    async_add_entities([ValveRequestedSensor(coordinator), ProblemSensor(coordinator)])


class ValveRequestedSensor(ZoneEntity, BinarySensorEntity):
    """On when the controller wants the valve open. In observe mode nothing acts on it."""

    _attr_device_class = BinarySensorDeviceClass.OPENING

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        super().__init__(coordinator, "valve_requested")

    @property
    def is_on(self) -> bool:
        """Return whether the valve should be open."""
        return self.coordinator.data.step.decision.valve_open


class ProblemSensor(ZoneEntity, BinarySensorEntity):
    """On when something needs attention. The attribute lists what."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        super().__init__(coordinator, "problem")

    @property
    def is_on(self) -> bool:
        """Return whether there is a problem."""
        return bool(self.coordinator.data.step.problems)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the current problems."""
        return {"reasons": sorted(problem.value for problem in self.coordinator.data.step.problems)}
