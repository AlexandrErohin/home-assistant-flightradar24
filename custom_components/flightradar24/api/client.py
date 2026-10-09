from FlightRadarAPI import FlightRadar24API, Flight
from ..const import (
    FAILURE_COOLDOWN,
    HTTP_TOO_MANY_REQUESTS,
    REQUEST_INTERVAL,
    REQUEST_ATTEMPTS,
    RETRY_BASE_DELAY,
)
from logging import Logger
from threading import Lock
from time import sleep, monotonic


class FeedCooldown(ConnectionError):
    """Raised instead of calling an endpoint that is still in cooldown.

    It reports the circuit breaker doing its job, not a new fault, so it is
    logged at debug like the rate limit that opened the breaker.
    """


def http_status(error: BaseException) -> int | None:
    """Return the HTTP status carried by *error*, or None if it carries none.

    curl_cffi raises HTTPError with the response attached, so the status is
    readable without matching on the message text.
    """
    status = getattr(getattr(error, 'response', None), 'status_code', None)
    return status if isinstance(status, int) else None


class FlightRadarClient:
    __slots__ = ('_client', '_logger', '_last_request', '_lock', '_broken_until')

    def __init__(self, client: FlightRadar24API, logger: Logger) -> None:
        self._client = client
        self._logger = logger
        self._last_request: float = 0.0
        self._lock = Lock()
        # Per endpoint, not global: the details endpoint is rate limited long
        # before the area feed is, and a shared breaker would stop the feed as
        # well - which is what leaves the in area / entered / exited sensors
        # sitting at 0 for as long as the details endpoint is unhappy.
        self._broken_until: dict[str, float] = {}

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
        # Skip an endpoint that just exhausted its retries instead of letting
        # every remaining call of the cycle burn its own backoff. While FR24
        # throttles, that is what keeps the feed throttled.
        if monotonic() < self._broken_until.get(method_name, 0.0):
            raise FeedCooldown(
                '{} is in cooldown after repeated failures'.format(method_name)
            )

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
                result = method(*args, **kwargs)
            except Exception as e:
                if attempt == REQUEST_ATTEMPTS - 1:
                    self._broken_until[method_name] = monotonic() + FAILURE_COOLDOWN
                    # Rate limiting is expected on the public feed - keep it out
                    # of the error log, but still raise so the caller backs off.
                    log = (self._logger.debug
                           if http_status(e) == HTTP_TOO_MANY_REQUESTS
                           else self._logger.warning)
                    log('FlightRadar24: Could not get details for %s - %s', method_name, e)
                    raise e
                sleep(RETRY_BASE_DELAY * (2 ** attempt))
            else:
                self._broken_until.pop(method_name, None)
                return result

        return None
