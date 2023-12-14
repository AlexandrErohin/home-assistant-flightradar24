from __future__ import annotations
from typing import Any
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.device_registry import DeviceInfo
import math
import pycountry
from .models import BoundingBox
from .const import (
    DOMAIN,
    URL,
    DEFAULT_NAME,
    EVENT_FLIGHTRADAR24_ENTRY,
    EVENT_FLIGHTRADAR24_EXIT,
)
from logging import Logger
from FlightRadar24 import FlightRadar24API


class FlightRadar24Coordinator(DataUpdateCoordinator[int]):

    def __init__(
            self,
            hass: HomeAssistant,
            bound: BoundingBox,
            client: FlightRadar24API,
            update_interval: int,
            logger: Logger,
    ) -> None:

        self._bound = bound
        self._client = client
        self._logger = logger
        self.tracked: dict[int, dict[str, Any]] | None = None
        self.entered = {}
        self.exited = {}
        self.device_info = DeviceInfo(
            configuration_url=URL,
            identifiers={(DOMAIN, DEFAULT_NAME)},
            manufacturer=DEFAULT_NAME,
            name=DEFAULT_NAME,
        )

        super().__init__(
            hass,
            logger,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    @staticmethod
    def get_bounding_box(
            latitude: float,
            longitude: float,
            radius: float,
    ) -> BoundingBox:
        """Get bounding box from radius and a point."""
        half_side_in_km = abs(radius) / 1000

        lat = math.radians(latitude)
        lon = math.radians(longitude)

        approx_earth_radius = 6371
        hypotenuse_distance = math.sqrt(2 * (math.pow(half_side_in_km, 2)))

        lat_min = math.asin(
            math.sin(lat) * math.cos(hypotenuse_distance / approx_earth_radius)
            + math.cos(lat)
            * math.sin(hypotenuse_distance / approx_earth_radius)
            * math.cos(225 * (math.pi / 180)),
        )
        lon_min = lon + math.atan2(
            math.sin(225 * (math.pi / 180))
            * math.sin(hypotenuse_distance / approx_earth_radius)
            * math.cos(lat),
            math.cos(hypotenuse_distance / approx_earth_radius)
            - math.sin(lat) * math.sin(lat_min),
        )

        lat_max = math.asin(
            math.sin(lat) * math.cos(hypotenuse_distance / approx_earth_radius)
            + math.cos(lat)
            * math.sin(hypotenuse_distance / approx_earth_radius)
            * math.cos(45 * (math.pi / 180)),
        )
        lon_max = lon + math.atan2(
            math.sin(45 * (math.pi / 180))
            * math.sin(hypotenuse_distance / approx_earth_radius)
            * math.cos(lat),
            math.cos(hypotenuse_distance / approx_earth_radius)
            - math.sin(lat) * math.sin(lat_max),
        )

        rad2deg = math.degrees

        return BoundingBox(
            min_latitude=rad2deg(lat_min),
            max_latitude=rad2deg(lat_max),
            min_longitude=rad2deg(lon_min),
            max_longitude=rad2deg(lon_max),
        )

    async def _async_update_data(self):
        self.entered = {}
        self.exited = {}
        try:
            flights = await self.hass.async_add_executor_job(
                self._client.get_flights, None, self._bound.get_string()
            )
            current: dict[int, dict[str, Any]] = {}
            for obj in flights:
                if self.tracked is not None and obj.id in self.tracked and self._is_valid(self.tracked[obj.id]):
                    flight = self.tracked[obj.id]
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

            if self.tracked is not None:
                entries = current.keys() - self.tracked.keys()
                self.entered = [current[x] for x in entries]
                exits = self.tracked.keys() - current.keys()
                self.exited = [self.tracked[x] for x in exits]
                self._handle_boundary(EVENT_FLIGHTRADAR24_ENTRY, self.entered)
                self._handle_boundary(EVENT_FLIGHTRADAR24_EXIT, self.exited)
            self.tracked = current

        except Exception as e:
            self._logger.error(e)

    def _handle_boundary(self, event: str, flights: list[dict[str, Any]]) -> None:
        for flight in flights:
            self.hass.bus.fire(event, flight)

    @staticmethod
    def _get_value(dictionary: dict, keys: list) -> Any | None:
        nested_dict = dictionary

        for key in keys:
            try:
                nested_dict = nested_dict[key]
            except Exception:
                return None
        return nested_dict

    @staticmethod
    def _is_valid(flight: dict) -> bool:
        return flight['flight_number'] is not None

    @staticmethod
    def _get_country_code(code: None | str) -> None | str:
        if code is None or len(code) == 2:
            return code
        country = pycountry.countries.get(alpha_3=code)

        return country.alpha_2 if country is not None else code

    @staticmethod
    def _get_flight_data(flight: dict) -> dict[str, Any] | None:
        flight_id = FlightRadar24Coordinator._get_value(flight, ['identification', 'id'])
        if flight_id is None:
            return None

        return {
            'id': flight_id,
            'flight_number': FlightRadar24Coordinator._get_value(flight, ['identification', 'number', 'default']),
            'callsign': FlightRadar24Coordinator._get_value(flight, ['identification', 'callsign']),
            'aircraft_registration': FlightRadar24Coordinator._get_value(flight, ['aircraft', 'registration']),
            'aircraft_photo_small': FlightRadar24Coordinator._get_value(flight,
                                                                        ['aircraft', 'images', 'thumbnails', 0, 'src']),
            'aircraft_model': FlightRadar24Coordinator._get_value(flight, ['aircraft', 'model', 'text']),
            'aircraft_code': FlightRadar24Coordinator._get_value(flight, ['aircraft', 'model', 'code']),
            'airline': FlightRadar24Coordinator._get_value(flight, ['airline', 'name']),
            'airline_short': FlightRadar24Coordinator._get_value(flight, ['airline', 'short']),
            'airline_iata': FlightRadar24Coordinator._get_value(flight, ['airline', 'code', 'iata']),
            'airline_icao': FlightRadar24Coordinator._get_value(flight, ['airline', 'code', 'icao']),
            'airport_origin_name': FlightRadar24Coordinator._get_value(flight, ['airport', 'origin', 'name']),
            'airport_origin_code_iata': FlightRadar24Coordinator._get_value(flight,
                                                                            ['airport', 'origin', 'code', 'iata']),
            'airport_origin_code_icao': FlightRadar24Coordinator._get_value(flight,
                                                                            ['airport', 'origin', 'code', 'icao']),
            'airport_origin_country_name': FlightRadar24Coordinator._get_value(flight,
                                                                               ['airport', 'origin', 'position',
                                                                                'country', 'name']),
            'airport_origin_country_code': FlightRadar24Coordinator._get_country_code(
                FlightRadar24Coordinator._get_value(flight,['airport', 'origin', 'position', 'country', 'code'])),
            'airport_origin_city': FlightRadar24Coordinator._get_value(flight,
                                                                       ['airport', 'origin', 'position', 'region',
                                                                        'city']),
            'airport_destination_name': FlightRadar24Coordinator._get_value(flight, ['airport', 'destination', 'name']),
            'airport_destination_code_iata': FlightRadar24Coordinator._get_value(flight,
                                                                                 ['airport', 'destination', 'code',
                                                                                  'iata']),
            'airport_destination_code_icao': FlightRadar24Coordinator._get_value(flight,
                                                                                 ['airport', 'destination', 'code',
                                                                                  'icao']),
            'airport_destination_country_name': FlightRadar24Coordinator._get_value(flight,
                                                                                    ['airport', 'destination',
                                                                                     'position', 'country',
                                                                                     'name']),
            'airport_destination_country_code': FlightRadar24Coordinator._get_country_code(
                FlightRadar24Coordinator._get_value(flight,
                                                    ['airport', 'destination', 'position', 'country', 'code'])),
            'airport_destination_city': FlightRadar24Coordinator._get_value(flight,
                                                                            ['airport', 'destination', 'position',
                                                                             'region', 'city']),
            'time_scheduled_departure': FlightRadar24Coordinator._get_value(flight, ['time', 'scheduled', 'departure']),
            'time_scheduled_arrival': FlightRadar24Coordinator._get_value(flight, ['time', 'scheduled', 'arrival']),
            'time_real_departure': FlightRadar24Coordinator._get_value(flight, ['time', 'real', 'departure']),
            'time_real_arrival': FlightRadar24Coordinator._get_value(flight, ['time', 'real', 'arrival']),
        }
