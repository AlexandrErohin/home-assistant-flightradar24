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
from .const import DOMAIN
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import FlightRadar24Coordinator


@dataclass
class FlightRadar24SensorRequiredKeysMixin:
    value: Callable[[FlightRadar24Coordinator], Any]
    attributes: Callable[[FlightRadar24Coordinator], Any]


@dataclass
class FlightRadar24SensorEntityDescription(SensorEntityDescription, FlightRadar24SensorRequiredKeysMixin):
    """A class that describes sensor entities."""


SENSOR_TYPES: tuple[FlightRadar24SensorEntityDescription, ...] = (
    FlightRadar24SensorEntityDescription(
        key="in_area",
        name="Current in area",
        icon="mdi:airplane",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.in_area) if coord.in_area is not None else 0,
        attributes=lambda coord: {'flights': [coord.in_area[x] for x in coord.in_area] if coord.in_area else {}},
    ),
    FlightRadar24SensorEntityDescription(
        key="entered",
        name="Entered area",
        icon="mdi:airplane",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.entered),
        attributes=lambda coord: {'flights': coord.entered},
    ),
    FlightRadar24SensorEntityDescription(
        key="exited",
        name="Exited area",
        icon="mdi:airplane",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.exited),
        attributes=lambda coord: {'flights': coord.exited},
    ),
    FlightRadar24SensorEntityDescription(
        key="tracked",
        name="Additional tracked",
        icon="mdi:airplane",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.tracked) if coord.tracked is not None else 0,
        attributes=lambda coord: {'flights': [coord.tracked[x] for x in coord.tracked] if coord.tracked else {}},
    ),
    FlightRadar24SensorEntityDescription(
        key="most_tracked",
        name="Most tracked",
        icon="mdi:airplane",
        state_class=SensorStateClass.TOTAL,
        value=lambda coord: len(coord.most_tracked) if coord.most_tracked is not None else None,
        attributes=lambda coord: {
            'flights': [coord.most_tracked[x] for x in coord.most_tracked] if coord.most_tracked else {}},
    ),
)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []

    for description in SENSOR_TYPES:
        sensors.append(FlightRadar24Sensor(coordinator, description))
    async_add_entities(sensors, False)


class FlightRadar24Sensor(
    CoordinatorEntity[FlightRadar24Coordinator], SensorEntity
):
    _attr_has_entity_name = True
    entity_description: FlightRadar24SensorEntityDescription

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            description: FlightRadar24SensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}_{DOMAIN}_{description.key}"
        self.entity_description = description

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.entity_description.value(self.coordinator)
        self._attr_extra_state_attributes = {'flights': {}}
        self.async_write_ha_state()
        self._attr_extra_state_attributes = self.entity_description.attributes(self.coordinator)
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.entity_description.value(self.coordinator) is not None
