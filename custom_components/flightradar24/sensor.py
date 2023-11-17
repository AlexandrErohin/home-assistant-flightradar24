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
from .const import DOMAIN
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
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []

    for description in SENSOR_TYPES:
        sensors.append(FlightRadar24Sensor(coordinator, description, coordinator.device_info))
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
