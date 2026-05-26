from __future__ import annotations

from typing import Any

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FlightRadar24Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # --- DYNAMIC MIGRATION LOGIC FOR THE SWITCH ---
    ent_reg = er.async_get(hass)
    old_unique_id = f"{coordinator.unique_id}_{DOMAIN}_scanning"
    new_unique_id = f"{entry.entry_id}_{DOMAIN}_scanning"

    if entity_id := ent_reg.async_get_entity_id(
        "switch",
        DOMAIN,
        old_unique_id,
    ):
        # Bulletproof check: Only migrate if the new ID isn't already taken!
        if not ent_reg.async_get_entity_id(
            "switch",
            DOMAIN,
            new_unique_id,
        ):
            try:
                ent_reg.async_update_entity(
                    entity_id,
                    new_unique_id=new_unique_id,
                )
            except ValueError:
                pass
    # ----------------------------------------------

    async_add_entities(
        [FlightRadar24ScanEntity(coordinator, entry.entry_id)],
        False,
    )


class FlightRadar24ScanEntity(
    CoordinatorEntity[FlightRadar24Coordinator],
    SwitchEntity,
):
    _attr_has_entity_name = True
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

        self.coordinator.flight.clear_live_data()
        self.coordinator.airport.clear_live_data()

        self.coordinator.async_set_updated_data(None)

        self.async_write_ha_state()
