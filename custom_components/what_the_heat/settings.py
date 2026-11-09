"""Settings shared by all rooms: the water temperature, and the outdoor and PV sensors."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .const import (
    CONF_OUTDOOR_ENTITY,
    CONF_PV_ENTITY,
    DEFAULT_WATER_TEMPERATURE,
    DOMAIN,
    MAX_WATER_TEMPERATURE,
    MIN_WATER_TEMPERATURE,
    SAVE_INTERVAL_S,
    SERVICE_SET_SENSORS,
    SERVICE_SET_WATER_TEMPERATURE,
    STORAGE_VERSION,
)
from .core.sun import SunSignal

_SETTINGS = f"{DOMAIN}_settings"
_LOCK = f"{DOMAIN}_settings_lock"
_WATER_SCHEMA = vol.Schema(
    {vol.Required(ATTR_TEMPERATURE): vol.All(vol.Coerce(float), vol.Range(MIN_WATER_TEMPERATURE, MAX_WATER_TEMPERATURE))}
)
# An empty value removes the sensor, and a missing one leaves it as it is.
_SENSOR = vol.Any(None, "", cv.entity_id)
_SENSORS_SCHEMA = vol.Schema({vol.Optional(CONF_OUTDOOR_ENTITY): _SENSOR, vol.Optional(CONF_PV_ENTITY): _SENSOR})


class GlobalSettings:
    """Holds and saves the settings. This integration neither reads nor changes the heat source.

    It also turns PV power into a share of full sun, once for the whole house.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.settings")
        self.water_temperature = DEFAULT_WATER_TEMPERATURE
        self.outdoor_entity: str | None = None
        self.pv_entity: str | None = None
        self._sun = SunSignal()
        self._last_save_s: float | None = None

    async def async_load(self) -> None:
        """Restore the saved values."""
        stored = await self._store.async_load() or {}
        self.water_temperature = stored.get("water_temperature", DEFAULT_WATER_TEMPERATURE)
        self.outdoor_entity = stored.get(CONF_OUTDOOR_ENTITY)
        self.pv_entity = stored.get(CONF_PV_ENTITY)
        self._sun = SunSignal(**stored.get("sun", {}))

    def values(self) -> dict[str, Any]:
        """Return the settings as the owner sees them."""
        return {
            "water_temperature": self.water_temperature,
            CONF_OUTDOOR_ENTITY: self.outdoor_entity,
            CONF_PV_ENTITY: self.pv_entity,
        }

    def snapshot(self) -> dict[str, Any]:
        """Return everything worth keeping across a restart."""
        return {**self.values(), "sun": self._sun.snapshot()}

    async def async_set_water_temperature(self, value: float) -> None:
        """Change and save the water temperature."""
        self.water_temperature = value
        await self._store.async_save(self.snapshot())

    async def async_set_sensors(self, changes: dict[str, str | None]) -> None:
        """Change and save the sensors named in changes. An empty name removes one."""
        if CONF_OUTDOOR_ENTITY in changes:
            self.outdoor_entity = changes[CONF_OUTDOOR_ENTITY] or None
        if CONF_PV_ENTITY in changes:
            pv_entity = changes[CONF_PV_ENTITY] or None
            if pv_entity != self.pv_entity:
                # Another installation has its own full sun.
                self._sun = SunSignal()
            self.pv_entity = pv_entity
        await self._store.async_save(self.snapshot())

    def sun_share(self, power_w: float | None, now_s: float) -> float | None:
        """Return the share of full sun for this PV power, or None while it is unknown."""
        share = self._sun.update(power_w, now_s)
        # A delayed save restarts its timer on each call, so it is only called when due.
        if power_w is not None and (self._last_save_s is None or now_s - self._last_save_s >= SAVE_INTERVAL_S):
            self._last_save_s = now_s
            self._store.async_delay_save(self.snapshot, 1)
        return share


async def async_get_settings(hass: HomeAssistant) -> GlobalSettings:
    """Return the settings, loading them once for all rooms."""
    async with hass.data.setdefault(_LOCK, asyncio.Lock()):
        if _SETTINGS not in hass.data:
            settings = GlobalSettings(hass)
            await settings.async_load()
            hass.data[_SETTINGS] = settings
    return hass.data[_SETTINGS]


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings"})
@callback
def _settings_query(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    connection.send_result(msg["id"], hass.data[_SETTINGS].values())


def register_services(hass: HomeAssistant, settings: GlobalSettings) -> None:
    """Add the services that change the settings and the query the page reads them with, once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_WATER_TEMPERATURE):
        return

    async def refresh_rooms() -> None:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is ConfigEntryState.LOADED:
                await entry.runtime_data.async_refresh()

    async def set_water_temperature(call: ServiceCall) -> None:
        await settings.async_set_water_temperature(call.data[ATTR_TEMPERATURE])
        await refresh_rooms()

    async def set_sensors(call: ServiceCall) -> None:
        await settings.async_set_sensors(dict(call.data))
        await refresh_rooms()

    hass.services.async_register(DOMAIN, SERVICE_SET_WATER_TEMPERATURE, set_water_temperature, _WATER_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_SENSORS, set_sensors, _SENSORS_SCHEMA)
    websocket_api.async_register_command(hass, _settings_query)
