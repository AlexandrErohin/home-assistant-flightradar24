from logging import getLogger
import voluptuous as vol
from typing import Any
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlowWithConfigEntry,
    OptionsFlow,
)
from .const import (
    DOMAIN,
    DEFAULT_NAME,
    CONF_MIN_ALTITUDE,
    CONF_MAX_ALTITUDE,
    CONF_MOST_TRACKED,
    CONF_ENABLE_TRACKER,
    CONF_MOST_TRACKED_DEFAULT,
    CONF_ENABLE_TRACKER_DEFAULT,
    MIN_ALTITUDE,
    MAX_ALTITUDE,
)
from FlightRadar24 import FlightRadar24API
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import callback
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    CONF_PASSWORD,
    CONF_USERNAME,
)

_LOGGER = getLogger(__name__)


class FlightRadarConfigFlow(ConfigFlow, domain=DOMAIN):

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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FlightRadarOptionsFlow(config_entry)


class FlightRadarOptionsFlow(OptionsFlowWithConfigEntry):

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        data = user_input or self.config_entry.data

        if user_input is not None:
            username = data.get(CONF_USERNAME)
            password = data.get(CONF_PASSWORD)

            try:
                if username and password:
                    client = FlightRadar24API()
                    await self.hass.async_add_executor_job(client.login, username, password)
                elif password and not username or username and not password:
                    errors['base'] = 'You need to pass username and password'
            except Exception as error:
                _LOGGER.error('FlightRadar24 Integration Exception - {}'.format(error))
                errors['base'] = str(error)

            if not errors:
                self.hass.config_entries.async_update_entry(self.config_entry, data=user_input)
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        data_schema = vol.Schema({
            vol.Required(CONF_RADIUS, default=data.get(CONF_RADIUS)): vol.Coerce(float),
            vol.Required(CONF_LATITUDE, default=data.get(CONF_LATITUDE)): cv.latitude,
            vol.Required(CONF_LONGITUDE, default=data.get(CONF_LONGITUDE)): cv.longitude,
            vol.Required(CONF_SCAN_INTERVAL, default=data.get(CONF_SCAN_INTERVAL)): int,
            vol.Optional(CONF_MIN_ALTITUDE,
                         description={"suggested_value": data.get(CONF_MIN_ALTITUDE, MIN_ALTITUDE)}): int,
            vol.Optional(CONF_MAX_ALTITUDE,
                         description={"suggested_value": data.get(CONF_MAX_ALTITUDE, MAX_ALTITUDE)}): int,
            vol.Optional(CONF_MOST_TRACKED,
                         description={
                             "suggested_value": data.get(CONF_MOST_TRACKED, CONF_MOST_TRACKED_DEFAULT)}): cv.boolean,
            vol.Optional(CONF_ENABLE_TRACKER,
                         description={
                             "suggested_value": data.get(CONF_ENABLE_TRACKER,
                                                         CONF_ENABLE_TRACKER_DEFAULT)}): cv.boolean,
            vol.Optional(CONF_USERNAME, description={"suggested_value": data.get(CONF_USERNAME, '')}): cv.string,
            vol.Optional(CONF_PASSWORD, description={"suggested_value": data.get(CONF_PASSWORD, '')}): cv.string,
        })

        return self.async_show_form(step_id="init", data_schema=data_schema, errors=errors)
