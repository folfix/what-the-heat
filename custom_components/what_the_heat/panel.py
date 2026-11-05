"""Adds a sidebar entry with an overview of all rooms."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import async_register_built_in_panel, async_remove_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

PANEL_URL_PATH = "what-the-heat"
PANEL_ELEMENT = "what-the-heat-panel"
STATIC_URL = f"/{DOMAIN}/panel.js"
_REGISTERED = f"{DOMAIN}_panel_registered"
_STATIC_DONE = f"{DOMAIN}_panel_static_done"


async def async_add_panel(hass: HomeAssistant) -> None:
    """Add the sidebar entry, once for all rooms."""
    if hass.http is None or hass.data.get(_REGISTERED):
        return
    if not hass.data.get(_STATIC_DONE):
        # A static path cannot be removed again, so it stays across reloads.
        path = Path(__file__).parent / "frontend" / "panel.js"
        await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, str(path), False)])
        hass.data[_STATIC_DONE] = True
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="What the Heat",
        sidebar_icon="mdi:heating-coil",
        frontend_url_path=PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": PANEL_ELEMENT,
                "embed_iframe": False,
                "trust_external": False,
                "js_url": f"{STATIC_URL}?v={VERSION}",
            }
        },
    )
    hass.data[_REGISTERED] = True


def remove_panel_if_unused(hass: HomeAssistant, leaving: ConfigEntry) -> None:
    """Remove the sidebar entry when the last room goes away."""
    if not hass.data.get(_REGISTERED):
        return
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id != leaving.entry_id and entry.state is ConfigEntryState.LOADED:
            return
    async_remove_panel(hass, PANEL_URL_PATH)
    hass.data[_REGISTERED] = False
