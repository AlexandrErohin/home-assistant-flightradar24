import voluptuous as vol
from typing import Any
from homeassistant import config_entries
from .const import (
    DOMAIN,
    DEFAULT_NAME,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
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
                }
            ),
            {
                CONF_LATITUDE: self.hass.config.latitude,
                CONF_LONGITUDE: self.hass.config.longitude,
            },
        )
                                    )
