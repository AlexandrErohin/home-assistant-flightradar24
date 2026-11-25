"""Airport weather parsing and unit-aware sensor values (#338)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.const import (
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
)

from custom_components.flightradar24.api.airport import AirportProcessor
from custom_components.flightradar24.const import (
    CONF_DISTANCE_UNIT,
    CONF_SPEED_UNIT,
    CONF_TEMPERATURE_UNIT,
    DISTANCE_UNIT_M,
    DISTANCE_UNIT_MI,
    SPEED_UNIT_KTS,
    TEMP_UNIT_F,
)
from custom_components.flightradar24 import sensor as sensor_module


WEATHER_PAYLOAD = {
    "metar": "EDDF 050620Z AUTO VRB02KT 9999 OVC016 02/01 Q0993 NOSIG",
    "time": 1770272400,
    "humidity": 93,
    "pressure": {"hg": 29, "hpa": 993},
    "sky": {
        "condition": {"text": "Overcast"},
        "visibility": {"km": 99999000, "mi": 62, "nmi": 54},
    },
    "wind": {
        "direction": {"degree": -1, "text": "Variable"},
        "speed": {"kmh": 4, "kts": 2, "mph": 2, "text": "Calm"},
    },
    "temp": {"celsius": 2, "fahrenheit": 36},
    "dewpoint": {"celsius": 1, "fahrenheit": 34},
}


def test_parse_weather_sanitizes_huge_visibility_km():
    weather = AirportProcessor._parse_weather(WEATHER_PAYLOAD)
    assert weather is not None
    assert weather.wind_direction_degree == -1
    assert weather.wind_direction_text == "Variable"
    assert weather.wind_speed_kmh == 4
    assert weather.temp_celsius == 2
    assert weather.humidity == 93
    assert weather.pressure_hpa == 993
    assert weather.dewpoint_celsius == 1
    assert weather.sky_condition == "Overcast"
    assert weather.visibility_mi == 62
    assert weather.visibility_km == round(62 * 1.609344, 3)
    assert weather.metar.startswith("EDDF")


def test_update_airport_info_stores_weather():
    client = MagicMock()
    client.get_airport_details.return_value = {
        "airport": {
            "pluginData": {
                "details": {
                    "stats": {
                        "arrivals": {
                            "delayAvg": 5,
                            "delayIndex": 0.4,
                            "today": {"quantity": {"onTime": 1, "delayed": 0, "canceled": 0}},
                        },
                        "departures": {
                            "delayAvg": 6,
                            "delayIndex": 0.5,
                            "today": {"quantity": {"onTime": 2, "delayed": 1, "canceled": 0}},
                        },
                    }
                },
                "weather": WEATHER_PAYLOAD,
                "schedule": {"arrivals": {"data": []}, "departures": {"data": []}},
            }
        }
    }
    processor = AirportProcessor(client)
    processor.set_track("FRA")
    assert processor.weather is not None
    assert processor.weather.sky_condition == "Overcast"
    assert processor.stats.arrivals_on_time == 1


def _coord(units: dict | None = None):
    weather = AirportProcessor._parse_weather(WEATHER_PAYLOAD)
    entry = SimpleNamespace(data=units or {})
    return SimpleNamespace(
        config_entry=entry,
        airport=SimpleNamespace(weather=weather),
    )


def test_sensor_helpers_respect_configured_units():
    coord = _coord(
        {
            CONF_TEMPERATURE_UNIT: TEMP_UNIT_F,
            CONF_SPEED_UNIT: SPEED_UNIT_KTS,
            CONF_DISTANCE_UNIT: DISTANCE_UNIT_MI,
        }
    )
    assert sensor_module._weather_temperature(coord) == 36
    assert sensor_module._weather_dewpoint(coord) == 34
    assert sensor_module._weather_wind_speed(coord) == 2
    assert sensor_module._weather_visibility(coord) == 62


def test_sensor_visibility_meters():
    coord = _coord({CONF_DISTANCE_UNIT: DISTANCE_UNIT_M})
    expected = round(coord.airport.weather.visibility_km * 1000, 1)
    assert sensor_module._weather_visibility(coord) == expected


def test_native_unit_of_measurement_follows_options():
    description = next(
        item
        for item in sensor_module.SENSOR_TYPES
        if item.key == "airport_temperature"
    )
    sensor = sensor_module.FlightRadar24Sensor.__new__(sensor_module.FlightRadar24Sensor)
    sensor.entity_description = description
    sensor.coordinator = _coord({CONF_TEMPERATURE_UNIT: TEMP_UNIT_F})
    assert sensor.native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT

    sensor.coordinator = _coord({CONF_SPEED_UNIT: SPEED_UNIT_KTS})
    sensor.entity_description = next(
        item for item in sensor_module.SENSOR_TYPES if item.key == "airport_wind_speed"
    )
    assert sensor.native_unit_of_measurement == UnitOfSpeed.KNOTS

    sensor.coordinator = _coord({CONF_DISTANCE_UNIT: DISTANCE_UNIT_MI})
    sensor.entity_description = next(
        item for item in sensor_module.SENSOR_TYPES if item.key == "airport_visibility"
    )
    assert sensor.native_unit_of_measurement == UnitOfLength.MILES
