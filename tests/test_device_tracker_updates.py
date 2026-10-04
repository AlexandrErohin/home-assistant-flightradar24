"""Tracker regressions using Home Assistant's real coordinator and state writer."""

import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.entity_component import EntityComponent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flightradar24.device_tracker import FlightRadar24Tracker


@pytest.mark.asyncio
@pytest.mark.parametrize("seed_update", [False, True])
async def test_tracker_initial_state_duplicates_and_availability(
    hass, seed_update
):
    entry = MockConfigEntry(domain="flightradar24", data={})
    entry.add_to_hass(hass)
    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), name="tracker", config_entry=entry
    )
    flight = {
        "id": "one", "tracked_type": "live", "latitude": 10, "longitude": 20
    }
    coordinator.flight = SimpleNamespace(tracked={"one": flight})
    coordinator.enable_tracker = True
    coordinator.unique_id = "test"
    coordinator.async_set_updated_data({})
    tracker = FlightRadar24Tracker(coordinator)
    tracker.entity_id = "device_tracker.flight"
    component = EntityComponent(
        logging.getLogger(__name__), "device_tracker", hass, timedelta(seconds=30)
    )
    await component.async_add_entities([tracker])
    if seed_update:
        coordinator.async_update_listeners()
    initial = hass.states.get(tracker.entity_id)
    assert initial.attributes["latitude"] == 10

    coordinator.async_update_listeners()
    coordinator.async_update_listeners()
    assert hass.states.get(tracker.entity_id) is initial

    flight["latitude"] = 11
    coordinator.async_update_listeners()
    assert hass.states.get(tracker.entity_id).attributes["latitude"] == 11

    coordinator.async_set_update_error(UpdateFailed("offline"))
    assert hass.states.get(tracker.entity_id).state == "unavailable"
    coordinator.async_set_updated_data({})
    assert hass.states.get(tracker.entity_id).state != "unavailable"
    assert hass.states.get(tracker.entity_id).attributes["latitude"] == 11

    coordinator.flight.tracked.clear()
    coordinator.async_update_listeners()
    assert "latitude" not in hass.states.get(tracker.entity_id).attributes
    await component.async_remove_entity(tracker.entity_id)
