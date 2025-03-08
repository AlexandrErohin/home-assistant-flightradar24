from __future__ import annotations
from logging import getLogger
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from .const import DOMAIN, TRANSLATION_KEY_TRACKED
from .coordinator import FlightRadar24Coordinator
from homeassistant.helpers import restore_state, entity_registry
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
]

_LOGGER = getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)

    client = FlightRadar24API()
    if username and password:
        await hass.async_add_executor_job(client.login, username, password)

    latitude = entry.data[CONF_LATITUDE]
    longitude = entry.data[CONF_LONGITUDE]

    bounds = client.get_bounds_by_point(latitude, longitude, entry.data[CONF_RADIUS])

    coordinator = FlightRadar24Coordinator(
        hass,
        bounds,
        client,
        entry.data[CONF_SCAN_INTERVAL],
        _LOGGER,
        entry.entry_id,
        entry.data.get(CONF_MIN_ALTITUDE, MIN_ALTITUDE),
        entry.data.get(CONF_MAX_ALTITUDE, MAX_ALTITUDE),
        Entity(latitude, longitude),
    )

    coordinator.tracked = get_restore_state(hass, entry)
    coordinator.most_tracked = {} if entry.data.get(CONF_MOST_TRACKED, CONF_MOST_TRACKED_DEFAULT) else None
    coordinator.enable_tracker = entry.data.get(CONF_ENABLE_TRACKER, CONF_ENABLE_TRACKER_DEFAULT)

    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def get_restore_state(hass: HomeAssistant, entry: ConfigEntry):
    existing_entries = entity_registry.async_entries_for_config_entry(
        entity_registry.async_get(hass),
        entry.entry_id,
    )
    last_states = restore_state.async_get(hass).last_states
    for entr in existing_entries:
        if TRANSLATION_KEY_TRACKED == entr.translation_key:
            state = last_states.get(entr.entity_id).state.attributes.get('flights')
            if state:
                tracked = {}
                for item in state:
                    key = item.get('id', item.get('callsign', item.get('flight_number')))
                    if key:
                        tracked[key] = item
                return tracked
    return {}
