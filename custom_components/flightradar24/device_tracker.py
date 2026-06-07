from __future__ import annotations
from typing import Any

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import FlightRadar24Coordinator
from .flight_key import flight_tracker_key
from .const import (
    DOMAIN,
    CONF_TRACKER_NAME_STYLE,
    CONF_TRACKER_NAME_DEFAULT,
    TRACKER_NAME_CALLSIGN_ROUTE,
    TRACKER_NAME_REG_ROUTE,
)


def _live_tracked_flights(coordinator: FlightRadar24Coordinator) -> list[dict[str, Any]]:
    return [
        flight
        for flight in coordinator.flight.tracked.values()
        if flight.get('tracked_type') == 'live'
    ]


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    ent_reg = er.async_get(hass)
    old_unique_id = f"{coordinator.unique_id}_{DOMAIN}"
    if entity_id := ent_reg.async_get_entity_id("device_tracker", DOMAIN, old_unique_id):
        ent_reg.async_remove(entity_id)

    if not coordinator.enable_tracker:
        return

    tracked: dict[str, FlightRadar24Tracker] = {}

    @callback
    def add_new_trackers() -> None:
        """Add a device tracker for each live tracked flight."""
        current_keys = {
            tracker_key
            for flight in coordinator.flight.tracked_list
            if (tracker_key := flight_tracker_key(flight))
        }
        for tracker_key in set(tracked) - current_keys:
            tracker = tracked.pop(tracker_key)
            if entity_id := ent_reg.async_get_entity_id(
                    "device_tracker",
                    DOMAIN,
                    FlightRadar24Tracker.unique_id(entry.entry_id, tracker_key),
            ):
                ent_reg.async_remove(entity_id)
            hass.async_create_task(tracker.async_remove())

        if not coordinator.enable_tracker:
            return

        new_entities: list[FlightRadar24Tracker] = []
        for flight in _live_tracked_flights(coordinator):
            tracker_key = flight_tracker_key(flight)
            if not tracker_key or tracker_key in tracked:
                continue

            tracker = FlightRadar24Tracker(coordinator, entry.entry_id, tracker_key)
            tracked[tracker_key] = tracker
            new_entities.append(tracker)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(add_new_trackers))
    add_new_trackers()


class FlightRadar24Tracker(CoordinatorEntity, TrackerEntity):
    def __init__(self, coordinator: FlightRadar24Coordinator, entry_id: str, tracker_key: str) -> None:
        self.tracker_key = tracker_key
        super().__init__(coordinator)
        self._info = self._find_info()
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = self.unique_id(entry_id, tracker_key)

    @staticmethod
    def unique_id(entry_id: str, tracker_key: str) -> str:
        return f"{entry_id}_{DOMAIN}_{tracker_key}"

    def _find_info(self) -> dict[str, Any]:
        for flight in _live_tracked_flights(self.coordinator):
            if flight_tracker_key(flight) == self.tracker_key:
                return flight
        return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._info = self._find_info()
        self.async_write_ha_state()

    @property
    def info(self) -> dict[str, Any]:
        return self._info

    @property
    def available(self) -> bool:
        info = self.info
        return bool(info)

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = self.info
        return info

    @property
    def latitude(self) -> float | None:
        info = self.info
        return info.get('latitude')

    @property
    def longitude(self) -> float | None:
        info = self.info
        return info.get('longitude')

    @property
    def icon(self) -> str:
        return "mdi:airplane"

    @property
    def entity_picture(self) -> str | None:
        # This tells the map to show the actual photo of the plane!
        info = self.info
        return info.get('aircraft_photo_small')

    @property
    def name(self) -> str:
        info = self.info
        # If no flight is currently tracked, return the default domain name
        if not info:
            return DOMAIN

        # Check what the user selected in the Integration Options
        style = self.coordinator.config_entry.data.get(
            CONF_TRACKER_NAME_STYLE, CONF_TRACKER_NAME_DEFAULT
        )

        # Safely grab the flight data, falling back to 'N/A' if it's missing
        callsign = info.get('callsign') or info.get('flight_number') or "Unknown"
        reg = info.get('aircraft_registration') or callsign
        origin = info.get('airport_origin_code_iata') or "N/A"
        dest = info.get('airport_destination_code_iata') or "N/A"

        # Piece the string together based on their preference!
        if style == TRACKER_NAME_CALLSIGN_ROUTE:
            return f"{callsign} ({origin} - {dest})"
        elif style == TRACKER_NAME_REG_ROUTE:
            return f"{reg} ({origin} - {dest})"

        # Default fallback (Callsign only)
        return callsign
