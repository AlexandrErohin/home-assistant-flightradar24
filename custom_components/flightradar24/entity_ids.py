from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import async_generate_entity_id

from .const import STABLE_ENTITY_OBJECT_IDS


def suggest_entity_id(hass: HomeAssistant, entity_id_format: str, key: str) -> str:
    """Return a unique entity_id based on the stable English object_id for *key*."""
    return async_generate_entity_id(
        entity_id_format,
        STABLE_ENTITY_OBJECT_IDS[key],
        hass=hass,
    )
