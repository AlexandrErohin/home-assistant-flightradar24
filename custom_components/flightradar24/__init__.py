from __future__ import annotations
from logging import getLogger
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from .api.client import FlightRadarClient
from .const import DOMAIN, SESSION_SETUP_MAX_TRIES
from .coordinator import FlightRadar24Coordinator, is_session_healthy
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
    CONF_MOST_TRACKED,
    CONF_MOST_TRACKED_DEFAULT,
    CONF_ENABLE_TRACKER,
    CONF_ENABLE_TRACKER_DEFAULT,
    MIN_ALTITUDE,
    MAX_ALTITUDE,
)
from FlightRadar24 import FlightRadar24API, Entity

PLATFORMS: list[Platform] = [
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.BUTTON,
]

_LOGGER = getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    import logging
    logging.getLogger("FlightRadarAPI").setLevel(logging.ERROR)
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)

    async def create_client() -> FlightRadar24API:
        new_client = FlightRadar24API()
        if username and password:
            await hass.async_add_executor_job(new_client.login, username, password)
        return new_client

    client = await create_client()

    # FR24's bot mitigation randomly hands out sessions that only ever receive
    # valid but empty feed responses, and a session keeps that fate for its
    # entire lifetime (#278, #271). Verify the session before using it.
    for attempt in range(1, SESSION_SETUP_MAX_TRIES + 1):
        try:
            healthy = await hass.async_add_executor_job(is_session_healthy, client)
        except Exception as e:
            raise ConfigEntryNotReady('FlightRadar24 is not reachable: {}'.format(e)) from e
        if healthy:
            break
        _LOGGER.warning(
            'FlightRadar24: got an empty session (bot mitigation), recreating (%d/%d)',
            attempt, SESSION_SETUP_MAX_TRIES,
        )
        client = await create_client()
    else:
        raise ConfigEntryNotReady(
            'FlightRadar24 keeps handing out empty sessions (bot mitigation), retrying setup later'
        )

    latitude = entry.data[CONF_LATITUDE]
    longitude = entry.data[CONF_LONGITUDE]

    bounds = client.get_bounds_by_point(latitude, longitude, entry.data[CONF_RADIUS])

    coordinator = FlightRadar24Coordinator(
        hass,
        bounds,
        FlightRadarClient(client, _LOGGER),
        entry.data[CONF_SCAN_INTERVAL],
        _LOGGER,
        entry.entry_id,
        entry.data.get(CONF_MIN_ALTITUDE, MIN_ALTITUDE),
        entry.data.get(CONF_MAX_ALTITUDE, MAX_ALTITUDE),
        Entity(latitude, longitude),
    )

    if entry.data.get(CONF_MOST_TRACKED, CONF_MOST_TRACKED_DEFAULT):
        coordinator.flight.enable_most_tracked()
    coordinator.enable_tracker = entry.data.get(CONF_ENABLE_TRACKER, CONF_ENABLE_TRACKER_DEFAULT)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
