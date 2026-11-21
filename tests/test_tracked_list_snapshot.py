"""Regression tests for #317 - the exposed tracked-flights list must not change by itself.

The ``additional_tracked`` sensor publishes ``coordinator.flight.tracked_list``
as its ``flights`` attribute.  If that property (or the sensor attribute dict)
hands out the coordinator's live flight dicts, the next coordinator refresh
mutates them in place and the already-published attribute list changes without
any user action (e.g. SQ306 "becoming" SQ305 on the same airframe).
"""

from copy import deepcopy
from time import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from FlightRadarAPI import Entity

from custom_components.flightradar24.api.event import EventManager
from custom_components.flightradar24.api.flight import FlightProcessor


def make_processor() -> FlightProcessor:
    return FlightProcessor(
        client=MagicMock(),
        event_manager=EventManager(),
        min_altitude=-1,
        max_altitude=100000,
        point=Entity(0, 0),
        bounds='1,-1,-1,1',
    )


class FeedFlight:
    """Minimal stand-in for FlightRadarAPI.Flight as returned by get_flights()."""

    def __init__(self, flight_id, registration=None, number=None, callsign=None, on_ground=1,
                 latitude=51.48, longitude=-0.46):
        self.id = flight_id
        self.registration = registration
        self.number = number
        self.callsign = callsign
        self.flight_number = number
        self.on_ground = on_ground
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = 0
        self.heading = 270
        self.ground_speed = 15
        self.squawk = ''
        self.vertical_speed = 0
        self.icao_24bit = '76CDAB'

    def get_distance_from(self, point) -> float:
        return 200.0


def tracked_flight(**overrides) -> dict:
    """A live tracked flight as stored in FlightProcessor._tracked (#317 SQ306)."""
    base = {
        'id': '41cceb13',
        'flight_number': 'SQ306',
        'callsign': 'SIA306',
        'aircraft_registration': '9V-SMK',
        'tracked_by': 'flight_number',
        'tracked_type': 'live',
        'live_attempt': 1,
        'on_ground': 1,
        'was_airborne': True,
        'has_landed': True,
        'gate_arrived_sent': True,
        'landed_event_sent': True,
        'latitude': 51.47,
        'longitude': -0.45,
        'altitude': 0,
        'ground_speed': 12,
        'details_updated_at': time(),
        'coordinates': [[51.47, -0.45]],
    }
    base.update(overrides)
    return base


def test_tracked_list_snapshot_survives_live_refresh():
    """A live refresh must not mutate the previously exposed tracked list.

    The refresh still updates the stored flight (new position), but the list
    that was exposed to the sensor before the refresh has to stay as it was.
    """
    processor = make_processor()
    processor.set_tracked({'41cceb13': tracked_flight()})
    processor._client.get_flights.return_value = [
        FeedFlight('41cceb13', registration='9V-SMK', number='SQ306', callsign='SIA306'),
    ]

    exposed = processor.tracked_list  # what the sensor publishes as `flights`
    snapshot = deepcopy(exposed)

    processor.update_flights_tracked()  # coordinator refresh

    assert exposed == snapshot
    # ... while the coordinator's own state did move on
    assert processor.tracked_list[0]['latitude'] == 51.48


def test_tracked_list_snapshot_survives_feed_miss():
    """A feed miss must not mutate the previously exposed tracked list.

    _on_tracked_live_missing used to `del flight['live_attempt']` on the stored
    dict - the same object the exposed list still referenced.
    """
    processor = make_processor()
    processor.set_tracked({'41cceb13': tracked_flight()})
    processor._client.get_flights.return_value = []

    exposed = processor.tracked_list
    snapshot = deepcopy(exposed)

    processor.update_flights_tracked()

    assert exposed == snapshot


def test_tracked_list_items_are_not_the_stored_dicts():
    """tracked_list must hand out copies, not the coordinator's live dicts."""
    processor = make_processor()
    stored = tracked_flight()
    processor.set_tracked({'41cceb13': stored})

    exposed = processor.tracked_list

    assert exposed[0] == stored
    assert exposed[0] is not stored


def test_sensor_attribute_list_is_a_snapshot_across_refresh():
    """The additional_tracked sensor's `flights` attribute must be stable.

    Build the real sensor attribute dict, run a coordinator refresh, and
    assert the published dict did not change underneath the user.
    """
    from custom_components.flightradar24.sensor import FlightRadar24RestoreSensor

    processor = make_processor()
    processor.set_tracked({'41cceb13': tracked_flight()})
    processor._client.get_flights.return_value = []

    sensor = FlightRadar24RestoreSensor.__new__(FlightRadar24RestoreSensor)
    sensor.coordinator = SimpleNamespace(flight=processor)

    attributes = sensor._current_extra_attributes()
    snapshot = deepcopy(attributes)

    processor.update_flights_tracked()

    assert attributes == snapshot
    # the next publish reflects the refreshed state
    refreshed = sensor._current_extra_attributes()
    assert 'live_attempt' not in refreshed['flights'][0]


def test_entered_and_exited_lists_are_snapshots():
    """entered/exited must not expose the processor's internal lists/dicts."""
    processor = make_processor()
    # seed a previous in-area flight so one exits and one enters
    processor._in_area = {'bbb': {'id': 'bbb', 'on_ground': 0}}
    details = {
        'id': 'aaa',
        'flight_number': 'XX1',
        'time_scheduled_departure': 1,
        'time_estimated_arrival': 2,
        'details_updated_at': time(),
        'coordinates': [],
    }
    processor._client.get_flights.return_value = [FeedFlight('aaa', on_ground=0)]
    with patch.object(FlightProcessor, '_fetch_details', return_value=details):
        processor.update_flights_in_area()

    entered = processor.entered_list
    exited = processor.exited_list
    assert [f['id'] for f in entered] == ['aaa']
    assert [f['id'] for f in exited] == ['bbb']
    entered_snapshot = deepcopy(entered)
    exited_snapshot = deepcopy(exited)

    # second refresh: the same in-area flight moved - stored dict gets updated
    processor._client.get_flights.return_value = [
        FeedFlight('aaa', on_ground=0, latitude=51.49),
    ]
    with patch.object(FlightProcessor, '_fetch_details', return_value=details):
        processor.update_flights_in_area()

    assert entered == entered_snapshot
    assert exited == exited_snapshot
