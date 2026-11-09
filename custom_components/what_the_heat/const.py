"""Constants for the what-the-heat integration."""

from __future__ import annotations

from typing import Any

DOMAIN = "what_the_heat"
VERSION = "0.7.0"
PLATFORMS = ["binary_sensor", "button", "climate", "number", "select", "sensor"]

CONF_THERMOSTAT = "thermostat"
CONF_TARGET = "target"
CONF_PHASE_OFFSET = "phase_offset"
# Shared by all rooms, in the integration's own settings entry.
CONF_WATER_TEMPERATURE = "water_temperature"
CONF_OUTDOOR_ENTITY = "outdoor_entity"
CONF_PV_ENTITY = "pv_entity"
SETTINGS_ID = "shared_settings"
LEGACY_SETTINGS = ("buffer_entity", "buffer_fallback", CONF_OUTDOOR_ENTITY)

DEFAULT_TARGET = 21.0
DEFAULT_PHASE_OFFSET = 0

MIN_TARGET = 5.0
MAX_TARGET = 30.0
TARGET_STEP = 0.5

DEFAULT_WATER_TEMPERATURE = 30.0
MIN_WATER_TEMPERATURE = 20.0
MAX_WATER_TEMPERATURE = 38.0

UPDATE_INTERVAL_S = 60
MAX_LOG_STEP_S = 300.0
STORAGE_VERSION = 1
SAVE_INTERVAL_S = 300


def is_settings_entry(entry: Any) -> bool:
    """Return whether a configuration entry holds the shared settings rather than a room."""
    return entry.unique_id == SETTINGS_ID
