import re
from typing import Any, Optional
from enum import Enum
from time import time
from random import randint
from .client import FlightRadarClient
from FlightRadarAPI import Flight, Entity
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
    EVENT_TRACKED_ARRIVED_GATE,
    EVENT_TRACKED_LEFT_GATE,
    COORDINATES_MAX_POINTS,
)
import pycountry


def is_helicopter(flight) -> bool:
    """Check if a flight is a helicopter based on callsign, model or ICAO code."""

    def get_val(key):
        return str(
            flight.get(key, "")
            if isinstance(flight, dict)
            else getattr(flight, key, "") or ""
        )

    callsign = get_val("callsign")
    model = get_val("aircraft_model")
    code = get_val("aircraft_code")

    if re.match(
        (
            r"^(LIFELN|POLICE|MEDIC|LL|HELI|SAR|SGR|ZULU|SLAYR|CRNGE|"
            r"VORTX|SHARK|REAPER|APACHE|FIRE|RESCUE|PNTHR|VICTR|CHX|"
            r"NHC|UKP|NPAS|AAC|AMBUSH|BARON|ARCTIC|COAST|KUST|RAINBOW|"
            r"SAMU|DRAG|PEGASO|HEMS)"
        ),
        callsign,
        re.IGNORECASE,
    ):
        return True

    if re.search(
        (
            r"(HELICOPTER|EUROCOPTER|ROBINSON|AGUSTA|BELL\s|SIKORSKY|"
            r"AEROSPATIALE|MD\sHELICOPTERS|GUIMBAL|KAMOV|LEONARDO|"
            r"WESTLAND|APACHE|CHINOOK|GAZELLE|MERLIN|WILDCAT|LYNX|"
            r"PUMA|BOEING\sAH|AH\-64)"
        ),
        model,
        re.IGNORECASE,
    ):
        return True

    if re.match(
        (
            r"^(R22|R44|R66|EC|AS[35]|H1[23467]|H6[045]|H47|AW|"
            r"B[0245]|UH|CH|A1[0-9]|H500|MI[0-9]|NH90|SK[0-9]|"
            r"EH10|LYNX|G2CA|S76|S92|EC45)"
        ),
        code,
        re.IGNORECASE,
    ):
        return True

    return False


def get_country_code(code: Optional[str]) -> Optional[str]:
    if code is None or len(code) == 2:
        return code

    country = pycountry.countries.get(alpha_3=code)

    return country.alpha_2 if country is not None else code


class FlightType(Enum):
    TRACKED = 1
    IN_AREA = 2


class FlightProcessor:
    __slots__ = ('_in_area', '_tracked', '_most_tracked', '_entered', '_exited', '_min_altitude', '_max_altitude',
                 '_point', '_client', '_bounds', '_event_manager', '_auto_cleanup', '_raw_in_area_count')

    def __init__(
            self,
            client: FlightRadarClient,
            event_manager: EventManager,
            min_altitude: int,
            max_altitude: int,
            point: Entity,
            bounds: str,
            auto_cleanup: bool = False,
    ) -> None:
        self._min_altitude = min_altitude
        self._max_altitude = max_altitude
        self._point = point
        self._client = client
        self._bounds = bounds
        self._event_manager = event_manager
        self._auto_cleanup = auto_cleanup
        self._in_area: dict[str, dict[str, Any]] | None = None
        self._tracked: dict[str, dict[str, Any]] = {}
        self._most_tracked: dict[str, dict[str, Any]] | None = None
        self._entered: list[dict[str, Any]] = []
        self._exited: list[dict[str, Any]] = []
        self._raw_in_area_count: int = 0

    @property
    def client(self) -> FlightRadarClient:
        return self._client

    @property
    def raw_in_area_count(self) -> int:
        return self._raw_in_area_count

    @property
    def bounds(self) -> str:
        return self._bounds

    def update_client(self, client: FlightRadarClient) -> None:
        self._client = client

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
    def most_tracked_enabled(self) -> bool:
        return self._most_tracked is not None

    @property
    def most_tracked_list(self) -> list[dict[str, Any]]:
        return list(self._most_tracked.values()) if self._most_tracked else []

    @property
    def entered_list(self) -> list[dict[str, Any]]:
        return self._entered

    @property
    def exited_list(self) -> list[dict[str, Any]]:
        return self._exited

    def clear_live_data(self) -> None:
        self._in_area = {}
        # None means "most tracked was never switched on" - clearing live data
        # must not turn the sensor on by accident.
        self._most_tracked = {} if self._most_tracked is not None else None
        self._entered = []
        self._exited = []
        self._tracked = {key: {
            'aircraft_registration': value.get('aircraft_registration'),
            'flight_number': value.get('flight_number'),
            'callsign': value.get('callsign'),
        } for key, value in self._tracked.items()}

    def clear_tracked(self) -> None:
        self._tracked = {}

    def set_tracked(self, tracked: dict[str, dict[str, Any]]) -> None:
        self._tracked = tracked

    def enable_most_tracked(self) -> None:
        self._most_tracked = {}

    def disable_most_tracked(self) -> None:
        self._most_tracked = None

    def add_track(self, number: str) -> dict | None:
        found = self._find_flight(number.upper())
        if not found:
            return None
        found = {found.get('id'): found}
        self._tracked = (self._tracked | found) if self._tracked else found

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
        self._entered = []
        self._exited = []
        flights = self._client.get_flights(bounds=self._bounds)
        # Unfiltered count for the session guard (see coordinator) - altitude
        # filtering below must not hide traffic from the empty-session detection.
        self._raw_in_area_count = len(flights)

        is_first_run = self._in_area is None
        self._in_area = self._in_area or {}

        # Firstly, remove exited flights
        if not is_first_run:
            for key in set(self._in_area) - {f.id for f in flights}:
                exited = self._in_area.pop(key)
                self._exited.append(exited)
                self._event_manager.add_event(EVENT_EXIT, exited)

        for obj in flights:
            altitude = to_int(obj.altitude)
            # An unknown altitude is not a reason to drop the flight from the area.
            if altitude is None or self._min_altitude <= altitude <= self._max_altitude:
                is_new_flight = not is_first_run and obj.id not in self._in_area
                # Secondly update existed flight or add a new flight with details
                flight = self._update_flights_data(obj, self._in_area.get(obj.id, {}), FlightType.IN_AREA)
                if flight:
                    self._in_area[flight['id']] = flight
                    if is_new_flight:
                        self._entered.append(flight)
                        self._event_manager.add_event(EVENT_ENTRY, flight)

    @staticmethod
    def _has_arrived_evidence(flight: dict[str, Any]) -> bool:
        """True when the tracked flight has actually landed this segment.

        Presence in the live feed alone is not enough: ADS-B gaps (e.g. Bay of
        Bengal) make flights disappear mid-air. Private/GA often lack
        time_real_arrival, so has_landed (from on_ground after being airborne)
        is the primary signal; time_real_arrival is an airline-only bonus.
        """
        if flight.get('has_landed'):
            return True
        if flight.get('time_real_arrival') is not None:
            return True
        return False

    @staticmethod
    def _reset_gate_lifecycle(flight: dict[str, Any], on_ground=None) -> None:
        """Start a new departure segment after leaving the gate."""
        flight['has_landed'] = False
        flight['gate_arrived_sent'] = False
        if on_ground is None:
            on_ground = flight.get('on_ground')
        flight['was_airborne'] = to_int(on_ground) == 0

    def _maybe_fire_left_gate(
            self,
            previous_type: str | None,
            flight: dict[str, Any],
    ) -> None:
        """Fire left_gate only on schedule/aircraft → live (not live reappear)."""
        if flight.get('tracked_type') != 'live':
            return
        if previous_type not in ('schedule', 'aircraft'):
            return
        self._event_manager.add_event(EVENT_TRACKED_LEFT_GATE, flight)
        self._reset_gate_lifecycle(flight)

    def update_flights_tracked(self) -> None:
        if not self._tracked:
            return

        current_flights = []
        flight_ids = set(self._tracked.keys())
        reg_to_id = {f.get('aircraft_registration'): f.get('id') for f in self._tracked.values() if
                     f.get('aircraft_registration')}

        # Firstly checking live flights
        if reg_to_id:
            flights = self._client.get_flights(registration=','.join(reg_to_id.keys()))
            for obj in flights:
                previous = self._tracked.get(obj.id, {})
                registration = getattr(obj, 'registration', None)
                old_flight_id = reg_to_id.get(registration) if registration else None
                if not previous and old_flight_id:
                    previous = self._tracked.get(old_flight_id, {})
                # New FR24 flight id for the same registration: keep tracking meta
                # only (lifecycle flags belong to the previous segment).
                if previous and previous.get('id') not in (None, obj.id):
                    previous = {
                        key: previous.get(key)
                        for key in ('tracked_by', 'tracked_type')
                        if previous.get(key) is not None
                    }
                previous_type = previous.get('tracked_type')
                flight = self._update_flights_data(obj, previous, FlightType.TRACKED)
                if flight:
                    registration = flight.get('aircraft_registration')
                    if registration in reg_to_id:
                        old_flight_id = reg_to_id.pop(registration)
                    if old_flight_id and old_flight_id != flight.get('id'):
                        self._tracked.pop(old_flight_id, None)
                    # mark that flight has updated
                    flight['live_attempt'] = 1
                    if not flight.get('tracked_type'):
                        flight['tracked_type'] = 'live'
                    self._tracked[obj.id] = flight
                    flight_ids.discard(old_flight_id)
                    flight_ids.discard(obj.id)
                    self._maybe_fire_left_gate(previous_type, flight)
                    if flight.get('flight_number'):
                        current_flights.append(flight.get('flight_number'))
                    if flight.get('callsign'):
                        current_flights.append(flight.get('callsign'))

        # Secondly checking flights that were live recently
        for flight_id in reg_to_id.values():
            flight = self._tracked[flight_id]
            # move to next update to re-check if this flight ends
            if flight.get('live_attempt'):
                del self._tracked[flight_id]['live_attempt']
                flight_ids.discard(flight_id)
                continue

            # Logic for recent live flights that now is ended
            if flight.get('tracked_type') != 'live':
                # fr24 search doesnt show schedule for aircraft registration - waiting live flight
                if flight.get('tracked_type') == 'aircraft':
                    flight_ids.discard(flight_id)
                continue

            # Still airborne (or never took off): treat missing live data as a
            # coverage gap / taxi flicker, not gate arrival (#315).
            if not self._has_arrived_evidence(flight):
                flight_ids.discard(flight_id)
                continue

            if not flight.get('gate_arrived_sent'):
                self._event_manager.add_event(EVENT_TRACKED_ARRIVED_GATE, flight)
                flight['gate_arrived_sent'] = True
                self._tracked[flight_id] = flight

            # --- AUTO-CLEANUP LOGIC WRAPPED IN CONFIG CHECK ---
            if self._auto_cleanup:
                del self._tracked[flight_id]
                flight_ids.discard(flight_id)
                continue

            if flight.get('tracked_by') == 'aircraft_registration':
                # fr24 search doesnt show schedule for aircraft registration - waiting live flight
                self._tracked[flight_id] = {
                            'id': flight_id,
                            'latitude': flight.get('latitude'),
                            'longitude': flight.get('longitude'),
                            'altitude': flight.get('altitude'),
                            'aircraft_icao_24bit': flight.get('aircraft_icao_24bit'),
                            'on_ground': flight.get('on_ground'),
                            'aircraft_category': flight.get('aircraft_category'),
                            'aircraft_registration': flight.get('aircraft_registration'),
                            'aircraft_photo_small': flight.get('aircraft_photo_small'),
                            'aircraft_photo_medium': flight.get('aircraft_photo_medium'),
                            'aircraft_photo_large': flight.get('aircraft_photo_large'),
                            'aircraft_model': flight.get('aircraft_model'),
                            'aircraft_code': flight.get('aircraft_code'),
                            'airline': flight.get('airline'),
                            'airline_short': flight.get('airline_short'),
                            'airline_iata': flight.get('airline_iata'),
                            'airline_icao': flight.get('airline_icao'),
                            'airport_origin_name': flight.get('airport_destination_name'),
                            'airport_origin_code_iata': flight.get('airport_destination_name'),
                            'airport_origin_code_icao': flight.get('airport_destination_code_icao'),
                            'airport_origin_country_name': flight.get('airport_destination_country_name'),
                            'airport_origin_country_code': flight.get('airport_destination_country_code'),
                            'airport_origin_city': flight.get('airport_destination_city'),
                            'airport_origin_timezone_offset': flight.get('airport_destination_timezone_offset'),
                            'airport_origin_timezone_abbr': flight.get('airport_destination_timezone_abbr'),
                            'airport_origin_terminal': None,
                            'airport_origin_latitude': flight.get('airport_destination_latitude'),
                            'airport_origin_longitude': flight.get('airport_destination_longitude'),
                            'tracked_by': 'aircraft_registration',
                            'tracked_type': 'aircraft',
                }
                flight_ids.discard(flight_id)
                continue

            # Flight-number tracking: allow phase 3 to refresh schedule, but do
            # not re-enter search while still marked live without a schedule yet
            # in a way that would pair with left_gate on a live flicker.
            # Phase 3 left_gate is gated on previous_type schedule/aircraft.

        # Thirdly checking scheduled flights
        for flight_id in list(flight_ids):
            flight = self._tracked.get(flight_id)
            if not flight:
                continue

            number = flight.get('flight_number') or flight.get('callsign')
            if not number or number in current_flights:
                del self._tracked[flight_id]
                continue
            previous_type = flight.get('tracked_type')
            found = self._find_flight(number)
            if found:
                if found.get('tracked_type') == 'schedule':
                    # Copy origin and destination airports info
                    keys_to_copy = ['airport_origin_name', 'airport_origin_code_iata', 'airport_origin_code_icao',
                                    'airport_origin_country_name', 'airport_origin_country_code',
                                    'airport_origin_city', 'airport_origin_timezone_offset',
                                    'airport_origin_timezone_abbr', 'airport_origin_latitude',
                                    'airport_origin_longitude', 'airport_destination_name',
                                    'airport_destination_code_iata', 'airport_destination_code_icao',
                                    'airport_destination_country_name', 'airport_destination_country_code',
                                    'airport_destination_city', 'airport_destination_timezone_offset',
                                    'airport_destination_timezone_abbr', 'airport_destination_latitude',
                                    'airport_destination_longitude'
                                    ]
                    for key in keys_to_copy:
                        if key in flight:
                            found[key] = flight[key]
                    # Schedule stub for the next segment - clear gate lifecycle.
                    self._reset_gate_lifecycle(found, on_ground=1)
                if flight_id != found.get('id'):
                    del self._tracked[flight_id]
                # Carry airline arrival evidence onto a still-live search hit
                if found.get('tracked_type') == 'live':
                    for key in ('was_airborne', 'has_landed', 'gate_arrived_sent'):
                        if flight.get(key) and not found.get(key):
                            found[key] = flight.get(key)
                self._tracked[found.get('id')] = found
                self._maybe_fire_left_gate(previous_type, found)

    def _find_flight(self, number: str) -> dict[str, Any] | None:
        flights = self._client.search(number)
        found = self._process_search_flight(flights, number)
        if not found:
            return None
        result = {
            'id': found.get('id'),
            'callsign': found.get('callsign'),
            'flight_number': found.get('flight'),
            'aircraft_registration': found.get('aircraft_registration'),
        }
        if found.get('tracked_type') == 'live':
            data = [None] * 20
            data[1] = found.get('lat')
            data[2] = found.get('lon')
            data[13] = []
            flight = Flight(found.get('id'), data)
            flight.registration = found.get('reg')
            flight.callsign = found.get('callsign')
            try:
                result = self._update_flights_data(flight, {})
            except Exception:
                found['tracked_type'] = 'schedule'
        if result:
            result['tracked_type'] = found.get('tracked_type')
            result['tracked_by'] = found.get('tracked_by')
        return result

    def _process_search_flight(self, objects: dict, search: str) -> dict | None:
        if not search:
            return None

        search_rules = [
            ('live', 'reg', 'aircraft_registration'),
            ('live', 'callsign', 'callsign'),
            ('live', 'flight', 'flight_number'),
            ('schedule', 'callsign', 'callsign'),
            ('schedule', 'flight', 'flight_number'),
        ]

        for type, field, tracked_by in search_rules:
            for item in objects.get(type, []):
                detail = item.get('detail')
                if detail and detail.get(field) == search:
                    detail['id'] = item.get('id')
                    detail['tracked_type'] = type
                    detail['tracked_by'] = tracked_by
                    return detail

        for element in objects.get('aircraft', []):
            if element.get('id') == search:
                element['aircraft_registration'] = element.get('id')
                element['tracked_type'] = 'aircraft'
                element['tracked_by'] = 'aircraft_registration'
                return element

        return None

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
                             previous: dict[str, Any],
                             sensor_type: FlightType | None = None,
                             ) -> dict[str, Any] | None:
        is_same_flight = previous and previous.get('id') == obj.id
        if is_same_flight:
            last_position = previous.get('on_ground')
            previous_closest_distance = previous.get('closest_distance')
        else:
            last_position = None
            previous_closest_distance = None

        if (is_same_flight and self._is_valid(previous)
                and to_int(last_position) == obj.on_ground):
            flight = previous
        else:
            data = self._client.get_flight_details(obj)
            flight = self._get_flight_data(data)
        if flight is not None:
            flight['latitude'] = obj.latitude
            flight['longitude'] = obj.longitude
            flight['altitude'] = obj.altitude
            flight['heading'] = obj.heading
            flight['ground_speed'] = obj.ground_speed
            flight['squawk'] = obj.squawk
            flight['vertical_speed'] = obj.vertical_speed
            flight['aircraft_icao_24bit'] = getattr(obj, 'icao_24bit', '')
            new_distance = obj.get_distance_from(self._point)
            flight['distance'] = new_distance
            flight['closest_distance'] = min(
                new_distance,
                previous_closest_distance if previous_closest_distance is not None else new_distance,
            )
            flight['on_ground'] = obj.on_ground
            flight['aircraft_category'] = "Helicopter" if is_helicopter(flight) else "Airplane"
            # Prefer live history we already accumulated; otherwise seed from
            # FR24 trail returned with the first details payload.
            seed = None
            if is_same_flight and previous.get('coordinates'):
                seed = previous.get('coordinates')
            elif flight.get('coordinates'):
                seed = flight.get('coordinates')
            flight['coordinates'] = self._append_coordinates(
                seed,
                obj.latitude,
                obj.longitude,
            )
            # Add information for additional tracked flights
            if previous.get('tracked_by'):
                flight['tracked_by'] = previous.get('tracked_by')
            if previous.get('tracked_type'):
                flight['tracked_type'] = 'live'
            self._apply_gate_lifecycle(flight, previous, obj.on_ground)
            self._takeoff_and_landing(flight, last_position, obj.on_ground, sensor_type)

        return flight

    @staticmethod
    def _apply_gate_lifecycle(
            flight: dict[str, Any],
            previous: dict[str, Any],
            on_ground,
    ) -> None:
        """Track airborne/landed sticky flags for gate events (#315).

        was_airborne: seen in the air this segment (or restored mid-flight).
        has_landed: back on ground after being airborne (works for private/GA
        without time_real_arrival). Pre-departure taxi keeps both false so a
        live-feed flicker cannot look like arrived_gate.
        """
        was_airborne = bool(previous.get('was_airborne'))
        has_landed = bool(previous.get('has_landed'))
        ground = to_int(on_ground)

        if ground == 0:
            was_airborne = True
        elif ground == 1 and was_airborne:
            has_landed = True

        flight['was_airborne'] = was_airborne
        flight['has_landed'] = has_landed
        flight['gate_arrived_sent'] = bool(previous.get('gate_arrived_sent'))

    def _coordinates_from_trail(self, trail: list | None) -> list[list[float]]:
        """Build chronological [lat, lon] history from FR24 details trail.

        FR24 returns `trail` newest-first (descending `ts`). Keep the newest
        COORDINATES_MAX_POINTS points and reverse them to oldest -> newest.
        """
        if not trail:
            return []

        points: list[list[float]] = []
        for item in trail[:COORDINATES_MAX_POINTS]:
            if not isinstance(item, dict):
                continue
            lat = item.get('lat')
            lng = item.get('lng')
            if lat is None or lng is None:
                continue
            points.append([lat, lng])
        points.reverse()
        return points

    def _append_coordinates(
            self,
            previous_coordinates: list | None,
            latitude,
            longitude,
    ) -> list[list[float]]:
        """Accumulate [lat, lon] history for the flight track."""
        coordinates = list(previous_coordinates) if previous_coordinates else []
        if latitude is None or longitude is None:
            return coordinates[-COORDINATES_MAX_POINTS:]

        point = [latitude, longitude]
        if not coordinates or coordinates[-1] != point:
            coordinates.append(point)
        return coordinates[-COORDINATES_MAX_POINTS:]

    def _takeoff_and_landing(self,
                             flight: dict[str, Any],
                             last_position, position,
                             sensor_type: FlightType | None) -> None:
        if sensor_type is None:
            return

        last = to_int(last_position)
        current = to_int(position)

        if last is None or current is None or last == current:
            return

        # (Type, position) -> event
        event_map = {
            (FlightType.IN_AREA, 0): EVENT_AREA_TOOK_OFF,  # 0 = ground -> take off
            (FlightType.IN_AREA, 1): EVENT_AREA_LANDED,  # 1 = Flying -> land
            (FlightType.TRACKED, 0): EVENT_TRACKED_TOOK_OFF,
            (FlightType.TRACKED, 1): EVENT_TRACKED_LANDED,
        }

        event_type = event_map.get((sensor_type, current))
        if event_type:
            if sensor_type == FlightType.TRACKED:
                if current == 0:
                    flight['was_airborne'] = True
                elif current == 1:
                    flight['was_airborne'] = True
                    flight['has_landed'] = True
            self._event_manager.add_event(event_type, flight)

    def _get_flight_data(self, flight: dict) -> dict[str, Any] | None:
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
            'airport_origin_country_code': get_country_code(
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
            'airport_destination_country_code': get_country_code(
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
            'details_updated_at': time(),
            # Seed track from FR24 trail (newest-first in API payload).
            'coordinates': self._coordinates_from_trail(flight.get('trail')),
        }

    def _is_valid(self, flight: dict) -> bool:
        if is_helicopter(flight):
            return flight.get("id") is not None

        f_num = flight.get('flight_number')
        sched = flight.get('time_scheduled_departure')
        est = flight.get('time_estimated_arrival')
        updated = flight.get('details_updated_at')

        # Do not require flight_number for the freshness branch: GA/private
        # aircraft often never get one, and gating on it re-fetches details
        # every scan until HTTP 429 (#254).
        return (
            (f_num is not None and sched is not None and est is not None)
            or (
                # flight times are updated rarely so no need to get them every scan
                updated is not None
                and updated > (time() - randint(2, 6) * 60)
            )
        )
