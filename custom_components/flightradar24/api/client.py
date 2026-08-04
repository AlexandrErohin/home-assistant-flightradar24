from FlightRadarAPI import FlightRadar24API, Flight
from ..const import (
    REQUEST_INTERVAL,
    REQUEST_ATTEMPTS,
    RETRY_BASE_DELAY,
)
from logging import Logger
from threading import Lock
from time import sleep, monotonic


class FlightRadarClient:
    __slots__ = ('_client', '_logger', '_last_request', '_lock')

    def __init__(self, client: FlightRadar24API, logger: Logger) -> None:
        self._client = client
        self._logger = logger
        self._last_request: float = 0.0
        self._lock = Lock()

    def get_airport_details(self, code: str) -> dict:
        return self._request('get_airport_details', code)

    def get_flights(self, **kwargs) -> dict:
        return self._request('get_flights', **kwargs)

    def get_flight_details(self, obj: Flight) -> dict:
        return self._request('get_flight_details', obj)

    def search(self, number: str) -> dict:
        return self._request('search', number)

    def get_most_tracked(self) -> dict:
        return self._request('get_most_tracked')

    def _request(self, method_name: str, *args, **kwargs) -> dict:
        for attempt in range(REQUEST_ATTEMPTS):
            # Hold the lock only for the spacing gate, not the HTTP call,
            # so a slow request does not serialize the other callers.
            with self._lock:
                elapsed = monotonic() - self._last_request
                if elapsed < REQUEST_INTERVAL:
                    sleep(REQUEST_INTERVAL - elapsed)
                self._last_request = monotonic()

            try:
                method = getattr(self._client, method_name)
                return method(*args, **kwargs)
            except Exception as e:
                if attempt == REQUEST_ATTEMPTS - 1:
                    self._logger.warning('FlightRadar24: Could not get details for %s - %s', method_name, e)
                    raise e
                sleep(RETRY_BASE_DELAY * (2 ** attempt))

        return None
