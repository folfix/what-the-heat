"""Constants for the what-the-heat integration."""

from __future__ import annotations

DOMAIN = "what_the_heat"
PLATFORMS = ["binary_sensor", "number", "select", "sensor"]

CONF_THERMOSTAT = "thermostat"
CONF_TARGET = "target"
CONF_BUFFER_ENTITY = "buffer_entity"
CONF_BUFFER_FALLBACK = "buffer_fallback"
CONF_OUTDOOR_ENTITY = "outdoor_entity"
CONF_PHASE_OFFSET = "phase_offset"

DEFAULT_TARGET = 21.0
DEFAULT_BUFFER_FALLBACK = 34.0
DEFAULT_PHASE_OFFSET = 0

BUFFER_LIMIT = 38.0
MIN_TARGET = 5.0
MAX_TARGET = 30.0
TARGET_STEP = 0.5

UPDATE_INTERVAL_S = 60
MAX_LOG_STEP_S = 300.0
STORAGE_VERSION = 1
SAVE_INTERVAL_S = 300
