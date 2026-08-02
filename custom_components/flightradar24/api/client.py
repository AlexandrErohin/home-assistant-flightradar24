from FlightRadar24 import FlightRadar24API, Flight
from ..const import (
    REQUEST_INTERVAL,
    REQUEST_ATTEMPTS,
    RETRY_BASE_DELAY,
    FAILURE_COOLDOWN,
    DETAILS_REQUEST_ATTEMPTS,
)
from logging import Logger
from threading import Lock
from time import sleep, monotonic


class FlightRadarClient:
    __slots__ = ('_client', '_logger', '_last_request', '_lock', '_broken_until')

    def __init__(self, client: FlightRadar24API, logger: Logger) -> None:
        self._client = client
        self._logger = logger
        self._last_request: float = 0.0
        self._lock = Lock()
        # Per endpoint, not global: get_flight_details is rate limited long
        # before the area feed is, and a shared breaker would stop the feed as
        # well - which is what leaves the in area / entered / exited sensors
        # sitting at 0 for as long as the details endpoint is unhappy.
        self._broken_until: dict[str, float] = {}

    def get_airport_details(self, code: str) -> dict:
        return self._request('get_airport_details', code)

    def get_flights(self, **kwargs) -> dict:
        return self._request('get_flights', **kwargs)

    def get_flight_details(self, obj: Flight) -> dict:
        return self._request('get_flight_details', obj, attempts=DETAILS_REQUEST_ATTEMPTS)

    def search(self, number: str) -> dict:
        return self._request('search', number)

    def get_most_tracked(self) -> dict:
        return self._request('get_most_tracked')

    def _request(self, method_name: str, *args, attempts: int = REQUEST_ATTEMPTS, **kwargs) -> dict:
        broken_until = self._broken_until.get(method_name, 0.0)
        if monotonic() < broken_until:
            raise ConnectionError('{} is in cooldown after repeated failures'.format(method_name))

        for attempt in range(attempts):
            # Hold the lock only for the spacing gate, not the HTTP call,
            # so a slow request does not serialize the other callers.
            with self._lock:
                elapsed = monotonic() - self._last_request
                if elapsed < REQUEST_INTERVAL:
                    sleep(REQUEST_INTERVAL - elapsed)
                self._last_request = monotonic()

            try:
                method = getattr(self._client, method_name)
                result = method(*args, **kwargs)
            except Exception as e:
                if attempt == attempts - 1:
                    self._broken_until[method_name] = monotonic() + FAILURE_COOLDOWN
                    self._logger.warning('FlightRadar24: Could not get details for %s - %s', method_name, e)
                    raise e
                sleep(RETRY_BASE_DELAY * (2 ** attempt))
            else:
                self._broken_until.pop(method_name, None)
                return result

        return None
