"""Adds the shared settings and the rooms, and changes them later."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME, UnitOfTemperature, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import (
    CONF_OUTDOOR_ENTITY,
    CONF_PHASE_OFFSET,
    CONF_PV_ENTITY,
    CONF_TARGET,
    CONF_THERMOSTAT,
    CONF_WATER_TEMPERATURE,
    DEFAULT_PHASE_OFFSET,
    DEFAULT_TARGET,
    DEFAULT_WATER_TEMPERATURE,
    DOMAIN,
    MAX_TARGET,
    MAX_WATER_TEMPERATURE,
    MIN_TARGET,
    MIN_WATER_TEMPERATURE,
    SETTINGS_ID,
    TARGET_STEP,
    is_settings_entry,
)
from .coordinator import merged_config

SHARED_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WATER_TEMPERATURE, default=DEFAULT_WATER_TEMPERATURE): NumberSelector(
            NumberSelectorConfig(
                min=MIN_WATER_TEMPERATURE,
                max=MAX_WATER_TEMPERATURE,
                step=0.5,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfTemperature.CELSIUS,
            )
        ),
        vol.Optional(CONF_OUTDOOR_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.TEMPERATURE)
        ),
        vol.Optional(CONF_PV_ENTITY): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER)),
    }
)
ROOM_FIELDS = {
    vol.Required(CONF_PHASE_OFFSET, default=DEFAULT_PHASE_OFFSET): NumberSelector(
        NumberSelectorConfig(
            min=0,
            max=180,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement=UnitOfTime.MINUTES,
        )
    ),
}
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): TextSelector(),
        vol.Required(CONF_THERMOSTAT): EntitySelector(EntitySelectorConfig(domain=CLIMATE_DOMAIN)),
        vol.Required(CONF_TARGET, default=DEFAULT_TARGET): NumberSelector(
            NumberSelectorConfig(
                min=MIN_TARGET,
                max=MAX_TARGET,
                step=TARGET_STEP,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfTemperature.CELSIUS,
            )
        ),
        **ROOM_FIELDS,
    }
)
ROOM_OPTIONS_SCHEMA = vol.Schema(ROOM_FIELDS)


class WhatTheHeatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Asks for the shared settings the first time, and adds one room each time after that.

    A thermostat can belong to only one room.
    """

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the room's settings, or for the shared settings while there are none."""
        if not any(is_settings_entry(entry) for entry in self._async_current_entries()):
            return await self.async_step_settings()
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)
        registered = er.async_get(self.hass).async_get(user_input[CONF_THERMOSTAT])
        if registered is not None and registered.platform == DOMAIN:
            # A room's own thermostat entity would make the room control itself.
            return self.async_show_form(
                step_id="user",
                data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
                errors={CONF_THERMOSTAT: "own_entity"},
            )
        await self.async_set_unique_id(user_input[CONF_THERMOSTAT])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the settings shared by all rooms."""
        if user_input is None:
            return self.async_show_form(step_id="settings", data_schema=SHARED_SCHEMA)
        await self.async_set_unique_id(SETTINGS_ID)
        self._abort_if_unique_id_configured(error="settings_exist")
        return self.async_create_entry(title="Shared settings", data={}, options=user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the settings form of a room or of the shared settings."""
        return SharedSettingsOptionsFlow() if is_settings_entry(config_entry) else RoomOptionsFlow()


class RoomOptionsFlow(OptionsFlow):
    """Changes the settings of a room. The target has its own entity."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the settings."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(ROOM_OPTIONS_SCHEMA, merged_config(self.config_entry)),
        )


class SharedSettingsOptionsFlow(OptionsFlow):
    """Changes the settings shared by all rooms."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the shared settings."""
        return await self.async_step_settings()

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the shared settings. A sensor left empty is removed."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(SHARED_SCHEMA, self.config_entry.options),
        )
