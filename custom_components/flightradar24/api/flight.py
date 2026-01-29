from typing import Any
from enum import Enum
from FlightRadar24 import FlightRadar24API, Flight, Entity
from .helper import to_int, get_value
from .event import EventManager
from ..const import (
    EVENT_ENTRY,
    EVENT_EXIT,
    EVENT_AREA_LANDED,
    EVENT_AREA_TOOK_OFF,
    EVENT_TRACKED_LANDED,
    EVENT_TRACKED_TOOK_OFF,
    EVENT_MOST_TRACKED_NEW,
)
import pycountry


class FlightType(Enum):
    TRACKED = 1
    IN_AREA = 2


class FlightProcessor:
    __slots__ = ('_in_area', '_tracked', '_most_tracked', '_entered', '_exited', '_min_altitude', '_max_altitude',
                 '_point', '_client', '_bounds', '_event_manager')

    def __init__(
            self,
            client: FlightRadar24API,
            event_manager: EventManager,
            min_altitude: int,
            max_altitude: int,
            point: Entity,
            bounds: str,
    ) -> None:
        self._min_altitude = min_altitude
        self._max_altitude = max_altitude
        self._point = point
        self._client = client
        self._bounds = bounds
        self._event_manager = event_manager
        self._in_area: dict[str, dict[str, Any]] | None = None
        self._tracked: dict[str, dict[str, Any]] = {}
        self._most_tracked: dict[str, dict[str, Any]] | None = None
        self._entered: list[dict[str, Any]] = []
        self._exited: list[dict[str, Any]] = []

    @property
    def tracked(self) -> dict[str, dict[str, Any]]:
        return self._tracked

    @property
    def tracked_list(self) -> list[dict[str, Any]]:
        return list(self._tracked.values()) if self._tracked else []

    @property
    def in_area_list(self) -> list[dict[str, Any]]:
        return list(self._in_area.values()) if self._in_area else []

    @property
    def most_tracked_list(self) -> list[dict[str, Any]] | None:
        return list(self._most_tracked.values()) if self._most_tracked else None

    @property
    def entered_list(self) -> list[dict[str, Any]]:
        return self._entered

    @property
    def exited_list(self) -> list[dict[str, Any]]:
        return self._exited

    def clear_tracked(self) -> None:
        self._tracked = {}

    def set_tracked(self, tracked: dict[str, dict[str, Any]]) -> None:
        self._tracked = tracked

    def enable_most_tracked(self) -> None:
        self._most_tracked = {}

    def add_track(self, number: str) -> dict | None:
        found: dict[str, dict[str, Any]] = {}
        number = number.upper()
        self._find_flight(found, number)
        if not found:
            return None
        self._tracked = self._tracked | found if self._tracked else found

        return found

    def remove_track(self, number: str) -> dict | None:
        number = number.upper()
        for flight_id, flight in self._tracked.items():
            if (number == flight.get('aircraft_registration') or
                    number == flight.get('flight_number') or
                    number == flight.get('callsign')):
                return self._tracked.pop(flight_id)
        return None

    def update_flights_in_area(self) -> None:
        self._entered = {}
        self._exited = {}
        flights = self._client.get_flights(bounds=self._bounds)
        current: dict[str, dict[str, Any]] = {}
        for obj in flights:
            if not self._min_altitude <= obj.altitude <= self._max_altitude:
                continue
            self._update_flights_data(obj, current, self._in_area, FlightType.IN_AREA)

        if self._in_area is not None:
            entries = current.keys() - self._in_area.keys()
            self._entered = [current[x] for x in entries]
            exits = self._in_area.keys() - current.keys()
            self._exited = [self._in_area[x] for x in exits]
            self._event_manager.add_events(EVENT_ENTRY, self._entered)
            self._event_manager.add_events(EVENT_EXIT, self._exited)
        self._in_area = current

    def update_flights_tracked(self) -> None:
        if not self._tracked:
            return

        reg_numbers = []
        current_flights = []
        current: dict[str, dict[str, Any]] = {}
        for flight in self._tracked:
            if self._tracked[flight].get('aircraft_registration'):
                reg_numbers.append(self._tracked[flight].get('aircraft_registration'))

        if reg_numbers:
            flights = self._client.get_flights(registration=','.join(reg_numbers))
            for obj in flights:
                self._update_flights_data(obj, current, self._tracked, FlightType.TRACKED)
                current[obj.id]['tracked_type'] = 'live'
                if current[obj.id].get('flight_number'):
                    current_flights.append(current[obj.id].get('flight_number'))
                if current[obj.id].get('callsign'):
                    current_flights.append(current[obj.id].get('callsign'))

        remains = self._tracked.keys() - current.keys()
        if remains:
            for flight_id in remains:
                flight_number = self._tracked[flight_id].get('flight_number')
                if flight_number and flight_number in current_flights:
                    continue
                callsign = self._tracked[flight_id].get('callsign')
                if not flight_number and callsign and callsign in current_flights:
                    continue
                number = flight_number or callsign
                if not number:
                    continue
                size = current.__len__()
                self._find_flight(current, number)
                if size != current.__len__():
                    current_flights.append(number)
                else:
                    current[flight_id] = self._tracked[flight_id]
                    current[flight_id]['tracked_type'] = 'not_found'

        self._tracked = current

    def _find_flight(self, current: dict[str, dict[str, Any]], number: str) -> None:
        def process_search_flight(objects: dict, search: str) -> dict | None:
            live = objects.get('live')
            if live:
                for element in live:
                    detail = element.get('detail')
                    if detail and search in (detail.get('reg'), detail.get('callsign'), detail.get('flight')):
                        return element
            schedule = objects.get('schedule')
            if schedule:
                for element in schedule:
                    detail = element.get('detail')
                    if detail and search in (detail.get('callsign'), detail.get('flight')):
                        return element
            return None

        flights = self._client.search(number)
        found = process_search_flight(flights, number)
        if not found:
            return
        if found.get('type') == 'live':
            data = [None] * 20
            data[1] = get_value(found, ['detail', 'lat'])
            data[2] = get_value(found, ['detail', 'lon'])
            data[13] = []
            flight = Flight(found.get('id'), data)
            flight.registration = found['detail']['reg']
            flight.callsign = found['detail']['callsign']

            self._update_flights_data(flight, current, self._tracked)
        else:
            current[found.get('id')] = {
                'id': found.get('id'),
                'callsign': found['detail'].get('callsign'),
                'flight_number': found['detail'].get('flight'),
                'aircraft_registration': None,
            }
        current[found.get('id')]['tracked_type'] = found.get('type')

    def update_most_tracked(self) -> None:
        if self._most_tracked is None:
            return
        flights = self._client.get_most_tracked()
        current: dict[str, dict[str, Any]] = {}
        for obj in flights.get('data'):
            current[obj['flight_id']] = {
                'id': obj.get('flight_id'),
                'flight_number': obj.get('flight'),
                'callsign': obj.get('callsign'),
                'squawk': obj.get('squawk'),
                'clicks': obj.get('clicks'),
                'airport_origin_code_iata': obj.get('from_iata'),
                'airport_origin_city': obj.get('from_city'),
                'airport_destination_code_iata': obj.get('to_iata'),
                'airport_destination_city': obj.get('to_city'),
                'aircraft_code': obj.get('model'),
                'aircraft_model': obj.get('type'),
                'on_ground': obj.get('on_ground'),
            }
        entries = [current[x] for x in (current.keys() - self._most_tracked.keys())]
        self._most_tracked = current
        self._event_manager.add_events(EVENT_MOST_TRACKED_NEW, entries)

    def _update_flights_data(self,
                             obj: Flight,
                             current: dict[str, dict[str, Any]],
                             tracked: dict[str, dict[str, Any]],
                             sensor_type: FlightType | None = None,
                             ) -> None:
        last_position = tracked[obj.id].get('on_ground') if tracked is not None and obj.id in tracked else None
        if (tracked is not None and obj.id in tracked and self._is_valid(tracked[obj.id])
                and to_int(last_position) == obj.on_ground):
            flight = tracked[obj.id]
        else:
            data = self._client.get_flight_details(obj)
            flight = self._get_flight_data(data)
        if flight is not None:
            current[flight['id']] = flight
            flight['latitude'] = obj.latitude
            flight['longitude'] = obj.longitude
            flight['altitude'] = obj.altitude
            flight['heading'] = obj.heading
            flight['ground_speed'] = obj.ground_speed
            flight['squawk'] = obj.squawk
            flight['vertical_speed'] = obj.vertical_speed
            new_distance = obj.get_distance_from(self._point)
            flight['distance'] = new_distance
            flight['closest_distance'] = min(new_distance, flight.get('closest_distance', new_distance))
            flight['on_ground'] = obj.on_ground
            self._takeoff_and_landing(flight, last_position, obj.on_ground, sensor_type)

    def _takeoff_and_landing(self,
                             flight: dict[str, Any],
                             last_position, position,
                             sensor_type: FlightType | None) -> None:
        last_position = to_int(last_position)
        position = to_int(position)
        if sensor_type is None or last_position is None or position is None or last_position == position:
            return
        if position == 0:
            self._event_manager.add_events(EVENT_AREA_TOOK_OFF if FlightType.IN_AREA == sensor_type
                                           else EVENT_TRACKED_TOOK_OFF, [flight])
        else:
            self._event_manager.add_events(EVENT_AREA_LANDED if FlightType.IN_AREA == sensor_type
                                           else EVENT_TRACKED_LANDED, [flight])

    def _get_flight_data(self, flight: dict) -> dict[str, Any] | None:

        def _get_country_code(code: None | str) -> None | str:
            if code is None or len(code) == 2:
                return code

            country = pycountry.countries.get(alpha_3=code)

            return country.alpha_2 if country is not None else code

        flight_id = get_value(flight, ['identification', 'id'])
        if flight_id is None:
            return None

        return {
            'id': flight_id,
            'flight_number': get_value(flight, ['identification', 'number', 'default']),
            'callsign': get_value(flight, ['identification', 'callsign']),
            'aircraft_registration': get_value(flight, ['aircraft', 'registration']),
            'aircraft_photo_small': get_value(flight, ['aircraft', 'images', 'thumbnails', 0, 'src']),
            'aircraft_photo_medium': get_value(flight, ['aircraft', 'images', 'medium', 0, 'src']),
            'aircraft_photo_large': get_value(flight, ['aircraft', 'images', 'large', 0, 'src']),
            'aircraft_model': get_value(flight, ['aircraft', 'model', 'text']),
            'aircraft_code': get_value(flight, ['aircraft', 'model', 'code']),
            'airline': get_value(flight, ['airline', 'name']),
            'airline_short': get_value(flight, ['airline', 'short']),
            'airline_iata': get_value(flight, ['airline', 'code', 'iata']),
            'airline_icao': get_value(flight, ['airline', 'code', 'icao']),
            'airport_origin_name': get_value(flight, ['airport', 'origin', 'name']),
            'airport_origin_code_iata': get_value(flight, ['airport', 'origin', 'code', 'iata']),
            'airport_origin_code_icao': get_value(flight, ['airport', 'origin', 'code', 'icao']),
            'airport_origin_country_name': get_value(flight, ['airport', 'origin', 'position', 'country', 'name']),
            'airport_origin_country_code': _get_country_code(
                get_value(flight, ['airport', 'origin', 'position', 'country', 'code'])),
            'airport_origin_city': get_value(flight, ['airport', 'origin', 'position', 'region', 'city']),
            'airport_origin_timezone_offset': get_value(flight, ['airport', 'origin', 'timezone', 'offset']),
            'airport_origin_timezone_abbr': get_value(flight, ['airport', 'origin', 'timezone', 'abbr']),
            'airport_origin_terminal': get_value(flight, ['airport', 'origin', 'info', 'terminal']),
            'airport_origin_latitude': get_value(flight, ['airport', 'origin', 'position', 'latitude']),
            'airport_origin_longitude': get_value(flight, ['airport', 'origin', 'position', 'longitude']),
            'airport_destination_name': get_value(flight, ['airport', 'destination', 'name']),
            'airport_destination_code_iata': get_value(flight, ['airport', 'destination', 'code', 'iata']),
            'airport_destination_code_icao': get_value(flight, ['airport', 'destination', 'code', 'icao']),
            'airport_destination_country_name': get_value(flight, ['airport', 'destination', 'position',
                                                                   'country', 'name']),
            'airport_destination_country_code': _get_country_code(
                get_value(flight, ['airport', 'destination', 'position', 'country', 'code'])),
            'airport_destination_city': get_value(flight, ['airport', 'destination', 'position',
                                                           'region', 'city']),
            'airport_destination_timezone_offset': get_value(flight,
                                                             ['airport', 'destination', 'timezone', 'offset']),
            'airport_destination_timezone_abbr': get_value(flight, ['airport', 'destination', 'timezone', 'abbr']),
            'airport_destination_terminal': get_value(flight, ['airport', 'destination', 'info', 'terminal']),
            'airport_destination_latitude': get_value(flight, ['airport', 'destination', 'position', 'latitude']),
            'airport_destination_longitude': get_value(flight, ['airport', 'destination', 'position', 'longitude']),
            'time_scheduled_departure': get_value(flight, ['time', 'scheduled', 'departure']),
            'time_scheduled_arrival': get_value(flight, ['time', 'scheduled', 'arrival']),
            'time_real_departure': get_value(flight, ['time', 'real', 'departure']),
            'time_real_arrival': get_value(flight, ['time', 'real', 'arrival']),
            'time_estimated_departure': get_value(flight, ['time', 'estimated', 'departure']),
            'time_estimated_arrival': get_value(flight, ['time', 'estimated', 'arrival']),
        }

    def _is_valid(self, flight: dict) -> bool:
        return all(flight.get(f) is not None for f in ['flight_number', 'time_scheduled_departure',
                                                       'time_estimated_arrival'])
