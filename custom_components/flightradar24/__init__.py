from __future__ import annotations
from logging import getLogger
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, CoreState, EVENT_HOMEASSISTANT_STARTED
from homeassistant.exceptions import ConfigEntryNotReady
from .api.client import FlightRadarClient
from .const import DOMAIN, SESSION_SETUP_MAX_TRIES
from .coordinator import FlightRadar24Coordinator, is_session_healthy
from .frontend import JSModuleRegistration
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
    CONF_ENABLE_TRACKER,
    CONF_ENABLE_TRACKER_DEFAULT,
    MIN_ALTITUDE,
    MAX_ALTITUDE,
    CONF_AUTO_CLEANUP,
    CONF_AUTO_CLEANUP_DEFAULT,
)
from FlightRadarAPI import FlightRadar24API, Entity

PLATFORMS: list[Platform] = [
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.BUTTON,
]

_LOGGER = getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration (frontend registration once)."""

    async def _register_frontend(_event=None) -> None:
        await JSModuleRegistration(hass).async_register()

    if hass.state == CoreState.running:
        await _register_frontend()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_frontend)

    return True


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
    session_verified = False
    for attempt in range(1, SESSION_SETUP_MAX_TRIES + 1):
        try:
            session_verified = await hass.async_add_executor_job(is_session_healthy, client)
        except Exception as e:
            raise ConfigEntryNotReady('FlightRadar24 is not reachable: {}'.format(e)) from e
        if session_verified:
            break
        _LOGGER.warning(
            'FlightRadar24: got an empty session (bot mitigation), recreating (%d/%d)',
            attempt, SESSION_SETUP_MAX_TRIES,
        )
        client = await create_client()

    if not session_verified:
        # Deliberately not ConfigEntryNotReady: FR24 is reachable, only this
        # session is suspect. Failing setup would send HA into its 5/10/20/40s
        # retry backoff and leave every entity unavailable for minutes after a
        # restart. Carry on - the coordinator's guard renews the session on the
        # first empty cycle instead.
        _LOGGER.warning(
            'FlightRadar24: could not verify the session during setup (bot mitigation), '
            'continuing - the runtime session guard will renew it if it stays empty'
        )

    latitude = entry.data[CONF_LATITUDE]
    longitude = entry.data[CONF_LONGITUDE]

    bounds = client.get_bounds_by_point(latitude, longitude, entry.data[CONF_RADIUS])

    # A cleared optional field is stored as None, and `None <= altitude` raises -
    # which used to abort the whole area update and pin the counts to 0.
    min_altitude = entry.data.get(CONF_MIN_ALTITUDE)
    max_altitude = entry.data.get(CONF_MAX_ALTITUDE)

    coordinator = FlightRadar24Coordinator(
        hass,
        bounds,
        FlightRadarClient(client, _LOGGER),
        entry.data[CONF_SCAN_INTERVAL],
        _LOGGER,
        entry.entry_id,
        MIN_ALTITUDE if min_altitude is None else int(min_altitude),
        MAX_ALTITUDE if max_altitude is None else int(max_altitude),
        Entity(latitude, longitude),
        session_verified,
        entry.data.get(CONF_AUTO_CLEANUP, CONF_AUTO_CLEANUP_DEFAULT)
    )

    coordinator.enable_tracker = entry.data.get(CONF_ENABLE_TRACKER, CONF_ENABLE_TRACKER_DEFAULT)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    # Kick off the first refresh without blocking setup - entities register
    # immediately and fill as soon as the first cycle completes, instead of
    # waiting up to scan_interval for the first scheduled tick.
    entry.async_create_background_task(hass, coordinator.async_refresh(), 'flightradar24_initial_refresh')

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if DOMAIN in hass.data and not hass.data[DOMAIN]:
            del hass.data[DOMAIN]
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
