from __future__ import annotations
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from .coordinator import FlightRadar24Coordinator
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from .const import (
    CONF_MIN_ALTITUDE,
    CONF_MAX_ALTITUDE,
    MIN_ALTITUDE,
    MAX_ALTITUDE,
)
from FlightRadar24 import FlightRadar24API
from .sensor import SENSOR_TYPES

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.TEXT,
]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)

    client = FlightRadar24API()
    if username and password:
        await hass.async_add_executor_job(client.login, username, password)

    bounds = client.get_bounds_by_point(
        entry.data[CONF_LATITUDE],
        entry.data[CONF_LONGITUDE],
        entry.data[CONF_RADIUS],
    )

    coordinator = FlightRadar24Coordinator(
        hass,
        bounds,
        client,
        entry.data[CONF_SCAN_INTERVAL],
        _LOGGER,
        entry.entry_id,
        entry.data.get(CONF_MIN_ALTITUDE, MIN_ALTITUDE),
        entry.data.get(CONF_MAX_ALTITUDE, MAX_ALTITUDE),
    )

    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
