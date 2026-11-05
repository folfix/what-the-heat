"""Adds a room, and changes its settings later."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
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
    CONF_TARGET,
    CONF_THERMOSTAT,
    DEFAULT_PHASE_OFFSET,
    DEFAULT_TARGET,
    DOMAIN,
    MAX_TARGET,
    MIN_TARGET,
    TARGET_STEP,
)
from .coordinator import merged_config

SETTINGS_FIELDS = {
    vol.Optional(CONF_OUTDOOR_ENTITY): EntitySelector(EntitySelectorConfig(domain="sensor")),
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
        **SETTINGS_FIELDS,
    }
)
OPTIONS_SCHEMA = vol.Schema(SETTINGS_FIELDS)


class WhatTheHeatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Adds one room. A thermostat can belong to only one room."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the room's settings."""
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the settings form."""
        return WhatTheHeatOptionsFlow()


class WhatTheHeatOptionsFlow(OptionsFlow):
    """Changes the settings of a room. The target has its own entity."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the settings."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, merged_config(self.config_entry)),
        )
