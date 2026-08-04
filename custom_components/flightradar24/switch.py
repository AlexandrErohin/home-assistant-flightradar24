from __future__ import annotations
from typing import Any

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from homeassistant.util import dt as dt_util
from .coordinator import FlightRadar24Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [FlightRadar24ScanEntity(coordinator, entry.entry_id),
         FlightRadar24MostTrackedEntity(coordinator, entry.entry_id)],
        False,
    )


class FlightRadar24ScanEntity(
    CoordinatorEntity[FlightRadar24Coordinator],
    SwitchEntity,
    RestoreEntity,
):
    _attr_has_entity_name = True
    _attr_should_poll = False  # Отключаем опрос
    entity_description: SwitchEntityDescription

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            entry_id: str,
    ) -> None:
        super().__init__(coordinator)

        self._attr_device_info = coordinator.device_info

        self.entity_description = SwitchEntityDescription(
            key="scanning",
            translation_key="scanning",
            icon="mdi:connection",
            entity_category=EntityCategory.CONFIG,
        )

        # FIXED: Lock down the unique ID using the entry_id
        self._attr_unique_id = (
            f"{entry_id}_{DOMAIN}_{self.entity_description.key}"
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        if (state := await self.async_get_last_state()) is not None:
            self.coordinator.scanning = state.state == "on"
            if not self.coordinator.scanning:
                self._disable()
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self.coordinator.scanning

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        self.coordinator.scanning = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self.coordinator.scanning = False
        self._disable()
        self.async_write_ha_state()

    def _disable(self) -> None:
        self.coordinator.flight.clear_live_data()
        self.coordinator.airport.clear_live_data()
        self.coordinator.async_set_updated_data(None)


class FlightRadar24MostTrackedEntity(
    CoordinatorEntity[FlightRadar24Coordinator],
    SwitchEntity,
    RestoreEntity,
):
    _attr_has_entity_name = True
    _attr_should_poll = False  # Отключаем опрос
    entity_description: SwitchEntityDescription
    # TELL THE RECORDER TO IGNORE THE MASSIVE FLIGHTS ARRAY
    _unrecorded_attributes = frozenset({"flights"})

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            entry_id: str,
    ) -> None:
        super().__init__(coordinator)

        self._attr_device_info = coordinator.device_info
        self._attr_extra_state_attributes = {'flights': []}
        self.entity_description = SwitchEntityDescription(
            key="most_tracked",
            translation_key="most_tracked",
            icon="mdi:airplane-search",
        )
        self._attr_unique_id = (
            f"{entry_id}_{DOMAIN}_{self.entity_description.key}"
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if (state := await self.async_get_last_state()) is not None:
            if state.state == "on":
                self.coordinator.flight.enable_most_tracked()
                self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self.coordinator.flight.most_tracked_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.flight.enable_most_tracked()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.flight.disable_most_tracked()
        self._attr_extra_state_attributes = {'flights': []}
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.flight.most_tracked_enabled:
            self._attr_extra_state_attributes = {
                "flights": [dict(flight) for flight in self.coordinator.flight.most_tracked_list],
                "last_updated": dt_util.now().isoformat()
            }
            self.async_write_ha_state()
