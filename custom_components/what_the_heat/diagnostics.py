"""Diagnostics download: settings, controller state and the daily measurements."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import is_settings_entry
from .coordinator import merged_config
from .settings import async_get_settings


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return everything needed to evaluate a room's run, or the shared settings."""
    shared = (await async_get_settings(hass)).snapshot()
    if is_settings_entry(entry):
        return {"shared": shared}
    coordinator = entry.runtime_data
    return {
        "config": merged_config(entry),
        "shared": shared,
        "runner": coordinator.runner.snapshot(),
        "learned": asdict(coordinator.runner.learned()),
        "today": coordinator.log.today,
        "days": coordinator.log.rows,
    }
