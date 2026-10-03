from __future__ import annotations
from copy import deepcopy
from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import FlightRadar24Coordinator
from .const import (
    DOMAIN,
    CONF_TRACKER_NAME_STYLE,
    CONF_TRACKER_NAME_DEFAULT,
    TRACKER_NAME_CALLSIGN_ROUTE,
    TRACKER_NAME_REG_ROUTE,
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if not coordinator.enable_tracker:
        return

    async_add_entities([FlightRadar24Tracker(coordinator)])


class FlightRadar24Tracker(CoordinatorEntity, TrackerEntity):
    def __init__(self, coordinator: FlightRadar24Coordinator) -> None:
        self.info = {}
        self._info_snapshot = {}
        super().__init__(coordinator)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write tracker state only when its flight data changes.

        TrackerEntity forces writes for every coordinator notification. The
        integration publishes intermediate values several times per scan, so
        keep a snapshot to suppress identical writes (the tracked flight dict
        itself is updated in place).
        """
        if not self.coordinator.enable_tracker:
            return

        info = self.info
        if not info:
            info = next(
                (
                    flight
                    for flight in self.coordinator.flight.tracked.values()
                    if flight.get("tracked_type") == "live"
                ),
                {},
            )
        else:
            flight = self.coordinator.flight.tracked.get(info.get("id"))
            info = flight if flight and flight.get("tracked_type") == "live" else {}

        if info == self._info_snapshot:
            return

        self.info = info
        self._info_snapshot = deepcopy(info)
        self.async_write_ha_state()

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def unique_id(self) -> str:
        return f"{self.coordinator.unique_id}_{DOMAIN}"

    @property
    def extra_state_attributes(self) -> dict[str, str]:
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
