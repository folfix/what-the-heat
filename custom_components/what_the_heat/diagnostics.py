"""Diagnostics download: settings, controller state and the daily measurements."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import merged_config


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return everything needed to evaluate a room's run."""
    coordinator = entry.runtime_data
    return {
        "config": merged_config(entry),
        "runner": coordinator.runner.snapshot(),
        "today": coordinator.log.today,
        "days": coordinator.log.rows,
    }
