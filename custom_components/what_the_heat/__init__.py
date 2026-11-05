"""what-the-heat: underfloor heating control for Home Assistant.

Each configuration entry is one room. This module must stay free of top-level Home
Assistant imports, because importing the control core runs it, and the core and the
simulator work without Home Assistant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DOMAIN, PLATFORMS

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one room."""
    from .coordinator import ZoneCoordinator  # noqa: PLC0415
    from .panel import async_add_panel  # noqa: PLC0415

    coordinator = ZoneCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_add_panel(hass)
    entry.async_on_unload(entry.add_update_listener(_async_options_changed))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one room and give the plain target back to its thermostat."""
    from .panel import remove_panel_if_unused  # noqa: PLC0415

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_release()
        remove_panel_if_unused(hass, entry)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete what was stored for a room."""
    from homeassistant.helpers.storage import Store  # noqa: PLC0415

    from .const import STORAGE_VERSION  # noqa: PLC0415

    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_options_changed(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
