"""Constants for the what-the-heat integration."""

from __future__ import annotations

DOMAIN = "what_the_heat"
VERSION = "0.3.2"
PLATFORMS = ["binary_sensor", "climate", "number", "select", "sensor"]

CONF_THERMOSTAT = "thermostat"
CONF_TARGET = "target"
CONF_OUTDOOR_ENTITY = "outdoor_entity"
CONF_PHASE_OFFSET = "phase_offset"
LEGACY_SETTINGS = ("buffer_entity", "buffer_fallback")

DEFAULT_TARGET = 21.0
DEFAULT_PHASE_OFFSET = 0

MIN_TARGET = 5.0
MAX_TARGET = 30.0
TARGET_STEP = 0.5

DEFAULT_WATER_TEMPERATURE = 30.0
MIN_WATER_TEMPERATURE = 20.0
MAX_WATER_TEMPERATURE = 38.0
SERVICE_SET_WATER_TEMPERATURE = "set_water_temperature"

UPDATE_INTERVAL_S = 60
MAX_LOG_STEP_S = 300.0
STORAGE_VERSION = 1
SAVE_INTERVAL_S = 300
