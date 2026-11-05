"""Settings shared by all rooms: the temperature of the water going into the floors."""

from __future__ import annotations

import asyncio

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_WATER_TEMPERATURE,
    DOMAIN,
    MAX_WATER_TEMPERATURE,
    MIN_WATER_TEMPERATURE,
    SERVICE_SET_WATER_TEMPERATURE,
    STORAGE_VERSION,
)

_SETTINGS = f"{DOMAIN}_settings"
_LOCK = f"{DOMAIN}_settings_lock"
_SERVICE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_TEMPERATURE): vol.All(vol.Coerce(float), vol.Range(MIN_WATER_TEMPERATURE, MAX_WATER_TEMPERATURE))}
)


class GlobalSettings:
    """Holds and saves the settings. This integration neither reads nor changes the heat source."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, float]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.settings")
        self.water_temperature = DEFAULT_WATER_TEMPERATURE

    async def async_load(self) -> None:
        """Restore the saved values."""
        stored = await self._store.async_load() or {}
        self.water_temperature = stored.get("water_temperature", DEFAULT_WATER_TEMPERATURE)

    async def async_set_water_temperature(self, value: float) -> None:
        """Change and save the water temperature."""
        self.water_temperature = value
        await self._store.async_save({"water_temperature": value})


async def async_get_settings(hass: HomeAssistant) -> GlobalSettings:
    """Return the settings, loading them once for all rooms."""
    async with hass.data.setdefault(_LOCK, asyncio.Lock()):
        if _SETTINGS not in hass.data:
            settings = GlobalSettings(hass)
            await settings.async_load()
            hass.data[_SETTINGS] = settings
    return hass.data[_SETTINGS]


def register_services(hass: HomeAssistant, settings: GlobalSettings) -> None:
    """Add the service that changes the water temperature, once for all rooms."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_WATER_TEMPERATURE):
        return

    async def set_water_temperature(call: ServiceCall) -> None:
        await settings.async_set_water_temperature(call.data[ATTR_TEMPERATURE])
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is ConfigEntryState.LOADED:
                await entry.runtime_data.async_refresh()

    hass.services.async_register(DOMAIN, SERVICE_SET_WATER_TEMPERATURE, set_water_temperature, _SERVICE_SCHEMA)
