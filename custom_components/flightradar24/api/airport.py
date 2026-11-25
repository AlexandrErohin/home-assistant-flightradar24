from dataclasses import dataclass
from enum import Enum
from .client import FlightRadarClient
from .helper import to_int, to_float, get_value
from typing import Any


class ScheduleType(Enum):
    ARRIVAL = 1
    DEPARTURE = 2


class AirportStats:
    arrivals_on_time: int
    arrivals_delayed: int
    arrivals_delay_average: int
    arrivals_delay_index: float
    arrivals_canceled: int
    departures_on_time: int
    departures_delayed: int
    departures_delay_average: int
    departures_delay_index: float
    departures_canceled: int


@dataclass
class AirportWeather:
    """Canonical METAR-derived weather from FR24 airport pluginData."""

    wind_direction_degree: float | None = None
    wind_direction_text: str | None = None
    wind_speed_kmh: float | None = None
    wind_speed_kts: float | None = None
    wind_speed_mph: float | None = None
    temp_celsius: float | None = None
    temp_fahrenheit: float | None = None
    dewpoint_celsius: float | None = None
    dewpoint_fahrenheit: float | None = None
    humidity: float | None = None
    pressure_hpa: float | None = None
    pressure_hg: float | None = None
    sky_condition: str | None = None
    visibility_km: float | None = None
    visibility_mi: float | None = None
    visibility_nmi: float | None = None
    metar: str | None = None
    time: int | None = None


# FR24 sometimes puts a sentinel like 99999000 in visibility.km while mi/nmi
# stay realistic (e.g. 62 mi). Treat huge km values as broken.
_VISIBILITY_KM_MAX = 1000.0


class AirportProcessor:
    __slots__ = ('_client', '_code', '_stats', '_weather', '_arrivals', '_departures')

    def __init__(self, client: FlightRadarClient) -> None:
        self._client = client
        self._code: str | None = None
        self._stats: AirportStats | None = None
        self._weather: AirportWeather | None = None
        self._arrivals: list[dict[str, Any]] | None = None
        self._departures: list[dict[str, Any]] | None = None

    def update_client(self, client: FlightRadarClient) -> None:
        self._client = client

    @property
    def code(self) -> str | None:
        return self._code

    @property
    def stats(self) -> AirportStats | None:
        return self._stats

    @property
    def weather(self) -> AirportWeather | None:
        return self._weather

    @property
    def arrivals(self) -> list[dict[str, Any]]:
        return self._arrivals

    @property
    def departures(self) -> list[dict[str, Any]]:
        return self._departures

    def set_track(self, code: str) -> None:
        code = code.upper()
        self.update_airport_info(code)
        self._code = code

    def restore_code(self, code: str) -> None:
        code = code.upper()
        self._code = code

    def remove_track(self) -> None:
        self._code = None
        self._stats = None
        self._weather = None
        self._arrivals = None
        self._departures = None

    def clear_live_data(self) -> None:
        self._stats = None
        self._weather = None
        self._arrivals = None
        self._departures = None

    def update_airport_info(self, code: str = None) -> None:
        if not self._code and not code:
            return

        data = get_value(self._client.get_airport_details(code or self._code), ['airport', 'pluginData'])
        self._stats = AirportStats()
        stats = get_value(data, ['details', 'stats', 'arrivals'])
        self._stats.arrivals_on_time = to_int(get_value(stats, ['today', 'quantity', 'onTime']))
        self._stats.arrivals_delayed = to_int(get_value(stats, ['today', 'quantity', 'delayed']))
        self._stats.arrivals_canceled = to_int(get_value(stats, ['today', 'quantity', 'canceled']))
        self._stats.arrivals_delay_average = to_int(get_value(stats, ['delayAvg']))
        self._stats.arrivals_delay_index = to_float(get_value(stats, ['delayIndex']))
        stats = get_value(data, ['details', 'stats', 'departures'])
        self._stats.departures_on_time = to_int(get_value(stats, ['today', 'quantity', 'onTime']))
        self._stats.departures_delayed = to_int(get_value(stats, ['today', 'quantity', 'delayed']))
        self._stats.departures_canceled = to_int(get_value(stats, ['today', 'quantity', 'canceled']))
        self._stats.departures_delay_average = to_int(get_value(stats, ['delayAvg']))
        self._stats.departures_delay_index = to_float(get_value(stats, ['delayIndex']))

        self._weather = self._parse_weather(get_value(data, ['weather']))

        self._update_schedule(ScheduleType.ARRIVAL, get_value(data, ['schedule', 'arrivals', 'data']))
        self._update_schedule(ScheduleType.DEPARTURE, get_value(data, ['schedule', 'departures', 'data']))

    @staticmethod
    def _parse_weather(weather: dict | None) -> AirportWeather | None:
        if not weather:
            return None

        visibility_km = to_float(get_value(weather, ['sky', 'visibility', 'km']))
        visibility_mi = to_float(get_value(weather, ['sky', 'visibility', 'mi']))
        visibility_nmi = to_float(get_value(weather, ['sky', 'visibility', 'nmi']))
        if (
            visibility_km is not None
            and visibility_km > _VISIBILITY_KM_MAX
            and visibility_mi is not None
        ):
            visibility_km = round(visibility_mi * 1.609344, 3)

        return AirportWeather(
            wind_direction_degree=to_float(get_value(weather, ['wind', 'direction', 'degree'])),
            wind_direction_text=get_value(weather, ['wind', 'direction', 'text']),
            wind_speed_kmh=to_float(get_value(weather, ['wind', 'speed', 'kmh'])),
            wind_speed_kts=to_float(get_value(weather, ['wind', 'speed', 'kts'])),
            wind_speed_mph=to_float(get_value(weather, ['wind', 'speed', 'mph'])),
            temp_celsius=to_float(get_value(weather, ['temp', 'celsius'])),
            temp_fahrenheit=to_float(get_value(weather, ['temp', 'fahrenheit'])),
            dewpoint_celsius=to_float(get_value(weather, ['dewpoint', 'celsius'])),
            dewpoint_fahrenheit=to_float(get_value(weather, ['dewpoint', 'fahrenheit'])),
            humidity=to_float(get_value(weather, ['humidity'])),
            pressure_hpa=to_float(get_value(weather, ['pressure', 'hpa'])),
            pressure_hg=to_float(get_value(weather, ['pressure', 'hg'])),
            sky_condition=get_value(weather, ['sky', 'condition', 'text']),
            visibility_km=visibility_km,
            visibility_mi=visibility_mi,
            visibility_nmi=visibility_nmi,
            metar=get_value(weather, ['metar']),
            time=to_int(get_value(weather, ['time'])),
        )

    def _update_schedule(self, schedule: ScheduleType, data: list) -> None:
        flights = []
        # Remote airport (from/to); local side is this tracked airport.
        remote = 'origin' if schedule == ScheduleType.ARRIVAL else 'destination'
        local = 'destination' if schedule == ScheduleType.ARRIVAL else 'origin'
        i = 0
        for item in (data or []):
            i += 1
            item = get_value(item, ['flight'])
            flights.append({
                'status_text': get_value(item, ['status', 'text']),
                'status': get_value(item, ['status', 'generic', 'status', 'text']),
                'flight_id': get_value(item, ['identification', 'id']),
                'flight_number': get_value(item, ['identification', 'number', 'default']),
                'callsign': get_value(item, ['identification', 'callsign']),
                'aircraft_code': get_value(item, ['aircraft', 'model', 'code']),
                'aircraft_model': get_value(item, ['aircraft', 'model', 'text']),
                'aircraft_registration': get_value(item, ['aircraft', 'registration']),
                'airline': get_value(item, ['airline', 'name']),
                'airline_short': get_value(item, ['airline', 'short']),
                'airline_iata': get_value(item, ['airline', 'code', 'iata']),
                'airline_icao': get_value(item, ['airline', 'code', 'icao']),
                'airport_name': get_value(item, ['airport', remote, 'name']),
                'airport_code_iata': get_value(item, ['airport', remote, 'code', 'iata']),
                'airport_code_icao': get_value(item, ['airport', remote, 'code', 'icao']),
                'airport_country_name': get_value(item, ['airport', remote, 'position', 'country', 'name']),
                'airport_country_code': get_value(item, ['airport', remote, 'position', 'country', 'code']),
                'airport_city': get_value(item, ['airport', remote, 'position', 'region', 'city']),
                'airport_terminal': get_value(item, ['airport', remote, 'info', 'terminal']),
                'airport_gate': get_value(item, ['airport', remote, 'info', 'gate']),
                'airport_baggage': get_value(item, ['airport', remote, 'info', 'baggage']),
                # Terminal / gate / baggage at the tracked airport.
                'terminal': get_value(item, ['airport', local, 'info', 'terminal']),
                'gate': get_value(item, ['airport', local, 'info', 'gate']),
                'baggage': get_value(item, ['airport', local, 'info', 'baggage']),
                'time_scheduled_departure': get_value(item, ['time', 'scheduled', 'departure']),
                'time_scheduled_arrival': get_value(item, ['time', 'scheduled', 'arrival']),
                'time_real_departure': get_value(item, ['time', 'real', 'departure']),
                'time_real_arrival': get_value(item, ['time', 'real', 'arrival']),
                'time_estimated_departure': get_value(item, ['time', 'estimated', 'departure']),
                'time_estimated_arrival': get_value(item, ['time', 'estimated', 'arrival']),
            })
            if i == 50:
                break
        if schedule == ScheduleType.ARRIVAL:
            self._arrivals = flights
        else:
            self._departures = flights
