from dataclasses import dataclass
from collections.abc import Callable
from typing import Any
from homeassistant.components.sensor import (
    SensorStateClass,
    SensorEntity,
    RestoreSensor,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from .const import DOMAIN
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import FlightRadar24Coordinator
from .api.flight import is_helicopter
import datetime
import copy


@dataclass
class FlightRadar24SensorRequiredKeysMixin:
    value: Callable[[FlightRadar24Coordinator], Any]
    attributes: Callable[[FlightRadar24Coordinator], Any] | None


@dataclass
class FlightRadar24SensorEntityDescription(SensorEntityDescription, FlightRadar24SensorRequiredKeysMixin):
    """A class that describes sensor entities."""


SENSOR_TYPES: tuple[FlightRadar24SensorEntityDescription, ...] = (
    FlightRadar24SensorEntityDescription(
        key="in_area",
        translation_key="in_area",
        icon="mdi:airplane-marker",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.flight.in_area_list),
        attributes=lambda coord: {'flights': coord.flight.in_area_list},
    ),
    FlightRadar24SensorEntityDescription(
        key="entered",
        translation_key="entered",
        icon="mdi:airplane-check",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.flight.entered_list),
        attributes=lambda coord: {'flights': coord.flight.entered_list},
    ),
    FlightRadar24SensorEntityDescription(
        key="exited",
        translation_key="exited",
        icon="mdi:airplane-remove",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.flight.exited_list),
        attributes=lambda coord: {'flights': coord.flight.exited_list},
    ),
    FlightRadar24SensorEntityDescription(
        key="most_tracked",
        translation_key="most_tracked",
        icon="mdi:airplane-search",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.flight.most_tracked_list) if coord.flight.most_tracked_list else None,
        attributes=lambda coord: {'flights': coord.flight.most_tracked_list if coord.flight.most_tracked_list else {}},
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_arrivals_on_time",
        translation_key="airport_arrivals_on_time",
        icon="mdi:airplane-check",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: coord.airport.stats.arrivals_on_time if coord.airport.stats else None,
        attributes=None,
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_arrivals_delayed",
        translation_key="airport_arrivals_delayed",
        icon="mdi:airplane-alert",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: coord.airport.stats.arrivals_delayed if coord.airport.stats else None,
        attributes=None,
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_arrivals_delay_average",
        translation_key="airport_arrivals_delay_average",
        icon="mdi:airplane-clock",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: coord.airport.stats.arrivals_delay_average if coord.airport.stats else None,
        attributes=None,
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_arrivals_delay_index",
        translation_key="airport_arrivals_delay_index",
        icon="mdi:airplane-clock",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda coord: coord.airport.stats.arrivals_delay_index if coord.airport.stats else None,
        attributes=None,
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_arrivals_canceled",
        translation_key="airport_arrivals_canceled",
        icon="mdi:airplane-remove",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: coord.airport.stats.arrivals_canceled if coord.airport.stats else None,
        attributes=None,
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_arrivals",
        translation_key="airport_arrivals",
        icon="mdi:airplane-landing",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.airport.arrivals) if coord.airport.arrivals is not None else None,
        attributes=lambda coord: {'flights': coord.airport.arrivals} if coord.airport.arrivals is not None else None,
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_departures_on_time",
        translation_key="airport_departures_on_time",
        icon="mdi:airplane-check",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: coord.airport.stats.departures_on_time if coord.airport.stats else None,
        attributes=None,
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_departures_delayed",
        translation_key="airport_departures_delayed",
        icon="mdi:airplane-alert",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: coord.airport.stats.departures_delayed if coord.airport.stats else None,
        attributes=None,
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_departures_delay_average",
        translation_key="airport_departures_delay_average",
        icon="mdi:airplane-clock",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: coord.airport.stats.departures_delay_average if coord.airport.stats else None,
        attributes=None,
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_departures_delay_index",
        translation_key="airport_departures_delay_index",
        icon="mdi:airplane-clock",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda coord: coord.airport.stats.departures_delay_index if coord.airport.stats else None,
        attributes=None,
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_departures_canceled",
        translation_key="airport_departures_canceled",
        icon="mdi:airplane-remove",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: coord.airport.stats.departures_canceled if coord.airport.stats else None,
        attributes=None,
    ),
    FlightRadar24SensorEntityDescription(
        key="airport_departures",
        translation_key="airport_departures",
        icon="mdi:airplane-takeoff",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.airport.departures) if coord.airport.departures is not None else None,
        attributes=lambda coord: ({'flights': coord.airport.departures}
                                  if coord.airport.departures is not None else None),
    ),
    FlightRadar24SensorEntityDescription(
        key="helicopters_in_area",
        translation_key="helicopters_in_area",
        icon="mdi:helicopter",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len([f for f in coord.flight.in_area_list if is_helicopter(f)]),
        attributes=lambda coord: {'flights': [f for f in coord.flight.in_area_list if is_helicopter(f)]},
    ),
)

RESTORE_SENSOR_TYPES: tuple[FlightRadar24SensorEntityDescription, ...] = (
    FlightRadar24SensorEntityDescription(
        key="additional_tracked",
        translation_key="additional_tracked",
        icon="mdi:airplane",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.flight.tracked_list),
        attributes=lambda coord: {'flights': coord.flight.tracked_list},
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []

    for description in SENSOR_TYPES:
        sensors.append(FlightRadar24Sensor(coordinator, description))
    for description in RESTORE_SENSOR_TYPES:
        sensors.append(FlightRadar24RestoreSensor(coordinator, description))
    async_add_entities(sensors, False)


class FlightRadar24Sensor(CoordinatorEntity[FlightRadar24Coordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: FlightRadar24SensorEntityDescription

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            description: FlightRadar24SensorEntityDescription,
    ) -> None:
        """Initialize."""
        # Assign the description before initializing the base classes
        self.entity_description = description
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}_{DOMAIN}_{description.key}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.entity_description.value(self.coordinator)
        if self.entity_description.attributes and self.entity_description.attributes(self.coordinator) is not None:
            new_attributes = copy.deepcopy(self.entity_description.attributes(self.coordinator))
            new_attributes["last_updated"] = datetime.datetime.now().isoformat()
            self._attr_extra_state_attributes = new_attributes
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.entity_description.value(self.coordinator) is not None


class FlightRadar24RestoreSensor(FlightRadar24Sensor, RestoreSensor):
    async def async_added_to_hass(self):
        """Restore state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state:
            tracked = {}
            for flight in last_state.attributes.get('flights', {}):
                tracked[flight.get('id') or flight.get('flight_number') or flight.get('callsign')] = flight
            self.coordinator.flight.set_tracked(tracked)
