"""Forgets what a room has learned, for example after something unusual has misled it."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ZoneCoordinator
from .entity import ZoneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the reset button of a room."""
    async_add_entities([ResetLearningButton(entry.runtime_data)])


class ResetLearningButton(ZoneEntity, ButtonEntity):
    """Clears what was learned. The daily measurements, the mode and the target stay."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        super().__init__(coordinator, "reset_learning")

    async def async_press(self) -> None:
        """Forget what the room has learned."""
        await self.coordinator.async_reset_learning()
