from dataclasses import dataclass
from collections.abc import Callable
from typing import Any
from homeassistant.components.sensor import (
    SensorStateClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, CONF_CREATE_MAP_ENTITIES
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import FlightRadar24Coordinator


@dataclass
class FlightRadar24SensorRequiredKeysMixin:
    value: Callable[[FlightRadar24Coordinator], Any]
    attributes: Callable[[FlightRadar24Coordinator], Any]


@dataclass
class TFlightRadar24SensorEntityDescription(SensorEntityDescription, FlightRadar24SensorRequiredKeysMixin):
    """A class that describes sensor entities."""


SENSOR_TYPES: tuple[TFlightRadar24SensorEntityDescription, ...] = (
    TFlightRadar24SensorEntityDescription(
        key="in_area",
        name="Current in area",
        icon="mdi:airplane",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.tracked) if coord.tracked is not None else 0,
        attributes=lambda coord: {'flights': [coord.tracked[x] for x in coord.tracked]},
    ),
    TFlightRadar24SensorEntityDescription(
        key="entered",
        name="Entered area",
        icon="mdi:airplane",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.entered),
        attributes=lambda coord: {'flights': coord.entered},
    ),
    TFlightRadar24SensorEntityDescription(
        key="exited",
        name="Exited area",
        icon="mdi:airplane",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.exited),
        attributes=lambda coord: {'flights': coord.exited},
    ),
)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FlightRadar24Coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []

    for description in SENSOR_TYPES:
        sensors.append(FlightRadar24Sensor(coordinator, description, coordinator.device_info))

    # Only show flights on map that have a flight number
    def filter_flight_codes(target: dict[str, Any]):
        return target.get('flight_number') is not None

    if entry.data.get(CONF_CREATE_MAP_ENTITIES) is True:
        flights = list(filter(filter_flight_codes, list(coordinator.tracked.values())))
        for index in range(10):
            flight = flights[index] if len(flights) > index else None
            sensors.append(FlightRadar24MapSensor(coordinator, flight, index))

    async_add_entities(sensors, False)


class FlightRadar24Sensor(
    CoordinatorEntity[FlightRadar24Coordinator], SensorEntity
):
    _attr_has_entity_name = True
    entity_description: TFlightRadar24SensorEntityDescription

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            description: TFlightRadar24SensorEntityDescription,
            device_info: DeviceInfo,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = description.key
        self.entity_description = description

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.entity_description.value(self.coordinator)
        self._attr_extra_state_attributes = self.entity_description.attributes(self.coordinator)
        self.async_write_ha_state()


class FlightRadar24MapSensor(
    CoordinatorEntity[FlightRadar24Coordinator], SensorEntity
):
    _attr_has_entity_name = True

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            flight: dict[str, Any] | None,
            index: int
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.index = index
        self.coordinator = coordinator
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"fr24_map_entity_{index}"
        self._attr_icon = "mdi:airplane"
        self._attr_name = f"Flight {index + 1}"
        self._attr_extra_state_attributes = {}
        self.set_state_attributes(flight)

    @callback
    def _handle_coordinator_update(self) -> None:
        flight_found = self._attr_extra_state_attributes['id'] is not None

        if flight_found:
            flight = self.coordinator.tracked.get(self._attr_extra_state_attributes['id'])
            if flight is not None:
                self.set_state_attributes(flight)
            else:
                flight_found = False

        if not flight_found:
            already_reserved_flights = []
            for i in range(10):
                flight = self.coordinator.hass.data[DOMAIN].get(f"fr24_map_entity_{i}")
                if flight is not None:
                    already_reserved_flights.append(flight['id'])

            for flight_id in self.coordinator.tracked:
                if flight_id not in already_reserved_flights:
                    self.set_state_attributes(self.coordinator.tracked[flight_id])
                    flight_found = True
                    break

            if not flight_found:
                self.set_state_attributes(None)

        self.async_write_ha_state()

    def set_state_attributes(self, flight: dict[str, Any] | None):
        self._attr_extra_state_attributes['id'] = flight['id'] if flight else None
        self._attr_extra_state_attributes['latitude'] = flight['latitude'] if flight else None
        self._attr_extra_state_attributes['longitude'] = flight['longitude'] if flight else None
        self._attr_extra_state_attributes['altitude'] = flight['altitude'] if flight else None
        self._attr_extra_state_attributes['heading'] = flight['heading'] if flight else None
        self._attr_extra_state_attributes['ground_speed'] = flight['ground_speed'] if flight else None
        self._attr_extra_state_attributes['squawk'] = flight['squawk'] if flight else None
        self.coordinator.hass.data[DOMAIN][self._attr_unique_id] = flight['id'] if flight else None
        self._attr_native_value = f"{flight['flight_number']}✈" if flight else None
