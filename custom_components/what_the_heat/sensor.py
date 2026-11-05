"""Sensors showing what a room's controller is doing, and how well it works."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ZoneCoordinator, ZoneData
from .core.zone import ZoneStatus
from .entity import ZoneEntity


def _today(key: str) -> Callable[[ZoneData], Any]:
    return lambda data: data.today.get(key) if data.today else None


@dataclass(frozen=True, kw_only=True)
class ZoneSensorDescription(SensorEntityDescription):
    """A sensor and how to get its value."""

    value: Callable[[ZoneData], Any]
    attributes: Callable[[ZoneData], dict[str, Any]] | None = None


def _learned_attributes(data: ZoneData) -> dict[str, Any]:
    learned = data.learned
    recent = learned.recent_heating
    return {
        "source": learned.source,
        "learned_from_hours": round(learned.hours, 1),
        "recent_heating_pct": None if recent is None else round(recent, 1),
    }


SENSORS = (
    ZoneSensorDescription(
        key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in ZoneStatus],
        value=lambda data: data.step.decision.status.value,
    ),
    ZoneSensorDescription(
        key="duty",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=lambda data: data.step.decision.duty,
    ),
    ZoneSensorDescription(
        key="requested_setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.step.decision.setpoint,
    ),
    ZoneSensorDescription(
        key="filtered_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda data: data.step.decision.temperature,
    ),
    ZoneSensorDescription(
        key="time_in_band_today",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=_today("time_in_band_pct"),
    ),
    ZoneSensorDescription(
        key="rms_deviation_today",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=_today("rms_deviation"),
    ),
    ZoneSensorDescription(
        key="heating_today",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=_today("heating_pct"),
    ),
    ZoneSensorDescription(
        key="longest_closed_today",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        value=_today("longest_closed_h"),
    ),
    ZoneSensorDescription(
        key="learned_demand",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=lambda data: data.learned.demand,
        attributes=_learned_attributes,
    ),
    ZoneSensorDescription(
        key="integral",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value=lambda data: data.step.decision.integral,
    ),
    ZoneSensorDescription(
        key="water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.water,
    ),
    ZoneSensorDescription(
        key="setpoint_writes",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value=lambda data: data.step.writes,
    ),
    ZoneSensorDescription(
        key="resends",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value=lambda data: data.step.resends,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the sensors of a room, and remove one that older versions had."""
    registry = er.async_get(hass)
    old = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_assumed_buffer_temperature")
    if old is not None:
        registry.async_remove(old)
    async_add_entities(ZoneSensor(entry.runtime_data, description) for description in SENSORS)


class ZoneSensor(ZoneEntity, SensorEntity):
    """A value read from the room's latest state."""

    entity_description: ZoneSensorDescription

    def __init__(self, coordinator: ZoneCoordinator, description: ZoneSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the current value."""
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the details behind the value, if there are any."""
        attributes = self.entity_description.attributes
        return None if attributes is None else attributes(self.coordinator.data)
