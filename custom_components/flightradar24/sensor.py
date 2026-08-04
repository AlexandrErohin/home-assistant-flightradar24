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
from homeassistant.util import dt as dt_util
from .coordinator import FlightRadar24Coordinator


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
        attributes=lambda coord: {
            'flights': coord.flight.in_area_list,
            'bounds': coord.flight.bounds,
        },
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
        value=lambda coord: (
            len(coord.airport.departures)
            if coord.airport.departures is not None
            else None
        ),
        attributes=lambda coord: (
            {"flights": coord.airport.departures}
            if coord.airport.departures is not None
            else None
        ),
    ),
)

RESTORE_SENSOR_TYPES: tuple[FlightRadar24SensorEntityDescription, ...] = (
    FlightRadar24SensorEntityDescription(
        key="additional_tracked",
        translation_key="additional_tracked",
        icon="mdi:airplane",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.flight.tracked_list),
        attributes=lambda coord: {"flights": coord.flight.tracked_list},
    ),
)


# Sensors that have no source at all until an airport is tracked - the only
# ones that legitimately report `unavailable`.
AIRPORT_KEYS = frozenset(
    description.key for description in SENSOR_TYPES if description.key.startswith("airport_")
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    sensors = []
    for description in SENSOR_TYPES:
        sensors.append(FlightRadar24Sensor(coordinator, description, entry.entry_id))
    for description in RESTORE_SENSOR_TYPES:
        sensors.append(FlightRadar24RestoreSensor(coordinator, description, entry.entry_id))
    async_add_entities(sensors, False)


class FlightRadar24Sensor(CoordinatorEntity[FlightRadar24Coordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: FlightRadar24SensorEntityDescription

    # TELL THE RECORDER TO IGNORE THE MASSIVE FLIGHTS ARRAY
    _unrecorded_attributes = frozenset({"flights"})

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            description: FlightRadar24SensorEntityDescription,
            entry_id: str,
    ) -> None:
        """Initialize."""
        self.entity_description = description
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{entry_id}_{DOMAIN}_{description.key}"
        self._attr_native_value = self.entity_description.value(coordinator)
        # Publish static attributes (e.g. bounds) immediately so Lovelace cards
        # can render the map before the first refresh finishes.
        if self.entity_description.attributes is not None:
            attributes = self.entity_description.attributes(coordinator)
            if attributes is not None:
                self._attr_extra_state_attributes = {
                    key: [dict(item) for item in value] if isinstance(value, list) else value
                    for key, value in attributes.items()
                }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.entity_description.value(self.coordinator)
        if self.entity_description.attributes is not None:
            attributes = self.entity_description.attributes(self.coordinator)
            if attributes is not None:
                # The coordinator keeps mutating these flight dicts in place, so
                # they have to be copied - but they are flat and there can be
                # hundreds of them, so deep-copying every cycle only stalls the
                # event loop for nothing.
                self._attr_extra_state_attributes = {
                    key: [dict(item) for item in value] if isinstance(value, list) else value
                    for key, value in attributes.items()
                }
                self._attr_extra_state_attributes["last_updated"] = dt_util.now().isoformat()
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Report unavailable only when this sensor has no source to read from.

        A value that simply has not been fetched yet is `unknown`, not
        `unavailable` - tying availability to the value being set is what took
        every sensor offline after a restart until the first cycle landed.
        """
        if self.entity_description.key in AIRPORT_KEYS:
            # The tracked airport is restored by the text entity, which may land
            # after this platform. A restored value is proof enough that one was
            # tracked; it is cleared again on the first cycle without an airport.
            return bool(self.coordinator.airport.code) or self._attr_native_value is not None
        if self.entity_description.key == "most_tracked":
            return self.coordinator.flight.most_tracked_enabled
        return True


class FlightRadar24RestoreSensor(FlightRadar24Sensor, RestoreSensor):

    # WE MUST RECORD THIS SPECIFIC SENSOR TO RESTORE TRACKED FLIGHTS ON REBOOT
    _unrecorded_attributes = frozenset()

    async def async_added_to_hass(self):
        """Restore state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state:
            tracked = {}
            for flight in last_state.attributes.get('flights', {}):
                tracked[flight.get('id') or flight.get('flight_number') or flight.get('callsign')] = flight
            self.coordinator.flight.set_tracked(tracked)
            self._attr_native_value = self.entity_description.value(self.coordinator)
            self.async_write_ha_state()
