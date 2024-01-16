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
from FlightRadar24 import FlightRadar24API

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)

    client = FlightRadar24API(username, password) if username and password else FlightRadar24API()

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
    )

    await coordinator.async_config_entry_first_refresh()
    # Store coordinator in global data
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload opensky config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
