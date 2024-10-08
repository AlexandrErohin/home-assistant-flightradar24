from __future__ import annotations
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import FlightRadar24Coordinator
from .const import DOMAIN


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    tracked: dict[str, FlightRadar24Tracker] = {}

    @callback
    def coordinator_updated():
        """Update the status of the device."""
        update_items(coordinator, async_add_entities, tracked)

    entry.async_on_unload(coordinator.async_add_listener(coordinator_updated))
    coordinator_updated()


@callback
def update_items(
        coordinator: FlightRadar24Coordinator,
        async_add_entities: AddEntitiesCallback,
        tracked: dict[str, FlightRadar24Tracker],
) -> None:
    if not coordinator.enable_tracker:
        return

    new_tracked: list[FlightRadar24Tracker] = []
    active: list[str] = []
    for flight in coordinator.tracked.values():
        flight_id = flight['flight_number'] if flight['flight_number'] else flight['callsign']
        active.append(flight_id)
        if flight_id not in tracked:
            tracked[flight_id] = FlightRadar24Tracker(coordinator, flight)
            new_tracked.append(tracked[flight_id])
        else:
            tracked[flight_id].info = flight

    if new_tracked:
        async_add_entities(new_tracked)


class FlightRadar24Tracker(CoordinatorEntity, TrackerEntity):
    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            data: dict,
    ) -> None:
        self.info = data

        super().__init__(coordinator)

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def unique_id(self) -> str:
        return f"{self.coordinator.unique_id}_{DOMAIN}_{self.info['flight_number']}"

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
    def name(self) -> str:
        return self.info['flight_number']
