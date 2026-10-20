"""Tests for when cached flight details are re-fetched."""

from time import time
from unittest.mock import MagicMock, patch

from FlightRadarAPI import Entity
import pytest

from custom_components.flightradar24.api.flight import FlightProcessor, FlightType


def make_processor() -> FlightProcessor:
    return FlightProcessor(
        client=MagicMock(),
        event_manager=MagicMock(),
        min_altitude=-1,
        max_altitude=100000,
        point=Entity(0, 0),
        bounds='1,-1,-1,1',
    )


def complete_details(age_minutes: float) -> dict:
    """Airline flight with every field the completeness check looks at."""
    return {
        'id': 'abc123',
        'flight_number': 'LY314',
        'aircraft_code': 'B738',
        'time_scheduled_departure': 1_000,
        'time_estimated_arrival': 2_000,
        'details_updated_at': time() - age_minutes * 60,
    }


@pytest.mark.parametrize('sensor_type', [FlightType.IN_AREA, None])
def test_complete_area_flight_details_are_reused(sensor_type):
    assert make_processor()._is_valid(complete_details(age_minutes=60), sensor_type)


def test_complete_tracked_flight_details_expire():
    """A tracked flight's ETA must not freeze at the value from take-off."""
    assert not make_processor()._is_valid(complete_details(age_minutes=60), FlightType.TRACKED)


def test_recent_tracked_flight_details_are_reused():
    assert make_processor()._is_valid(complete_details(age_minutes=1), FlightType.TRACKED)


def test_stale_tracked_flight_is_refetched_and_keeps_tracking_meta():
    processor = make_processor()
    previous = {
        **complete_details(age_minutes=60),
        'on_ground': 0,
        'tracked_by': 'flight_number',
        'tracked_type': 'live',
        'coordinates': [[1.0, 1.0]],
    }
    obj = MagicMock(id='abc123', on_ground=0, latitude=2.0, longitude=2.0)
    obj.get_distance_from.return_value = 10
    fresh = {**complete_details(age_minutes=0), 'time_estimated_arrival': 3_000}

    # FlightProcessor uses __slots__, so patch the method on the class
    with patch.object(FlightProcessor, '_fetch_details', return_value=fresh) as fetch:
        flight = processor._update_flights_data(obj, previous, FlightType.TRACKED)

    fetch.assert_called_once_with(obj)
    assert flight['time_estimated_arrival'] == 3_000
    assert flight['tracked_by'] == 'flight_number'
    assert flight['tracked_type'] == 'live'
    assert flight['coordinates'] == [[1.0, 1.0], [2.0, 2.0]]
