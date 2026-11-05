"""Base class for the entities of one room."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZoneCoordinator


class ZoneEntity(CoordinatorEntity[ZoneCoordinator]):
    """An entity attached to the room's device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZoneCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="what-the-heat",
            model="Zone controller",
            entry_type=DeviceEntryType.SERVICE,
        )
