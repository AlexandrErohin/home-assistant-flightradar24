"""Gate / landed event lifecycle for tracked flights (#276, #315)."""

from unittest.mock import MagicMock, patch

from FlightRadarAPI import Entity

from custom_components.flightradar24.api.event import EventManager
from custom_components.flightradar24.api.flight import FlightProcessor
from custom_components.flightradar24.const import (
    EVENT_TRACKED_ARRIVED_GATE,
    EVENT_TRACKED_LANDED,
    EVENT_TRACKED_LEFT_GATE,
)


def make_processor(auto_cleanup: bool = False) -> FlightProcessor:
    return FlightProcessor(
        client=MagicMock(),
        event_manager=EventManager(),
        min_altitude=-1,
        max_altitude=100000,
        point=Entity(0, 0),
        bounds='1,-1,-1,1',
        auto_cleanup=auto_cleanup,
    )


def event_names(processor: FlightProcessor) -> list[str]:
    return [event.event for event in processor._event_manager._events]


def live_flight(**overrides) -> dict:
    base = {
        'id': '4257d6bf',
        'flight_number': 'SQ327',
        'callsign': 'SIA327',
        'aircraft_registration': '9V-SWB',
        'tracked_by': 'flight_number',
        'tracked_type': 'live',
        'on_ground': 1,
        'was_airborne': True,
        'has_landed': True,
        'landed_event_sent': True,
        'gate_arrived_sent': False,
        'time_real_arrival': 1_700_000_000,
        'latitude': 1.0,
        'longitude': 1.0,
        'altitude': 0,
    }
    base.update(overrides)
    return base


def test_time_real_arrival_alone_is_arrival_evidence():
    """Restart / track-after-landing: airline timestamp without was_airborne."""
    flight = live_flight(
        was_airborne=False,
        has_landed=False,
        landed_event_sent=False,
        require_airborne_for_arrival=False,
    )
    assert FlightProcessor._has_arrived_evidence(flight)


def test_sticky_time_real_arrival_after_left_gate_reset_is_ignored():
    """After left_gate, FR24 may keep the old arrival time until airborne again."""
    flight = live_flight(
        was_airborne=False,
        has_landed=False,
        landed_event_sent=False,
        require_airborne_for_arrival=True,
    )
    assert not FlightProcessor._has_arrived_evidence(flight)


def test_time_real_arrival_after_airborne_is_arrival_evidence():
    flight = live_flight(
        has_landed=False,
        landed_event_sent=False,
        require_airborne_for_arrival=True,
    )
    assert FlightProcessor._has_arrived_evidence(flight)


def test_left_gate_sets_require_airborne_for_arrival():
    processor = make_processor()
    flight = live_flight(
        was_airborne=False,
        has_landed=False,
        landed_event_sent=False,
        gate_arrived_sent=False,
        time_real_arrival=1_700_000_000,
        require_airborne_for_arrival=False,
    )
    processor._maybe_fire_left_gate('schedule', flight)
    assert flight['require_airborne_for_arrival'] is True
    assert not FlightProcessor._has_arrived_evidence(flight)


def test_left_gate_blocked_after_arrival_completed():
    processor = make_processor()
    flight = live_flight(gate_arrived_sent=True, has_landed=True)
    processor._maybe_fire_left_gate('aircraft', flight)
    assert event_names(processor) == []
    assert flight['gate_arrived_sent'] is True


def test_left_gate_fires_on_real_departure():
    processor = make_processor()
    flight = live_flight(
        was_airborne=False,
        has_landed=False,
        landed_event_sent=False,
        gate_arrived_sent=False,
        time_real_arrival=None,
        on_ground=1,
    )
    processor._maybe_fire_left_gate('schedule', flight)
    assert event_names(processor) == [EVENT_TRACKED_LEFT_GATE]
    assert flight['gate_arrived_sent'] is False
    assert flight['has_landed'] is False
    assert flight['landed_event_sent'] is False


def test_arrival_fires_missed_landed_then_arrived_gate():
    """When on_ground edge was missed, arrived evidence still yields landed."""
    processor = make_processor()
    flight = live_flight(has_landed=False, landed_event_sent=False, gate_arrived_sent=False)
    processor._maybe_fire_arrival_events(flight)
    assert event_names(processor) == [EVENT_TRACKED_LANDED, EVENT_TRACKED_ARRIVED_GATE]
    assert flight['landed_event_sent'] is True
    assert flight['gate_arrived_sent'] is True
    assert flight['has_landed'] is True


def test_arrival_does_not_duplicate_landed_or_arrived():
    processor = make_processor()
    flight = live_flight(gate_arrived_sent=False, landed_event_sent=True)
    processor._maybe_fire_arrival_events(flight)
    processor._maybe_fire_arrival_events(flight)
    assert event_names(processor) == [EVENT_TRACKED_ARRIVED_GATE]


def test_post_arrival_live_flicker_does_not_repeat_gate_events():
    """SQ327-style: arrived, then same id briefly live again, then gone (#276)."""
    processor = make_processor()
    flight_id = '4257d6bf'
    registration = '9V-SWB'

    # Cycle 1: live flight missing from feed after landing evidence.
    processor._tracked[flight_id] = live_flight(
        landed_event_sent=True,
        gate_arrived_sent=False,
        tracked_by='aircraft_registration',
    )
    processor._client.get_flights.return_value = []
    processor.update_flights_tracked()
    assert event_names(processor) == [EVENT_TRACKED_ARRIVED_GATE]
    stub = processor._tracked[flight_id]
    assert stub['tracked_type'] == 'aircraft'
    assert stub['gate_arrived_sent'] is True
    assert stub['has_landed'] is True

    # Clear fired events; next cycles must stay quiet.
    processor._event_manager._events.clear()

    # Cycle 2: same FR24 id reappears briefly on the ground (parked ADS-B).
    live_obj = MagicMock(
        id=flight_id,
        registration=registration,
        on_ground=1,
        latitude=1.0,
        longitude=1.0,
        altitude=0,
        heading=0,
        ground_speed=0,
        squawk='0000',
        vertical_speed=0,
    )
    live_obj.get_distance_from.return_value = 1
    processor._client.get_flights.return_value = [live_obj]

    details = {
        'id': flight_id,
        'flight_number': 'SQ327',
        'callsign': 'SIA327',
        'aircraft_registration': registration,
        'time_real_arrival': 1_700_000_000,
        'on_ground': 1,
    }
    with patch.object(FlightProcessor, '_fetch_details', return_value=details):
        processor.update_flights_tracked()
    assert event_names(processor) == []
    assert processor._tracked[flight_id]['gate_arrived_sent'] is True

    processor._event_manager._events.clear()

    # Cycle 3: grace live_attempt
    processor._client.get_flights.return_value = []
    processor.update_flights_tracked()
    assert event_names(processor) == []

    # Cycle 4: still missing — must not fire arrived_gate again.
    processor.update_flights_tracked()
    assert event_names(processor) == []


def test_new_flight_id_for_same_registration_can_leave_gate():
    """A later segment (new FR24 id) must still get left_gate."""
    processor = make_processor()
    old_id = 'oldseg'
    new_id = 'newseg'
    registration = '9V-SWB'
    processor._tracked[old_id] = {
        'id': old_id,
        'aircraft_registration': registration,
        'tracked_by': 'aircraft_registration',
        'tracked_type': 'aircraft',
        'gate_arrived_sent': True,
        'has_landed': True,
        'landed_event_sent': True,
        'was_airborne': True,
        'on_ground': 1,
    }

    live_obj = MagicMock(
        id=new_id,
        registration=registration,
        number='SQ999',
        callsign='SIA999',
        on_ground=1,
        latitude=1.0,
        longitude=1.0,
        altitude=0,
        heading=0,
        ground_speed=0,
        squawk='0000',
        vertical_speed=0,
    )
    live_obj.get_distance_from.return_value = 1
    processor._client.get_flights.return_value = [live_obj]
    details = {
        'id': new_id,
        'aircraft_registration': registration,
        'flight_number': 'SQ999',
        'callsign': 'SIA999',
        'time_real_arrival': None,
        'on_ground': 1,
    }
    with patch.object(FlightProcessor, '_fetch_details', return_value=details):
        processor.update_flights_tracked()
    assert EVENT_TRACKED_LEFT_GATE in event_names(processor)
    assert old_id not in processor._tracked
    assert processor._tracked[new_id]['gate_arrived_sent'] is False


def test_flight_number_track_does_not_follow_airframe_to_next_sector():
    """SQ306 must not become SQ305 when the same REG turns around (#317)."""
    processor = make_processor()
    old_id = '41cceb13'
    new_id = '41cf5171'
    registration = '9V-SMK'
    processor._tracked[old_id] = live_flight(
        id=old_id,
        flight_number='SQ306',
        callsign='SIA306',
        aircraft_registration=registration,
        tracked_by='flight_number',
        tracked_type='live',
        was_airborne=True,
        has_landed=True,
        landed_event_sent=True,
        gate_arrived_sent=False,
        time_real_arrival=1_700_000_000,
        live_attempt=None,
    )
    processor._tracked[old_id].pop('live_attempt', None)

    live_obj = MagicMock(
        id=new_id,
        registration=registration,
        number='SQ305',
        callsign='SIA305',
        on_ground=1,
        latitude=51.46,
        longitude=-0.45,
        altitude=0,
        heading=270,
        ground_speed=18,
        squawk='',
        vertical_speed=0,
    )
    live_obj.get_distance_from.return_value = 1
    processor._client.get_flights.return_value = [live_obj]

    processor.update_flights_tracked()

    assert new_id not in processor._tracked
    assert old_id in processor._tracked
    tracked = processor._tracked[old_id]
    assert tracked['flight_number'] == 'SQ306'
    assert 'aircraft_registration' not in tracked
    assert EVENT_TRACKED_ARRIVED_GATE in event_names(processor)
    assert EVENT_TRACKED_LEFT_GATE not in event_names(processor)


def test_flight_number_track_allows_same_number_new_fr24_id():
    """Same service with a new FR24 id may still update by registration."""
    processor = make_processor()
    old_id = 'old306'
    new_id = 'new306'
    registration = '9V-SMK'
    processor._tracked[old_id] = {
        'id': old_id,
        'flight_number': 'SQ306',
        'callsign': 'SIA306',
        'aircraft_registration': registration,
        'tracked_by': 'flight_number',
        'tracked_type': 'live',
        'on_ground': 0,
        'was_airborne': True,
        'has_landed': False,
        'gate_arrived_sent': False,
        'landed_event_sent': False,
    }
    live_obj = MagicMock(
        id=new_id,
        registration=registration,
        number='SQ306',
        callsign='SIA306',
        on_ground=0,
        latitude=1.0,
        longitude=1.0,
        altitude=35000,
        heading=90,
        ground_speed=450,
        squawk='',
        vertical_speed=0,
    )
    live_obj.get_distance_from.return_value = 1
    processor._client.get_flights.return_value = [live_obj]
    details = {
        'id': new_id,
        'flight_number': 'SQ306',
        'callsign': 'SIA306',
        'aircraft_registration': registration,
        'on_ground': 0,
    }
    with patch.object(FlightProcessor, '_fetch_details', return_value=details):
        processor.update_flights_tracked()

    assert old_id not in processor._tracked
    assert processor._tracked[new_id]['flight_number'] == 'SQ306'
    assert processor._tracked[new_id]['tracked_by'] == 'flight_number'
