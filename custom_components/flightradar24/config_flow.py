from __future__ import annotations
import voluptuous as vol
from typing import Any
from homeassistant import config_entries
from .const import (
    DOMAIN,
    DEFAULT_NAME, CONF_MAP_ENTITIES,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import callback
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        return self.async_show_form(step_id="user", data_schema=self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Required(CONF_RADIUS, default=1000): vol.Coerce(float),
                    vol.Required(CONF_LATITUDE): cv.latitude,
                    vol.Required(CONF_LONGITUDE): cv.longitude,
                    vol.Required(CONF_SCAN_INTERVAL, default=10): int,
                    vol.Required(CONF_MAP_ENTITIES, default=0): int,
                }
            ),
            {
                CONF_LATITUDE: self.hass.config.latitude,
                CONF_LONGITUDE: self.hass.config.longitude,
            },
        ))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self.config_entry.data = user_input
            return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        data = self.config_entry.data

        data_schema = vol.Schema({
            vol.Required(CONF_RADIUS, default=data.get(CONF_RADIUS)): vol.Coerce(float),
            vol.Required(CONF_LATITUDE, default=data.get(CONF_LATITUDE)): cv.latitude,
            vol.Required(CONF_LONGITUDE, default=data.get(CONF_LONGITUDE)): cv.longitude,
            vol.Required(CONF_SCAN_INTERVAL, default=data.get(CONF_SCAN_INTERVAL)): int,
            vol.Required(CONF_MAP_ENTITIES, default=data.get(CONF_MAP_ENTITIES)): int,
        })

        return self.async_show_form(step_id="init", data_schema=data_schema)
