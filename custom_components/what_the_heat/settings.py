"""Settings shared by all rooms, kept in the integration's own settings entry.

The water temperature and the outdoor and PV sensors rarely change, so they are set with
Configure on that entry. Without it the rooms use 30 °C water and no sensors.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_OUTDOOR_ENTITY,
    CONF_PV_ENTITY,
    CONF_WATER_TEMPERATURE,
    DEFAULT_WATER_TEMPERATURE,
    DOMAIN,
    SAVE_INTERVAL_S,
    STORAGE_VERSION,
    is_settings_entry,
)
from .core.sun import SunSignal

_SETTINGS = f"{DOMAIN}_settings"
_LOCK = f"{DOMAIN}_settings_lock"


class GlobalSettings:
    """The shared settings, and the share of full sun from PV, worked out once for the house.

    This integration neither reads nor changes the heat source.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.settings")
        self.water_temperature = DEFAULT_WATER_TEMPERATURE
        self.outdoor_entity: str | None = None
        self.pv_entity: str | None = None
        self._sun = SunSignal()
        self._sun_entity: str | None = None  # the PV sensor whose full sun the signal holds
        self._last_save_s: float | None = None

    async def async_load(self) -> None:
        """Restore what was learned about full sun."""
        stored = await self._store.async_load() or {}
        self._sun = SunSignal(**stored.get("sun", {}))
        self._sun_entity = stored.get(CONF_PV_ENTITY)

    def apply(self, options: Mapping[str, Any]) -> None:
        """Use the values of the settings entry. Missing ones fall back to the defaults."""
        self.water_temperature = options.get(CONF_WATER_TEMPERATURE, DEFAULT_WATER_TEMPERATURE)
        self.outdoor_entity = options.get(CONF_OUTDOOR_ENTITY) or None
        self.pv_entity = options.get(CONF_PV_ENTITY) or None
        if self.pv_entity != self._sun_entity:
            # Another installation has its own full sun.
            self._sun = SunSignal()
            self._sun_entity = self.pv_entity

    def snapshot(self) -> dict[str, Any]:
        """Return the settings and what is known about full sun, for diagnostics."""
        return {
            CONF_WATER_TEMPERATURE: self.water_temperature,
            CONF_OUTDOOR_ENTITY: self.outdoor_entity,
            CONF_PV_ENTITY: self.pv_entity,
            "sun": self._sun.snapshot(),
        }

    def sun_share(self, power_w: float | None, now_s: float) -> float | None:
        """Return the share of full sun for this PV power, or None while it is unknown."""
        share = self._sun.update(power_w, now_s)
        # A delayed save restarts its timer on each call, so it is only called when due.
        if power_w is not None and (self._last_save_s is None or now_s - self._last_save_s >= SAVE_INTERVAL_S):
            self._last_save_s = now_s
            self._store.async_delay_save(self._stored, 1)
        return share

    def _stored(self) -> dict[str, Any]:
        return {CONF_PV_ENTITY: self._sun_entity, "sun": self._sun.snapshot()}


def _settings_entry(hass: HomeAssistant) -> ConfigEntry | None:
    return next((entry for entry in hass.config_entries.async_entries(DOMAIN) if is_settings_entry(entry)), None)


async def async_get_settings(hass: HomeAssistant) -> GlobalSettings:
    """Return the settings, loading them once for all rooms, whichever entry starts first."""
    async with hass.data.setdefault(_LOCK, asyncio.Lock()):
        if _SETTINGS not in hass.data:
            settings = GlobalSettings(hass)
            await settings.async_load()
            entry = _settings_entry(hass)
            settings.apply(entry.options if entry else {})
            hass.data[_SETTINGS] = settings
    return hass.data[_SETTINGS]


async def async_apply_settings(hass: HomeAssistant, options: Mapping[str, Any]) -> None:
    """Use changed settings, and let the running rooms act on them right away."""
    settings = await async_get_settings(hass)
    settings.apply(options)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if not is_settings_entry(entry) and entry.state is ConfigEntryState.LOADED:
            await entry.runtime_data.async_refresh()
