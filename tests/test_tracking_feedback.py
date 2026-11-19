"""Immediate feedback for changes to the additional tracked flights."""

from logging import getLogger
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from FlightRadarAPI import Entity
import pytest

from custom_components.flightradar24.const import EVENT_TRACKED_LEFT_GATE
from custom_components.flightradar24.coordinator import FlightRadar24Coordinator
from custom_components.flightradar24.sensor import (
    FlightRadar24RestoreSensor,
    RESTORE_SENSOR_TYPES,
)
from custom_components.flightradar24.text import (
    AIRPORT_SENSOR_TYPES,
    FLIGHT_SENSOR_TYPES,
    FlightRadar24TextAirport,
    FlightRadar24TextFlight,
)


@pytest.fixture
def coordinator(hass):
    """Create a coordinator without making external API requests."""
    return FlightRadar24Coordinator(
        hass=hass,
        bounds="1,-1,-1,1",
        client=MagicMock(),
        update_interval=20,
        logger=getLogger(__name__),
        unique_id="test_tracking_feedback",
        min_altitude=-1,
        max_altitude=100000,
        point=Entity(0, 0),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["add_flight_track", "remove_flight_track"])
async def test_tracking_change_updates_sensor_before_next_poll(coordinator, operation):
    """The tracked sensor receives the new count and attributes immediately."""
    flight = {"id": "test-flight", "flight_number": "TEST123"}
    removing = operation == "remove_flight_track"
    if removing:
        coordinator.flight.set_tracked({flight["id"]: flight})
    sensor = FlightRadar24RestoreSensor(coordinator, RESTORE_SENSOR_TYPES[0], "test-entry")
    writes = []
    sensor.async_write_ha_state = Mock(side_effect=lambda: writes.append(
        (sensor.native_value, sensor.extra_state_attributes["flights"])
    ))
    remove_listener = coordinator.async_add_listener(sensor._handle_coordinator_update)

    try:
        with patch(
            "custom_components.flightradar24.api.flight.FlightProcessor._find_flight",
            return_value=flight,
        ):
            await getattr(coordinator, operation)("TEST123")

        expected_flights = [] if removing else [flight]
        assert writes == [(len(expected_flights), expected_flights)]
    finally:
        remove_listener()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["add_flight_track", "remove_flight_track"])
async def test_tracking_no_match_does_not_notify_listeners(coordinator, operation):
    """An unsuccessful lookup does not publish an unchanged tracked list."""
    listener = Mock()
    remove_listener = coordinator.async_add_listener(listener)
    try:
        with patch(
            "custom_components.flightradar24.api.flight.FlightProcessor._find_flight",
            return_value=None,
        ):
            await getattr(coordinator, operation)("TEST123")

        listener.assert_not_called()
        assert coordinator.flight.tracked_list == []
    finally:
        remove_listener()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["add_flight_track", "remove_flight_track"])
async def test_tracking_respects_disabled_scanning(coordinator, operation):
    """A disabled coordinator must neither perform the lookup nor notify."""
    coordinator.scanning = False
    listener = Mock()
    remove_listener = coordinator.async_add_listener(listener)
    try:
        with patch.object(coordinator.hass, "async_add_executor_job", new_callable=AsyncMock) as executor:
            await getattr(coordinator, operation)("TEST123")

        executor.assert_not_awaited()
        listener.assert_not_called()
    finally:
        remove_listener()


@pytest.mark.asyncio
async def test_failed_tracking_lookup_does_not_notify_listeners(coordinator):
    """A failed API lookup must not publish a successful data update."""
    listener = Mock()
    remove_listener = coordinator.async_add_listener(listener)
    try:
        with patch(
            "custom_components.flightradar24.api.flight.FlightProcessor._find_flight",
            side_effect=RuntimeError("Test lookup failure"),
        ):
            await coordinator.add_flight_track("TEST123")

        listener.assert_not_called()
    finally:
        remove_listener()


LIVE_SEARCH = {
    "live": [{
        "id": "3c1a2b3d",
        "detail": {"flight": "EY223", "callsign": "ETD223", "reg": "A6-TST", "lat": 0.5, "lon": 0.5},
    }],
}


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", ["rate_limited", "cooldown"])
async def test_add_airborne_flight_while_details_are_unavailable(coordinator, caplog, unavailable):
    """A live search hit is still tracked when get_flight_details fails (#357)."""
    client = coordinator.flight._client
    client.search.return_value = LIVE_SEARCH
    client.get_flight_details.side_effect = RuntimeError("HTTP Error 429")
    listener = Mock()
    remove_listener = coordinator.async_add_listener(listener)
    try:
        with patch(
            "custom_components.flightradar24.api.flight.endpoint_in_cooldown",
            return_value=unavailable == "cooldown",
        ):
            await coordinator.add_flight_track("EY223")

        listener.assert_called_once()
        assert "No flight found" not in caplog.text
        [tracked] = coordinator.flight.tracked_list
        assert tracked["id"] == "3c1a2b3d"
        assert tracked["flight_number"] == "EY223"
        assert tracked["callsign"] == "ETD223"
        assert tracked["tracked_type"] == "live"
        assert tracked["tracked_by"] == "flight_number"
        assert "aircraft_registration" not in tracked or tracked.get(
            "aircraft_registration") in (None, "")
    finally:
        remove_listener()


@pytest.mark.asyncio
async def test_flight_added_without_details_becomes_live_later(coordinator):
    """Once details work again the next tracked update promotes it to live."""
    client = coordinator.flight._client
    client.search.return_value = LIVE_SEARCH
    with patch(
        "custom_components.flightradar24.api.flight.FlightProcessor._fetch_details",
        return_value=None,
    ):
        await coordinator.add_flight_track("EY223")

    details = {"id": "3c1a2b3d", "flight_number": "EY223", "callsign": "ETD223", "aircraft_code": "B789"}
    with patch(
        "custom_components.flightradar24.api.flight.FlightProcessor._fetch_details",
        return_value=details,
    ):
        coordinator.flight.update_flights_tracked()

    [tracked] = coordinator.flight.tracked_list
    assert tracked["id"] == "3c1a2b3d"
    assert tracked["tracked_type"] == "live"
    assert tracked["tracked_by"] == "flight_number"
    assert tracked["aircraft_code"] == "B789"
    events = [e.event for e in coordinator.flight._event_manager._events]
    assert EVENT_TRACKED_LEFT_GATE not in events


@pytest.mark.asyncio
@pytest.mark.parametrize("description", FLIGHT_SENSOR_TYPES, ids=lambda description: description.key)
async def test_flight_text_publishes_cleared_input(coordinator, description):
    """The final state write must contain the cleared input, not the flight number."""
    coordinator.add_flight_track = AsyncMock()
    coordinator.remove_flight_track = AsyncMock()
    entity = FlightRadar24TextFlight(coordinator, description)
    writes = []
    entity.async_write_ha_state = Mock(side_effect=lambda: writes.append(entity.native_value))

    await entity.async_set_value("TEST123")

    method = coordinator.add_flight_track if description.key == "add_track" else coordinator.remove_flight_track
    method.assert_awaited_once_with("TEST123")
    assert writes == [""]
    assert entity.native_value == ""


@pytest.mark.asyncio
async def test_airport_text_keeps_selected_code(coordinator):
    """Only the one-shot flight inputs should be cleared after submission."""
    coordinator.update_airport_track = AsyncMock()
    entity = FlightRadar24TextAirport(coordinator, AIRPORT_SENSOR_TYPES[0])
    writes = []
    entity.async_write_ha_state = Mock(side_effect=lambda: writes.append(entity.native_value))

    await entity.async_set_value("TEST")

    coordinator.update_airport_track.assert_awaited_once_with("TEST")
    assert writes == ["TEST"]
    assert entity.native_value == "TEST"
