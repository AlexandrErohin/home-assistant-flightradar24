from dataclasses import dataclass
from logging import getLogger
from collections.abc import Callable
from typing import Any

from FlightRadarAPI import AirportNotFoundError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.components.text import (
    ENTITY_ID_FORMAT,
    TextEntity,
    TextEntityDescription,
    TextMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FlightRadar24Coordinator
from .entity_ids import suggest_entity_id

_LOGGER = getLogger(__name__)


@dataclass
class FlightRadar24TextRequiredKeys:
    method: Callable[[FlightRadar24Coordinator, str], Any]


@dataclass
class FlightRadar24TextEntityDescription(TextEntityDescription, FlightRadar24TextRequiredKeys):
    """A class that describes sensor entities."""


FLIGHT_SENSOR_TYPES: tuple[FlightRadar24TextEntityDescription, ...] = (
    FlightRadar24TextEntityDescription(
        key="add_track",
        translation_key="add_track",
        icon="mdi:airplane-plus",
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator, value: coordinator.add_flight_track(value),
    ),
    FlightRadar24TextEntityDescription(
        key="remove_track",
        translation_key="remove_track",
        icon="mdi:airplane-minus",
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator, value: coordinator.remove_flight_track(value),
    ),
)


AIRPORT_SENSOR_TYPES: tuple[FlightRadar24TextEntityDescription, ...] = (
    FlightRadar24TextEntityDescription(
        key="airport_track",
        translation_key="airport_track",
        icon="mdi:airport",
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator, value: coordinator.update_airport_track(value),
    ),
)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []

    for description in FLIGHT_SENSOR_TYPES:
        sensors.append(FlightRadar24TextFlight(coordinator, description))
    for description in AIRPORT_SENSOR_TYPES:
        sensors.append(FlightRadar24TextAirport(coordinator, description))
    async_add_entities(sensors, False)


class FlightRadar24TextFlight(
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
        self.entity_id = suggest_entity_id(coordinator.hass, ENTITY_ID_FORMAT, description.key)

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value
        await self.entity_description.method(self.coordinator, value)
        self._attr_native_value = ''
        self.async_write_ha_state()


class FlightRadar24TextAirport(
    CoordinatorEntity[FlightRadar24Coordinator], TextEntity, RestoreEntity
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
        self.entity_id = suggest_entity_id(coordinator.hass, ENTITY_ID_FORMAT, description.key)
        self._attr_mode = TextMode.TEXT
        self._attr_native_min = 0
        self._attr_native_max = 10

    async def async_set_value(self, value: str | None) -> None:
        if value is None:
            value = ""
        self._attr_native_value = value
        if not await self.entity_description.method(self.coordinator, value):
            # Unknown code or scanning off: keep showing the airport that is tracked.
            self._attr_native_value = self.coordinator.airport.code or ""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore last value; drop a code FR24 does not know."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in ("unknown", "unavailable", ""):
            return

        code = last_state.state
        self._attr_native_value = code
        if not self.coordinator.scanning:
            # Cannot validate offline; keep the soft restore used before (#362).
            self.coordinator.airport.restore_code(code)
            self.coordinator.async_update_listeners()
            return

        try:
            await self.coordinator.hass.async_add_executor_job(
                self.coordinator.airport.set_track, code)
        except AirportNotFoundError as err:
            # Persisted rejected code: do not retry it every airport refresh.
            self.coordinator.logger.error("FlightRadar24: %s", err)
            self._attr_native_value = ""
            self.async_write_ha_state()
            return
        except Exception as err:
            # Temporary failure (429, timeout, …): soft-restore for later refresh.
            self.coordinator.logger.error("FlightRadar24: %s", err)
            self.coordinator.airport.restore_code(code)
            self.coordinator.async_update_listeners()
            return

        self._attr_native_value = self.coordinator.airport.code or code
        self.coordinator.mark_airport_details_fresh()
        self.coordinator.async_update_listeners()
        self.async_write_ha_state()
