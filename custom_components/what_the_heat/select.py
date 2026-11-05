"""Selects who is in charge of a room's thermostat."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ZoneCoordinator
from .core.runner import Mode
from .entity import ZoneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the mode selector of a room."""
    async_add_entities([ModeSelect(entry.runtime_data)])


class ModeSelect(ZoneEntity, SelectEntity):
    """Observe, active or handback."""

    _attr_options = [mode.value for mode in Mode]

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        super().__init__(coordinator, "mode")

    @property
    def current_option(self) -> str:
        """Return the current mode."""
        return self.coordinator.runner.mode.value

    async def async_select_option(self, option: str) -> None:
        """Change the mode."""
        await self.coordinator.async_set_mode(Mode(option))
