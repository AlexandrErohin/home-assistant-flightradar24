from FlightRadarAPI import FlightRadar24API, Flight
import FlightRadarAPI.api as _flightradar_api
from ..const import (
    REQUEST_INTERVAL,
    REQUEST_ATTEMPTS,
    RETRY_BASE_DELAY,
    FAILURE_COOLDOWN,
    RATE_LIMIT_MAX_COOLDOWN,
)
from logging import Logger
from threading import Lock
from time import sleep, monotonic

HTTP_TOO_MANY_REQUESTS = 429

# FlightRadarAPI >= 1.5.2 re-requests an empty feed answer up to
# FEED_EMPTY_RETRIES more times whenever the feed's `full_count` is above zero.
# `full_count` is the worldwide total, not the count inside the requested
# bounds, so a small area that is simply empty costs 1 + 4 back-to-back feed
# requests on every scan (#330). The sticky-empty session that retry targets is
# already handled by the session guard in coordinator.py (#278).
if hasattr(_flightradar_api, 'FEED_EMPTY_RETRIES'):
    _flightradar_api.FEED_EMPTY_RETRIES = 0


class EndpointCooldown(ConnectionError):
    """Raised instead of sending a request while its endpoint is paused."""


def http_status(error: Exception) -> int | None:
    """Status code of the HTTP response attached to the error, if any."""
    response = getattr(error, 'response', None)
    return getattr(response, 'status_code', None)


# FR24 rate limits the IP, not the session. The cooldowns are therefore shared
# by every client in the process: a renewed session or a second config entry
# must not start from a clean slate and hit the limit again.
# endpoint -> (paused until, consecutive HTTP 429 answers)
_cooldowns: dict[str, tuple[float, int]] = {}
_cooldowns_lock = Lock()


def _cooldown_remaining(endpoint: str) -> float:
    with _cooldowns_lock:
        until, _ = _cooldowns.get(endpoint, (0.0, 0))
    return until - monotonic()


def _open_cooldown(endpoint: str, rate_limited: bool) -> tuple[int, int]:
    """Pause the endpoint; return (seconds, consecutive 429 answers).

    A 429 doubles the pause on every further 429 in a row, up to
    RATE_LIMIT_MAX_COOLDOWN, so a rate limited IP actually goes quiet and
    gets out of the limit. Any other failure pauses for FAILURE_COOLDOWN.
    """
    with _cooldowns_lock:
        _, strikes = _cooldowns.get(endpoint, (0.0, 0))
        if rate_limited:
            strikes += 1
            delay = min(FAILURE_COOLDOWN * 2 ** (strikes - 1), RATE_LIMIT_MAX_COOLDOWN)
        else:
            delay = FAILURE_COOLDOWN
        _cooldowns[endpoint] = (monotonic() + delay, strikes)
    return delay, strikes


def _clear_cooldown(endpoint: str) -> None:
    with _cooldowns_lock:
        _cooldowns.pop(endpoint, None)


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
        # The cooldown is kept per endpoint: a paused details endpoint must not
        # take the feed (and with it the tracked flights) down with it.
        remaining = _cooldown_remaining(method_name)
        if remaining > 0:
            raise EndpointCooldown(
                '{} paused for another {:.0f} seconds'.format(method_name, remaining)
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
                # Retrying a 429 within seconds only extends the rate limit.
                if http_status(e) == HTTP_TOO_MANY_REQUESTS:
                    delay, strikes = _open_cooldown(method_name, rate_limited=True)
                    self._logger.warning(
                        'FlightRadar24: %s is rate limited (HTTP 429, %d in a row), pausing it for %d seconds',
                        method_name, strikes, delay,
                    )
                    raise e
                if attempt == REQUEST_ATTEMPTS - 1:
                    delay, _ = _open_cooldown(method_name, rate_limited=False)
                    self._logger.warning(
                        'FlightRadar24: Could not get details for %s - %s; pausing it for %d seconds',
                        method_name, e, delay,
                    )
                    raise e
                sleep(RETRY_BASE_DELAY * (2 ** attempt))
            else:
                _clear_cooldown(method_name)
                return result

        return None
