import logging
from collections import deque
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

_LOGGER = logging.getLogger(__name__)


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

    # Use a queue to ensure that sensors get properly rotated (as little shared route trace as possible on map)
    slot_queue = deque()
    hass.data[DOMAIN]["slot_queue"] = slot_queue

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

        if not flight:
            _LOGGER.debug(f"Sensor {index} init # Got no flight data -> add sensor to queue")
            self.coordinator.hass.data[DOMAIN].get("slot_queue").append(index)
        else:
            _LOGGER.debug(f"Sensor {index} init # Got data for flight {flight['id']}")

    @callback
    def _handle_coordinator_update(self) -> None:
        attached_to_a_flight = self._attr_extra_state_attributes['id'] is not None

        if attached_to_a_flight:
            flight_id = self._attr_extra_state_attributes['id']
            _LOGGER.debug(f"Sensor {self.index} update # Sensor previously attached to flight {flight_id}")

            flight = self.coordinator.tracked.get(flight_id)
            if flight is not None:
                _LOGGER.debug(f"Sensor {self.index} update # Attached flight {flight_id} is still tracked -> updating data")
                self.set_state_attributes(flight)
            else:
                _LOGGER.debug(f"Sensor {self.index} update # Attached flight {flight_id} is no longer tracked -> clearing data")
                attached_to_a_flight = False
                self.set_state_attributes(None)
        else:
            _LOGGER.debug(f"Sensor {self.index} update # Sensor previously not attached to any flight")

        if not attached_to_a_flight:
            slot_queue: deque = self.coordinator.hass.data[DOMAIN].get("slot_queue")

            if self.index not in slot_queue:
                _LOGGER.debug(f"Sensor {self.index} update # Currently not attached to any flight and sensor not yet in queue")
                if len(slot_queue) > 0:
                    _LOGGER.debug(f"Sensor {self.index} update # Queue not empty -> adding sensor to end of queue")
                    slot_queue.append(self.index)
                else:
                    _LOGGER.debug(f"Sensor {self.index} update # Queue is empty -> try to attach a flight directly")
                    attached_to_a_flight = self.update_flight_data()
                    if not attached_to_a_flight:
                        _LOGGER.debug(f"Sensor {self.index} update # No unattached flights found -> adding sensor to queue")
                        slot_queue.append(self.index)

            else:
                _LOGGER.debug(f"Sensor {self.index} update # Currently not attached to any flight and sensor already in queue")
                if slot_queue[0] is self.index:
                    _LOGGER.debug(f"Sensor {self.index} update # Sensor is first in queue ({slot_queue}) -> try to attach a flight")
                    attached_to_a_flight = self.update_flight_data()
                    if attached_to_a_flight:
                        _LOGGER.debug(f"Sensor {self.index} update # Sensor attached to flight {self._attr_extra_state_attributes['id']} -> leave queue")
                        slot_queue.popleft()
                    else:
                        _LOGGER.debug(f"Sensor {self.index} update # No unattached flights found -> stay in queue")
                else:
                    _LOGGER.debug(f"Sensor {self.index} update # Sensor is not first in queue ({slot_queue}) -> stay in queue and do nothing")

        self.async_write_ha_state()

    def update_flight_data(self):
        attached_to_a_flight = False
        flights_attached_to_sensors = []

        for i in range(10):
            flight_id = self.coordinator.hass.data[DOMAIN].get(f"fr24_map_entity_{i}")
            if flight_id is not None:
                flights_attached_to_sensors.append(flight_id)

        _LOGGER.debug(f"Sensor {self.index} update # Currently attached flights: {flights_attached_to_sensors}")

        for flight_id in self.coordinator.tracked:
            if flight_id not in flights_attached_to_sensors:
                _LOGGER.debug(f"Sensor {self.index} update # Flight {flight_id} is unattached -> attach to this sensor")
                self.set_state_attributes(self.coordinator.tracked[flight_id])
                attached_to_a_flight = True
                break

        return attached_to_a_flight

    def set_state_attributes(self, flight: dict[str, Any] | None):
        self._attr_extra_state_attributes['id'] = flight['id'] if flight else None
        self._attr_extra_state_attributes['latitude'] = str(flight['latitude']) if flight else None
        self._attr_extra_state_attributes['longitude'] = str(flight['longitude']) if flight else None
        self._attr_extra_state_attributes['altitude'] = flight['altitude'] if flight else None
        self._attr_extra_state_attributes['heading'] = flight['heading'] if flight else None
        self._attr_extra_state_attributes['ground_speed'] = flight['ground_speed'] if flight else None
        self._attr_extra_state_attributes['squawk'] = flight['squawk'] if flight else None
        self.coordinator.hass.data[DOMAIN][self._attr_unique_id] = flight['id'] if flight else None
        self._attr_native_value = f"{flight['flight_number']}✈" if flight else None
