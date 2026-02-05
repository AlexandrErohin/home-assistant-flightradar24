from enum import Enum
from FlightRadar24 import FlightRadar24API
from .helper import to_int, get_value
from typing import Any


class ScheduleType(Enum):
    ARRIVAL = 1
    DEPARTURE = 2


class AirportStats:
    arrivals_on_time: int
    arrivals_delayed: int
    arrivals_canceled: int
    departures_on_time: int
    departures_delayed: int
    departures_canceled: int


class AirportProcessor:
    __slots__ = ('_client', '_code', '_stats', '_arrivals', '_departures')

    def __init__(self, client: FlightRadar24API) -> None:
        self._client = client
        self._code: str | None = None
        self._stats: AirportStats | None = None
        self._arrivals: list[dict[str, Any]] | None = None
        self._departures: list[dict[str, Any]] | None = None

    @property
    def code(self) -> str | None:
        return self._code

    @property
    def stats(self) -> AirportStats | None:
        return self._stats

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
        self._arrivals = None
        self._departures = None

    def update_airport_info(self, code: str = None) -> None:
        if not self._code and not code:
            return

        data = get_value(self._client.get_airport_details(self._code or code), ['airport', 'pluginData'])
        self._stats = AirportStats()
        stats = get_value(data, ['details', 'stats'])
        self._stats.arrivals_on_time = to_int(get_value(stats, ['arrivals', 'today', 'quantity', 'onTime']))
        self._stats.arrivals_delayed = to_int(get_value(stats, ['arrivals', 'today', 'quantity', 'delayed']))
        self._stats.arrivals_canceled = to_int(get_value(stats, ['arrivals', 'today', 'quantity', 'canceled']))
        self._stats.departures_on_time = to_int(get_value(stats, ['departures', 'today', 'quantity', 'onTime']))
        self._stats.departures_delayed = to_int(get_value(stats, ['departures', 'today', 'quantity', 'delayed']))
        self._stats.departures_canceled = to_int(get_value(stats, ['departures', 'today', 'quantity', 'canceled']))

        self._update_schedule(ScheduleType.ARRIVAL, get_value(data, ['schedule', 'arrivals', 'data']))
        self._update_schedule(ScheduleType.DEPARTURE, get_value(data, ['schedule', 'departures', 'data']))

    def _update_schedule(self, schedule: ScheduleType, data: list) -> None:
        flights = []
        airport = 'origin' if schedule == ScheduleType.ARRIVAL else 'destination'
        i = 0
        for item in data:
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
                'airport_name': get_value(item, ['airport', airport, 'name']),
                'airport_code_iata': get_value(item, ['airport', airport, 'code', 'iata']),
                'airport_code_icao': get_value(item, ['airport', airport, 'code', 'icao']),
                'airport_country_name': get_value(item, ['airport', airport, 'position', 'country', 'name']),
                'airport_country_code': get_value(item, ['airport', airport, 'position', 'country', 'code']),
                'airport_city': get_value(item, ['airport', airport, 'position', 'region', 'city']),
                'time_scheduled_departure': get_value(item, ['time', 'scheduled', 'departure']),
                'time_scheduled_arrival': get_value(item, ['time', 'scheduled', 'arrival']),
                'time_real_departure': get_value(item, ['time', 'real', 'arrival']),
                'time_real_arrival': get_value(item, ['time', 'real', 'arrival']),
                'time_estimated_departure': get_value(item, ['time', 'estimated', 'arrival']),
                'time_estimated_arrival': get_value(item, ['time', 'estimated', 'arrival']),
            })
            if i == 50:
                break
        if schedule == ScheduleType.ARRIVAL:
            self._arrivals = flights
        else:
            self._departures = flights
