"""Gate / baggage fields from FR24 flight details and airport schedule (#343)."""

from unittest.mock import MagicMock

from custom_components.flightradar24.api.airport import AirportProcessor, ScheduleType
from custom_components.flightradar24.api.flight import FlightProcessor


def _details_payload():
    return {
        "identification": {
            "id": "abc123",
            "number": {"default": "DL2066"},
            "callsign": "DAL2066",
        },
        "aircraft": {
            "registration": "N852NW",
            "model": {"text": "Airbus A330-223", "code": "A332"},
            "images": {},
        },
        "airline": {
            "name": "Delta Air Lines",
            "short": "Delta",
            "code": {"iata": "DL", "icao": "DAL"},
        },
        "airport": {
            "origin": {
                "name": "Detroit Metropolitan Wayne County Airport",
                "code": {"iata": "DTW", "icao": "KDTW"},
                "position": {
                    "latitude": 42.21,
                    "longitude": -83.35,
                    "country": {"name": "United States", "code": "US"},
                    "region": {"city": "Detroit"},
                },
                "timezone": {"offset": -18000, "abbr": "EST"},
                "info": {"terminal": "M", "baggage": None, "gate": "A28"},
            },
            "destination": {
                "name": "Berlin Brandenburg Airport",
                "code": {"iata": "BER", "icao": "EDDB"},
                "position": {
                    "latitude": 52.36,
                    "longitude": 13.5,
                    "country": {"name": "Germany", "code": "DE"},
                    "region": {"city": "Berlin"},
                },
                "timezone": {"offset": 3600, "abbr": "CET"},
                "info": {"terminal": "2", "baggage": "3", "gate": "D01"},
            },
        },
        "time": {
            "scheduled": {"departure": 1, "arrival": 2},
            "real": {"departure": None, "arrival": None},
            "estimated": {"departure": None, "arrival": None},
        },
        "trail": [],
    }


def test_flight_details_map_gate_and_baggage():
    processor = FlightProcessor(
        MagicMock(), MagicMock(), -1, 100000, MagicMock(), "1,1,-1,-1"
    )
    data = processor._get_flight_data(_details_payload())
    assert data["airport_origin_terminal"] == "M"
    assert data["airport_origin_gate"] == "A28"
    assert data["airport_origin_baggage"] is None
    assert data["airport_destination_terminal"] == "2"
    assert data["airport_destination_gate"] == "D01"
    assert data["airport_destination_baggage"] == "3"


def test_airport_arrivals_use_destination_gate_baggage():
    processor = AirportProcessor(MagicMock())
    schedule = [
        {
            "flight": {
                "identification": {
                    "id": "f1",
                    "number": {"default": "DL2066"},
                    "callsign": "DAL2066",
                },
                "status": {
                    "text": "Landed 10:02",
                    "generic": {"status": {"text": "landed"}},
                },
                "aircraft": {
                    "model": {"code": "A332", "text": "Airbus A330-223"},
                    "registration": "N852NW",
                },
                "airline": {
                    "name": "Delta Air Lines",
                    "short": "Delta",
                    "code": {"iata": "DL", "icao": "DAL"},
                },
                "airport": {
                    "origin": {
                        "name": "Detroit",
                        "code": {"iata": "DTW", "icao": "KDTW"},
                        "position": {
                            "country": {"name": "United States", "code": "US"},
                            "region": {"city": "Detroit"},
                        },
                        "info": {"terminal": "M", "baggage": None, "gate": "A28"},
                    },
                    "destination": {
                        "info": {"terminal": "2", "baggage": "3", "gate": "D01"},
                    },
                },
                "time": {
                    "scheduled": {"departure": 1, "arrival": 2},
                    "real": {"departure": None, "arrival": None},
                    "estimated": {"departure": None, "arrival": None},
                },
            }
        }
    ]
    processor._update_schedule(ScheduleType.ARRIVAL, schedule)
    flight = processor.arrivals[0]
    assert flight["gate"] == "D01"
    assert flight["baggage"] == "3"
    assert flight["terminal"] == "2"
    assert flight["airport_gate"] == "A28"
    assert flight["airport_terminal"] == "M"
    assert flight["airport_city"] == "Detroit"


def test_airport_departures_use_origin_gate():
    processor = AirportProcessor(MagicMock())
    schedule = [
        {
            "flight": {
                "identification": {
                    "id": "f2",
                    "number": {"default": "DL1"},
                    "callsign": "DAL1",
                },
                "status": {
                    "text": "Scheduled",
                    "generic": {"status": {"text": "scheduled"}},
                },
                "aircraft": {"model": {"code": "B738", "text": "Boeing 737"}, "registration": "N1"},
                "airline": {
                    "name": "Delta",
                    "short": "Delta",
                    "code": {"iata": "DL", "icao": "DAL"},
                },
                "airport": {
                    "origin": {
                        "info": {"terminal": "2", "baggage": None, "gate": "D5"},
                    },
                    "destination": {
                        "name": "Boston",
                        "code": {"iata": "BOS", "icao": "KBOS"},
                        "position": {
                            "country": {"name": "United States", "code": "US"},
                            "region": {"city": "Boston"},
                        },
                        "info": {"terminal": "A", "baggage": "3", "gate": "A10"},
                    },
                },
                "time": {
                    "scheduled": {"departure": 1, "arrival": 2},
                    "real": {"departure": None, "arrival": None},
                    "estimated": {"departure": None, "arrival": None},
                },
            }
        }
    ]
    processor._update_schedule(ScheduleType.DEPARTURE, schedule)
    flight = processor.departures[0]
    assert flight["gate"] == "D5"
    assert flight["terminal"] == "2"
    assert flight["baggage"] is None
    assert flight["airport_gate"] == "A10"
    assert flight["airport_baggage"] == "3"
    assert flight["airport_city"] == "Boston"
