from __future__ import annotations
from typing import Any
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import FlightRadar24Coordinator


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FlightRadar24ScanEntity(coordinator)], False)


class FlightRadar24ScanEntity(
    CoordinatorEntity[FlightRadar24Coordinator], SwitchEntity
):
    entity_description: SwitchEntityDescription

    def __init__(self, coordinator: FlightRadar24Coordinator) -> None:
        super().__init__(coordinator)

        self._attr_device_info = coordinator.device_info
        self.entity_description = SwitchEntityDescription(
            key="scanning",
            name="API data fetching",
            icon="mdi:connection",
            entity_category=EntityCategory.CONFIG,
        )
        self._attr_unique_id = f"{coordinator.unique_id}_{DOMAIN}_{self.entity_description.key}"

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
        self.async_write_ha_state()
