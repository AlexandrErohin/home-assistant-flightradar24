from dataclasses import dataclass
from logging import getLogger
from collections.abc import Callable
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import FlightRadar24Coordinator

_LOGGER = getLogger(__name__)


@dataclass
class FlightRadar24TextRequiredKeys:
    method: Callable[[FlightRadar24Coordinator, str], Any]


@dataclass
class FlightRadar24TextEntityDescription(TextEntityDescription, FlightRadar24TextRequiredKeys):
    """A class that describes sensor entities."""


SENSOR_TYPES: tuple[FlightRadar24TextEntityDescription, ...] = (
    FlightRadar24TextEntityDescription(
        key="add_track",
        name="Add to track",
        icon="mdi:airplane-plus",
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator, value: coordinator.add_track(value),
    ),
    FlightRadar24TextEntityDescription(
        key="remove_track",
        name="Remove from track",
        icon="mdi:airplane-minus",
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator, value: coordinator.remove_track(value),
    ),
)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []

    for description in SENSOR_TYPES:
        sensors.append(FlightRadar24Text(coordinator, description))
    async_add_entities(sensors, False)


class FlightRadar24Text(
    CoordinatorEntity[FlightRadar24Coordinator], TextEntity
):
    _attr_has_entity_name = True
    entity_description: FlightRadar24TextEntityDescription

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            description: FlightRadar24TextEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self._attr_native_value = ''
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}_{DOMAIN}_{description.key}"
        self.entity_description = description

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value
        await self.entity_description.method(self.coordinator, value)
        self.async_write_ha_state()
        self._attr_native_value = ''
