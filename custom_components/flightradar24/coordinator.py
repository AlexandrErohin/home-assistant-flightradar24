from __future__ import annotations
from typing import Any
from enum import Enum
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.device_registry import DeviceInfo
from pycountry import countries
from .const import (
    DOMAIN,
    URL,
    DEFAULT_NAME,
    EVENT_ENTRY,
    EVENT_EXIT,
    EVENT_MOST_TRACKED_NEW,
    EVENT_AREA_LANDED,
    EVENT_AREA_TOOK_OFF,
    EVENT_TRACKED_LANDED,
    EVENT_TRACKED_TOOK_OFF,
)
from logging import Logger
from FlightRadar24 import FlightRadar24API, Flight, Entity


class SensorType(Enum):
    TRACKED = 1
    IN_AREA = 2


class FlightRadar24Coordinator(DataUpdateCoordinator[int]):

    def __init__(
            self,
            hass: HomeAssistant,
            bounds: str,
            client: FlightRadar24API,
            update_interval: int,
            logger: Logger,
            unique_id: str,
            min_altitude: int,
            max_altitude: int,
            point: Entity,
    ) -> None:

        self._bounds = bounds
        self._client = client
        self.unique_id = unique_id
        self.in_area: dict[str, dict[str, Any]] | None = None
        self.tracked: dict[str, dict[str, Any]] = {}
        self.most_tracked: dict[str, dict[str, Any]] | None = None
        self.entered = {}
        self.exited = {}
        self.min_altitude = min_altitude
        self.max_altitude = max_altitude
        self.point = point
        self.enable_tracker: bool = False
        self.scanning: bool = True
        self.device_info = DeviceInfo(
            configuration_url=URL,
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=DEFAULT_NAME,
            name=DEFAULT_NAME,
        )

        super().__init__(
            hass,
            logger,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def clear_tracked(self) -> None:
        self.tracked = {}

    async def add_track(self, number: str) -> None:
        if not self.scanning:
            self.logger.error('FlightRadar24: API data fetching if OFF')
            return
        current: dict[str, dict[str, Any]] = {}
        number = number.upper()
        await self._find_flight(current, number)
        if not current:
            self.logger.error('FlightRadar24: Add Track - No flight found by - {}'.format(number))
            return
        self.tracked = self.tracked | current if self.tracked else current

    async def _find_flight(self, current: dict[str, dict[str, Any]], number: str) -> None:
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

        try:
            flights = await self.hass.async_add_executor_job(self._client.search, number)
            found = process_search_flight(flights, number)
            if not found:
                return
            if found.get('type') == 'live':
                data = [None] * 20
                data[1] = self._get_value(found, ['detail', 'lat'])
                data[2] = self._get_value(found, ['detail', 'lon'])
                data[13] = []
                flight = Flight(found.get('id'), data)
                flight.registration = found['detail']['reg']
                flight.callsign = found['detail']['callsign']

                await self._update_flights_data(flight, current, self.tracked)
            else:
                current[found.get('id')] = {
                    'id': found.get('id'),
                    'callsign': found['detail'].get('callsign'),
                    'flight_number': found['detail'].get('flight'),
                    'aircraft_registration': None,
                }
            current[found.get('id')]['tracked_type'] = found.get('type')
        except Exception as e:
            self.logger.error(e)

    async def remove_track(self, number: str) -> None:
        if not self.scanning:
            self.logger.error('FlightRadar24: API data fetching if OFF')
            return
        number = number.upper()
        remove = None
        for flight_id in self.tracked:
            flight = self.tracked[flight_id]
            if number in [flight.get('aircraft_registration'), flight.get('flight_number'), flight.get('callsign')]:
                remove = flight_id
                break
        if remove:
            del self.tracked[remove]
        else:
            self.logger.error('FlightRadar24: Remove Track - No flight found by - {}'.format(number))

    async def _async_update_data(self):
        if not self.scanning:
            return
        try:
            await self._update_flights_in_area()
            await self._update_flights_tracked()
            await self._update_most_tracked()
        except Exception as e:
            self.logger.error(e)

    async def _update_flights_in_area(self) -> None:
        self.entered = {}
        self.exited = {}
        flights = await self.hass.async_add_executor_job(
            self._client.get_flights, None, self._bounds
        )
        current: dict[str, dict[str, Any]] = {}
        for obj in flights:
            if not self.min_altitude <= obj.altitude <= self.max_altitude:
                continue
            await self._update_flights_data(obj, current, self.in_area, SensorType.IN_AREA)

        if self.in_area is not None:
            entries = current.keys() - self.in_area.keys()
            self.entered = [current[x] for x in entries]
            exits = self.in_area.keys() - current.keys()
            self.exited = [self.in_area[x] for x in exits]
            self._handle_boundary(EVENT_ENTRY, self.entered)
            self._handle_boundary(EVENT_EXIT, self.exited)
        self.in_area = current

    async def _update_flights_tracked(self) -> None:
        if not self.tracked:
            return

        reg_numbers = []
        current_flights = []
        current: dict[str, dict[str, Any]] = {}
        for flight in self.tracked:
            if self.tracked[flight].get('aircraft_registration'):
                reg_numbers.append(self.tracked[flight].get('aircraft_registration'))

        if reg_numbers:
            flights = await self.hass.async_add_executor_job(self._client.get_flights, None, None,
                                                             ','.join(reg_numbers))
            for obj in flights:
                await self._update_flights_data(obj, current, self.tracked, SensorType.TRACKED)
                current[obj.id]['tracked_type'] = 'live'
                if current[obj.id].get('flight_number'):
                    current_flights.append(current[obj.id].get('flight_number'))
                if current[obj.id].get('callsign'):
                    current_flights.append(current[obj.id].get('callsign'))

        remains = self.tracked.keys() - current.keys()
        if remains:
            for flight_id in remains:
                flight_number = self.tracked[flight_id].get('flight_number')
                if flight_number and flight_number in current_flights:
                    continue
                callsign = self.tracked[flight_id].get('callsign')
                if not flight_number and callsign and callsign in current_flights:
                    continue
                number = flight_number or callsign
                if not number:
                    continue
                size = current.__len__()
                await self._find_flight(current, number)
                if size != current.__len__():
                    current_flights.append(number)
                else:
                    current[flight_id] = self.tracked[flight_id]
                    current[flight_id]['tracked_type'] = 'not_found'

        self.tracked = current

    async def _update_most_tracked(self) -> None:
        if self.most_tracked is None:
            return
        flights = await self.hass.async_add_executor_job(self._client.get_most_tracked)
        current: dict[int, dict[str, Any]] = {}
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
        entries = [current[x] for x in (current.keys() - self.most_tracked.keys())]
        self.most_tracked = current
        self._handle_boundary(EVENT_MOST_TRACKED_NEW, entries)

    async def _update_flights_data(self,
                                   obj: Flight,
                                   current: dict[str, dict[str, Any]],
                                   tracked: dict[str, dict[str, Any]],
                                   sensor_type: SensorType | None = None,
                                   ) -> None:
        last_position = tracked[obj.id].get('on_ground') if tracked is not None and obj.id in tracked else None
        if (tracked is not None and obj.id in tracked and self._is_valid(tracked[obj.id])
                and self._to_int(last_position) == obj.on_ground):
            flight = tracked[obj.id]
        else:
            data = await self.hass.async_add_executor_job(
                self._client.get_flight_details, obj
            )
            flight = await self._get_flight_data(data)
        if flight is not None:
            current[flight['id']] = flight
            flight['latitude'] = obj.latitude
            flight['longitude'] = obj.longitude
            flight['altitude'] = obj.altitude
            flight['heading'] = obj.heading
            flight['ground_speed'] = obj.ground_speed
            flight['squawk'] = obj.squawk
            flight['vertical_speed'] = obj.vertical_speed
            flight['distance'] = obj.get_distance_from(self.point)
            flight['on_ground'] = obj.on_ground
            self._takeoff_and_landing(flight, last_position, obj.on_ground, sensor_type)

    def _handle_boundary(self, event: str, flights: list[dict[str, Any]]) -> None:
        for flight in flights:
            self._fire_event(event, flight)

    def _fire_event(self, event: str, flight: dict[str, Any]) -> None:
        flight['tracked_by_device'] = self.config_entry.title
        self.hass.bus.fire(event, flight)

    def _takeoff_and_landing(self,
                             flight: dict[str, Any],
                             last_position, position,
                             sensor_type: SensorType | None) -> None:
        last_position = self._to_int(last_position)
        position = self._to_int(position)
        if sensor_type is None or last_position is None or position is None or last_position == position:
            return
        if position == 0:
            self._fire_event(EVENT_AREA_TOOK_OFF if SensorType.IN_AREA == sensor_type else EVENT_TRACKED_TOOK_OFF,
                             flight)
        else:
            self._fire_event(EVENT_AREA_LANDED if SensorType.IN_AREA == sensor_type else EVENT_TRACKED_LANDED, flight)

    @staticmethod
    def _is_valid(flight: dict) -> bool:
        return all(flight.get(f) is not None for f in ['flight_number', 'time_scheduled_departure'])

    @staticmethod
    def _to_int(element: any) -> None | int:
        if element is None:
            return None
        try:
            return int(element)
        except ValueError:
            return None

    @staticmethod
    def _get_value(dictionary: dict, keys: list) -> Any | None:
        nested_dict = dictionary

        for key in keys:
            try:
                nested_dict = nested_dict[key]
            except Exception:
                return None
        return nested_dict

    async def _get_flight_data(self, flight: dict) -> dict[str, Any] | None:

        async def _get_country_code(code: None | str) -> None | str:
            if code is None or len(code) == 2:
                return code

            def _get_code(c: str):
                return countries.get(alpha_3=c)

            country = await self.hass.async_add_executor_job(_get_code, code)

            return country.alpha_2 if country is not None else code

        flight_id = self._get_value(flight, ['identification', 'id'])
        if flight_id is None:
            return None

        return {
            'id': flight_id,
            'flight_number': self._get_value(flight, ['identification', 'number', 'default']),
            'callsign': self._get_value(flight, ['identification', 'callsign']),
            'aircraft_registration': self._get_value(flight, ['aircraft', 'registration']),
            'aircraft_photo_small': self._get_value(flight, ['aircraft', 'images', 'thumbnails', 0, 'src']),
            'aircraft_photo_medium': self._get_value(flight, ['aircraft', 'images', 'medium', 0, 'src']),
            'aircraft_photo_large': self._get_value(flight, ['aircraft', 'images', 'large', 0, 'src']),
            'aircraft_model': self._get_value(flight, ['aircraft', 'model', 'text']),
            'aircraft_code': self._get_value(flight, ['aircraft', 'model', 'code']),
            'airline': self._get_value(flight, ['airline', 'name']),
            'airline_short': self._get_value(flight, ['airline', 'short']),
            'airline_iata': self._get_value(flight, ['airline', 'code', 'iata']),
            'airline_icao': self._get_value(flight, ['airline', 'code', 'icao']),
            'airport_origin_name': self._get_value(flight, ['airport', 'origin', 'name']),
            'airport_origin_code_iata': self._get_value(flight, ['airport', 'origin', 'code', 'iata']),
            'airport_origin_code_icao': self._get_value(flight, ['airport', 'origin', 'code', 'icao']),
            'airport_origin_country_name': self._get_value(flight, ['airport', 'origin', 'position',
                                                                    'country', 'name']),
            'airport_origin_country_code': await _get_country_code(
                self._get_value(flight, ['airport', 'origin', 'position', 'country', 'code'])),
            'airport_origin_city': self._get_value(flight, ['airport', 'origin', 'position', 'region', 'city']),
            'airport_origin_timezone_offset': self._get_value(flight, ['airport', 'origin', 'timezone', 'offset']),
            'airport_origin_timezone_abbr': self._get_value(flight, ['airport', 'origin', 'timezone', 'abbr']),
            'airport_origin_terminal': self._get_value(flight, ['airport', 'origin', 'info', 'terminal']),
            'airport_destination_name': self._get_value(flight, ['airport', 'destination', 'name']),
            'airport_destination_code_iata': self._get_value(flight, ['airport', 'destination', 'code', 'iata']),
            'airport_destination_code_icao': self._get_value(flight, ['airport', 'destination', 'code', 'icao']),
            'airport_destination_country_name': self._get_value(flight, ['airport', 'destination',
                                                                         'position', 'country', 'name']),
            'airport_destination_country_code': await _get_country_code(
                self._get_value(flight, ['airport', 'destination', 'position', 'country', 'code'])),
            'airport_destination_city': self._get_value(flight, ['airport', 'destination', 'position',
                                                                 'region', 'city']),
            'airport_destination_timezone_offset': self._get_value(flight,
                                                                   ['airport', 'destination', 'timezone', 'offset']),
            'airport_destination_timezone_abbr': self._get_value(flight,
                                                                 ['airport', 'destination', 'timezone', 'abbr']),
            'airport_destination_terminal': self._get_value(flight, ['airport', 'destination', 'info', 'terminal']),
            'time_scheduled_departure': self._get_value(flight, ['time', 'scheduled', 'departure']),
            'time_scheduled_arrival': self._get_value(flight, ['time', 'scheduled', 'arrival']),
            'time_real_departure': self._get_value(flight, ['time', 'real', 'departure']),
            'time_real_arrival': self._get_value(flight, ['time', 'real', 'arrival']),
            'time_estimated_departure': self._get_value(flight, ['time', 'estimated', 'departure']),
            'time_estimated_arrival': self._get_value(flight, ['time', 'estimated', 'arrival']),
        }
