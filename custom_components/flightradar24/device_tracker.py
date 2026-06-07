from __future__ import annotations
from typing import Any

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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
    if not coordinator.enable_tracker:
        return

    tracked: dict[str, FlightRadar24Tracker] = {}

    @callback
    def add_new_trackers() -> None:
        """Add a device tracker for each live tracked flight."""
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
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{entry_id}_{DOMAIN}_{tracker_key}"

    @property
    def info(self) -> dict[str, Any]:
        for flight in _live_tracked_flights(self.coordinator):
            if flight_tracker_key(flight) == self.tracker_key:
                return flight
        return {}

    @property
    def available(self) -> bool:
        return bool(self.info)

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.info

    @property
    def latitude(self) -> float | None:
        return self.info.get('latitude')

    @property
    def longitude(self) -> float | None:
        return self.info.get('longitude')

    @property
    def icon(self) -> str:
        return "mdi:airplane"

    @property
    def entity_picture(self) -> str | None:
        # This tells the map to show the actual photo of the plane!
        return self.info.get('aircraft_photo_small')

    @property
    def name(self) -> str:
        # If no flight is currently tracked, return the default domain name
        if not self.info:
            return DOMAIN

        # Check what the user selected in the Integration Options
        style = self.coordinator.config_entry.data.get(
            CONF_TRACKER_NAME_STYLE, CONF_TRACKER_NAME_DEFAULT
        )

        # Safely grab the flight data, falling back to 'N/A' if it's missing
        callsign = self.info.get('callsign') or self.info.get('flight_number') or "Unknown"
        reg = self.info.get('aircraft_registration') or callsign
        origin = self.info.get('airport_origin_code_iata') or "N/A"
        dest = self.info.get('airport_destination_code_iata') or "N/A"

        # Piece the string together based on their preference!
        if style == TRACKER_NAME_CALLSIGN_ROUTE:
            return f"{callsign} ({origin} - {dest})"
        elif style == TRACKER_NAME_REG_ROUTE:
            return f"{reg} ({origin} - {dest})"

        # Default fallback (Callsign only)
        return callsign
