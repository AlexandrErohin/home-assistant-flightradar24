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
from homeassistant.helpers import entity_registry as er  # Imported for migration
from .coordinator import FlightRadar24Coordinator
from .flight_key import flight_display_name, flight_tracker_key
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


@callback
def _remove_bad_registry_entries(ent_reg: er.EntityRegistry) -> None:
    """Remove entities created with a non-serializable unique ID."""
    for entity_entry in list(ent_reg.entities.values()):
        if (
                entity_entry.domain == "sensor"
                and entity_entry.platform == DOMAIN
                and not isinstance(entity_entry.unique_id, str)
        ):
            ent_reg.async_remove(entity_entry.entity_id)


@callback
def _remove_stale_tracked_flight_entries(
        ent_reg: er.EntityRegistry,
        entry_id: str,
        current_keys: set[str],
) -> None:
    """Remove tracked-flight sensor registry entries no longer tracked."""
    prefix = f"{entry_id}_{DOMAIN}_tracked_flight_"
    for entity_entry in list(ent_reg.entities.values()):
        unique_id = entity_entry.unique_id
        if (
                entity_entry.domain == "sensor"
                and entity_entry.platform == DOMAIN
                and isinstance(unique_id, str)
                and unique_id.startswith(prefix)
                and unique_id.removeprefix(prefix) not in current_keys
        ):
            ent_reg.async_remove(entity_entry.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # --- DYNAMIC MIGRATION LOGIC TO PREVENT BREAKING CHANGES ---
    ent_reg = er.async_get(hass)
    _remove_bad_registry_entries(ent_reg)
    for description in SENSOR_TYPES + RESTORE_SENSOR_TYPES:
        old_unique_id = f"{coordinator.unique_id}_{DOMAIN}_{description.key}"
        new_unique_id = f"{entry.entry_id}_{DOMAIN}_{description.key}"
        if entity_id := ent_reg.async_get_entity_id("sensor", DOMAIN, old_unique_id):
            # Bulletproof check: Only migrate if the new ID isn't already taken!
            if not ent_reg.async_get_entity_id("sensor", DOMAIN, new_unique_id):
                try:
                    ent_reg.async_update_entity(entity_id, new_unique_id=new_unique_id)
                except ValueError:
                    pass
    # -----------------------------------------------------------

    sensors = []
    for description in SENSOR_TYPES:
        sensors.append(FlightRadar24Sensor(coordinator, description, entry.entry_id))
    for description in RESTORE_SENSOR_TYPES:
        sensors.append(FlightRadar24RestoreSensor(coordinator, description, entry.entry_id))
    async_add_entities(sensors, False)

    tracked_sensors: dict[str, FlightRadar24TrackedFlightSensor] = {}

    @callback
    def add_tracked_flight_sensors() -> None:
        """Add one sensor per additional tracked flight."""
        current_keys = {
            tracker_key
            for flight in coordinator.flight.tracked_list
            if (tracker_key := flight_tracker_key(flight))
        }
        _remove_stale_tracked_flight_entries(ent_reg, entry.entry_id, current_keys)
        for tracker_key in set(tracked_sensors) - current_keys:
            sensor = tracked_sensors.pop(tracker_key)
            if entity_id := ent_reg.async_get_entity_id(
                    "sensor",
                    DOMAIN,
                    FlightRadar24TrackedFlightSensor.make_unique_id(entry.entry_id, tracker_key),
            ):
                ent_reg.async_remove(entity_id)
            if sensor.hass is not None:
                hass.async_create_task(sensor.async_remove())

        new_entities: list[FlightRadar24TrackedFlightSensor] = []
        for flight in coordinator.flight.tracked_list:
            tracker_key = flight_tracker_key(flight)
            if not tracker_key or tracker_key in tracked_sensors:
                continue

            sensor = FlightRadar24TrackedFlightSensor(coordinator, entry.entry_id, tracker_key)
            tracked_sensors[tracker_key] = sensor
            new_entities.append(sensor)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(add_tracked_flight_sensors))
    add_tracked_flight_sensors()


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
            self.coordinator.async_set_updated_data(self.coordinator.data)


class FlightRadar24TrackedFlightSensor(CoordinatorEntity[FlightRadar24Coordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:airplane"
    _attr_state_class = SensorStateClass.TOTAL
    _unrecorded_attributes = frozenset({"flights", "flight"})

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            entry_id: str,
            tracker_key: str,
    ) -> None:
        self.tracker_key = tracker_key
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = self.make_unique_id(entry_id, tracker_key)

    @staticmethod
    def make_unique_id(entry_id: str, tracker_key: str) -> str:
        return f"{entry_id}_{DOMAIN}_tracked_flight_{tracker_key}"

    @property
    def flight(self) -> dict[str, Any]:
        for flight in self.coordinator.flight.tracked_list:
            if flight_tracker_key(flight) == self.tracker_key:
                return flight
        return {}

    @property
    def name(self) -> str:
        flight = self.flight
        if flight:
            return f"Tracked flight {flight_display_name(flight)}"
        return "Tracked flight"

    @property
    def native_value(self) -> int | None:
        flight = self.flight
        if not flight:
            return None
        return 1

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        flight = copy.deepcopy(self.flight)
        if not flight:
            return {"flights": [], "last_updated": datetime.datetime.now().isoformat()}
        return {
            "flights": [flight],
            "flight": flight,
            "tracked_type": flight.get("tracked_type"),
            "last_updated": datetime.datetime.now().isoformat(),
        }

    @property
    def available(self) -> bool:
        return bool(self.flight)
