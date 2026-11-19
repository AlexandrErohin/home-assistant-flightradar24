"""A tracked flight found by search keeps its exact position (#151)."""

from copy import deepcopy
from unittest.mock import MagicMock, patch

from FlightRadarAPI import Entity
import pytest

from custom_components.flightradar24.api.flight import FlightProcessor

HOME = Entity(51.47, -0.4543)

# Real FR24 search answer (trimmed): the live position is rounded to 0.1 degree.
SEARCH = {
    "live": [{
        "id": "42a4df0b",
        "label": "EI387 / EIN3YR / A20N (EI-NSD)",
        "detail": {
            "lat": 51.5, "lon": -0.8, "schd_from": "LHR", "schd_to": "SNN", "ac_type": "A20N",
            "reg": "EI-NSD", "callsign": "EIN3YR", "flight": "EI387", "operator": "EIN",
        },
        "type": "live",
        "match": "begins",
    }],
    "schedule": [{
        "id": "EI387",
        "label": "EI387 / EIN3YR",
        "detail": {"callsign": "EIN3YR", "flight": "EI387", "operator": "EIN"},
        "type": "schedule",
        "match": "begins",
    }],
}

# Flight details: the trail is newest-first and holds the exact position.
DETAILS = {
    "identification": {"id": "42a4df0b", "number": {"default": "EI387"}, "callsign": "EIN3YR"},
    "aircraft": {"registration": "EI-NSD"},
    "trail": [{"lat": 51.4611, "lng": -0.826}, {"lat": 51.46, "lng": -0.80}],
}


def _processor(details, search=SEARCH):
    client = MagicMock()
    client.search.return_value = deepcopy(search)
    if isinstance(details, Exception):
        client.get_flight_details.side_effect = details
    else:
        client.get_flight_details.return_value = details
    return FlightProcessor(client, MagicMock(), -1, 100000, HOME, "1,-1,-1,1")


def _track(processor, via):
    if via == "add_track":
        processor.add_track("EI387")
    else:
        processor.set_tracked({"EI387": {
            "id": "EI387",
            "flight_number": "EI387",
            "tracked_type": "schedule",
            "tracked_by": "flight_number",
        }})
        processor.update_flights_tracked()
    [tracked] = processor.tracked_list
    return tracked


@pytest.mark.parametrize("via", ["add_track", "refresh"])
def test_search_hit_uses_exact_trail_position(via):
    """The rounded search position is neither published nor added to the track."""
    tracked = _track(_processor(DETAILS), via)

    assert tracked["id"] == "42a4df0b"
    assert tracked["tracked_type"] == "live"
    assert (tracked["latitude"], tracked["longitude"]) == (51.4611, -0.826)
    assert tracked["coordinates"] == [[51.46, -0.80], [51.4611, -0.826]]
    expected = Entity(51.4611, -0.826).get_distance_from(HOME)
    assert tracked["distance"] == expected
    assert tracked["closest_distance"] == expected


def test_search_hit_without_trail_keeps_search_position():
    """Without a trail the search position is the only one there is."""
    tracked = _track(_processor(DETAILS | {"trail": []}), "add_track")

    assert (tracked["latitude"], tracked["longitude"]) == (51.5, -0.8)
    assert tracked["coordinates"] == [[51.5, -0.8]]
    assert tracked["distance"] == Entity(51.5, -0.8).get_distance_from(HOME)


@pytest.mark.parametrize("via", ["add_track", "refresh"])
@pytest.mark.parametrize("newest", [(51.4501, -0.8499), (51.5499, -0.7501)])
def test_trail_point_just_inside_search_rounding_is_used(via, newest):
    """A trail point within 0.05 degree of the search position is the exact position."""
    details = DETAILS | {"trail": [{"lat": newest[0], "lng": newest[1]}, {"lat": 51.46, "lng": -0.80}]}
    tracked = _track(_processor(details), via)

    assert (tracked["latitude"], tracked["longitude"]) == newest
    assert tracked["coordinates"] == [[51.46, -0.80], list(newest)]
    assert tracked["distance"] == Entity(*newest).get_distance_from(HOME)


@pytest.mark.parametrize("via", ["add_track", "refresh"])
@pytest.mark.parametrize("stale", [(51.0, -0.8), (51.5, -0.9), (51.5501, -0.8)])
def test_stale_trail_point_keeps_search_position(via, stale):
    """A trail point outside the search rounding is old: behave as before (search position)."""
    details = DETAILS | {"trail": [{"lat": stale[0], "lng": stale[1]}, {"lat": 50.9, "lng": -0.7}]}
    tracked = _track(_processor(details), via)

    assert (tracked["latitude"], tracked["longitude"]) == (51.5, -0.8)
    assert tracked["coordinates"] == [[50.9, -0.7], list(stale), [51.5, -0.8]]
    expected = Entity(51.5, -0.8).get_distance_from(HOME)
    assert tracked["distance"] == expected
    assert tracked["closest_distance"] == expected


@pytest.mark.parametrize("via", ["add_track", "refresh"])
@pytest.mark.parametrize("unavailable", ["rate_limited", "cooldown"])
def test_search_hit_without_details_is_tracked_without_position(via, unavailable):
    """Without details the hit is tracked as live, with no position, as before."""
    processor = _processor(RuntimeError("HTTP Error 429"))
    with patch(
        "custom_components.flightradar24.api.flight.endpoint_in_cooldown",
        return_value=unavailable == "cooldown",
    ):
        tracked = _track(processor, via)

    assert tracked["id"] == "42a4df0b"
    assert tracked["flight_number"] == "EI387"
    assert tracked["callsign"] == "EIN3YR"
    assert tracked["tracked_type"] == "live"
    assert tracked["tracked_by"] == "flight_number"
    assert "latitude" not in tracked
    assert "coordinates" not in tracked


def test_search_hit_without_position_is_tracked_without_position():
    """A search answer without lat/lon behaves as before: tracked as live, no position."""
    live = SEARCH["live"][0]
    detail = {k: v for k, v in live["detail"].items() if k not in ("lat", "lon")}
    search = SEARCH | {"live": [live | {"detail": detail}]}
    tracked = _track(_processor(DETAILS, search), "add_track")

    assert tracked["id"] == "42a4df0b"
    assert tracked["tracked_type"] == "live"
    assert "latitude" not in tracked
    assert "coordinates" not in tracked
