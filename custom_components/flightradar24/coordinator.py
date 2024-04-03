from __future__ import annotations
from typing import Any
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.device_registry import DeviceInfo
import pycountry
from .const import (
    DOMAIN,
    URL,
    DEFAULT_NAME,
    EVENT_FLIGHTRADAR24_ENTRY,
    EVENT_FLIGHTRADAR24_EXIT,
    EVENT_FLIGHTRADAR24_MOST_TRACKED_NEW,
)
from logging import Logger
from FlightRadar24 import FlightRadar24API, Flight


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

    async def add_track(self, number: str) -> None:
        try:
            flights = await self.hass.async_add_executor_job(self._client.search, number)
            flights = flights.get('live')
            if not flights:
                self.logger.error('FlightRadar24: No flight found by - {}'.format(number))
                return
            current: dict[int, dict[str, Any]] = {}
            data = [None] * 20
            data[1] = self._get_value(flights, [0, 'detail', 'lat'])
            data[2] = self._get_value(flights, [0, 'detail', 'lon'])
            data[13] = []
            flight = Flight(self._get_value(flights, [0, 'id']), data)
            flight.registration = self._get_value(flights, [0, 'detail', 'reg'])
            flight.callsign = self._get_value(flights, [0, 'detail', 'callsign'])

            await self._update_flights_data(flight, current, self.tracked)
            self.tracked = self.tracked | current if self.tracked else current
        except Exception as e:
            self.logger.error(e)

    async def remove_track(self, number: str) -> None:
        flight_id = None
        for flight_id in self.tracked:
            flight = self.tracked[flight_id]
            if number in [flight['aircraft_registration'], flight['flight_number'], flight['callsign']]:
                break
        if flight_id is not None:
            del self.tracked[flight_id]

    async def _async_update_data(self):
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
        current: dict[int, dict[str, Any]] = {}
        for obj in flights:
            if not self.min_altitude <= obj.altitude <= self.max_altitude:
                continue
            await self._update_flights_data(obj, current, self.in_area)

        if self.in_area is not None:
            entries = current.keys() - self.in_area.keys()
            self.entered = [current[x] for x in entries]
            exits = self.in_area.keys() - current.keys()
            self.exited = [self.in_area[x] for x in exits]
            self._handle_boundary(EVENT_FLIGHTRADAR24_ENTRY, self.entered)
            self._handle_boundary(EVENT_FLIGHTRADAR24_EXIT, self.exited)
        self.in_area = current

    async def _update_flights_tracked(self) -> None:
        if not self.tracked:
            return

        flights = await self.hass.async_add_executor_job(
            self._client.get_flights, None, None,
            ','.join([self.tracked[x]['aircraft_registration'] for x in self.tracked])
        )
        current: dict[int, dict[str, Any]] = {}
        for obj in flights:
            await self._update_flights_data(obj, current, self.tracked)
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
            }
        entries = self.entered = [current[x] for x in (current.keys() - self.most_tracked.keys())]
        self.most_tracked = current
        self._handle_boundary(EVENT_FLIGHTRADAR24_MOST_TRACKED_NEW, entries)

    async def _update_flights_data(self,
                                   obj: Flight,
                                   current: dict[int, dict[str, Any]],
                                   area: dict[str, dict[str, Any]],
                                   ) -> None:
        if area is not None and obj.id in area and self._is_valid(area[obj.id]):
            flight = area[obj.id]
        else:
            data = await self.hass.async_add_executor_job(
                self._client.get_flight_details, obj
            )
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

    def _handle_boundary(self, event: str, flights: list[dict[str, Any]]) -> None:
        for flight in flights:
            flight['tracked_by_device'] = self.config_entry.title
            self.hass.bus.fire(event, flight)

    @staticmethod
    def _is_valid(flight: dict) -> bool:
        return flight.get('flight_number') is not None

    @staticmethod
    def _get_value(dictionary: dict, keys: list) -> Any | None:
        nested_dict = dictionary

        for key in keys:
            try:
                nested_dict = nested_dict[key]
            except Exception:
                return None
        return nested_dict

    def _get_flight_data(self, flight: dict) -> dict[str, Any] | None:

        def _get_country_code(code: None | str) -> None | str:
            if code is None or len(code) == 2:
                return code
            country = pycountry.countries.get(alpha_3=code)

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
            'airport_origin_country_code': _get_country_code(
                self._get_value(flight, ['airport', 'origin', 'position', 'country', 'code'])),
            'airport_origin_city': self._get_value(flight, ['airport', 'origin', 'position', 'region', 'city']),
            'airport_destination_name': self._get_value(flight, ['airport', 'destination', 'name']),
            'airport_destination_code_iata': self._get_value(flight, ['airport', 'destination', 'code', 'iata']),
            'airport_destination_code_icao': self._get_value(flight, ['airport', 'destination', 'code', 'icao']),
            'airport_destination_country_name': self._get_value(flight, ['airport', 'destination',
                                                                         'position', 'country', 'name']),
            'airport_destination_country_code': _get_country_code(
                self._get_value(flight, ['airport', 'destination', 'position', 'country', 'code'])),
            'airport_destination_city': self._get_value(flight, ['airport', 'destination', 'position',
                                                                 'region', 'city']),
            'time_scheduled_departure': self._get_value(flight, ['time', 'scheduled', 'departure']),
            'time_scheduled_arrival': self._get_value(flight, ['time', 'scheduled', 'arrival']),
            'time_real_departure': self._get_value(flight, ['time', 'real', 'departure']),
            'time_real_arrival': self._get_value(flight, ['time', 'real', 'arrival']),
            'time_estimated_departure': self._get_value(flight, ['time', 'estimated', 'departure']),
            'time_estimated_arrival': self._get_value(flight, ['time', 'estimated', 'arrival']),
        }
