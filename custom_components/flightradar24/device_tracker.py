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
    if not coordinator.enable_tracker:
        return

    tracked = FlightRadar24Tracker(coordinator)
    async_add_entities([tracked])

    @callback
    def coordinator_updated():
        """Update the status of the device."""
        update_items(coordinator, tracked)

    entry.async_on_unload(coordinator.async_add_listener(coordinator_updated))
    coordinator_updated()


@callback
def update_items(coordinator: FlightRadar24Coordinator, tracked: FlightRadar24Tracker) -> None:
    if not coordinator.enable_tracker:
        return

    if not tracked.info:
        for flight in coordinator.tracked.values():
            if flight.get('tracked_type') == 'live':
                tracked.info = flight
                break
    else:
        flight = coordinator.tracked.get(tracked.info['id'])
        if flight and flight.get('tracked_type') == 'live':
            tracked.info = coordinator.tracked.get(tracked.info['id'])
        else:
            tracked.info = {}


class FlightRadar24Tracker(CoordinatorEntity, TrackerEntity):
    def __init__(self, coordinator: FlightRadar24Coordinator) -> None:
        self.info = {}
        super().__init__(coordinator)

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
    def name(self) -> str:
        return DOMAIN
