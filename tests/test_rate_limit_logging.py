"""Coverage for demoting FR24's routine HTTP 429 out of the error log.

FR24 rate-limits the public feed continuously once it throttles a client, so a
429 is an expected answer the next cycle recovers from. Logging it at error
level fills the Home Assistant log and raises repair notices for a non-fault.
Any other failure keeps its original level.
"""

from logging import getLogger
from unittest.mock import MagicMock

from curl_cffi.requests.exceptions import HTTPError
import pytest

from custom_components.flightradar24.api.client import (
    FeedCooldown,
    FlightRadarClient,
    http_status,
)
from custom_components.flightradar24.const import (
    FAILURE_COOLDOWN,
    HTTP_TOO_MANY_REQUESTS,
    REQUEST_ATTEMPTS,
)
from custom_components.flightradar24.coordinator import FlightRadar24Coordinator


def _http_error(status: int) -> HTTPError:
    """Build the error curl_cffi raises from `raise_for_status()`."""
    response = MagicMock()
    response.status_code = status
    return HTTPError(f"HTTP Error {status}: ", 0, response)


def test_http_status_reads_the_attached_response() -> None:
    assert http_status(_http_error(429)) == HTTP_TOO_MANY_REQUESTS
    assert http_status(_http_error(503)) == 503


def test_http_status_is_none_without_a_response() -> None:
    """A status must never be inferred from the message text."""
    assert http_status(ValueError("HTTP Error 429:")) is None
    assert http_status(HTTPError("boom", 0, None)) is None


def test_http_status_ignores_a_non_integer_status() -> None:
    response = MagicMock()
    response.status_code = "429"
    assert http_status(HTTPError("boom", 0, response)) is None


@pytest.mark.parametrize(
    ('status', 'expected_level'),
    [(429, 'debug'), (503, 'warning')],
)
def test_client_logs_rate_limit_at_debug(status, expected_level, monkeypatch) -> None:
    """The client keeps the method name but drops a 429 to debug."""
    monkeypatch.setattr(
        'custom_components.flightradar24.api.client.sleep', lambda _seconds: None
    )
    logger = MagicMock()
    api = MagicMock()
    api.get_flights.side_effect = _http_error(status)
    client = FlightRadarClient(api, logger)

    with pytest.raises(HTTPError):
        client.get_flights(bounds='1,2,3,4')

    # Still raises after exhausting the retries, so the caller backs off.
    assert api.get_flights.call_count == REQUEST_ATTEMPTS

    used = getattr(logger, expected_level)
    unused = getattr(logger, 'warning' if expected_level == 'debug' else 'debug')
    assert used.call_count == 1
    assert 'get_flights' in used.call_args.args
    assert unused.call_count == 0
    assert logger.error.call_count == 0


@pytest.mark.parametrize(
    ('error', 'expected_level'),
    [
        (_http_error(429), 'debug'),
        (_http_error(503), 'error'),
        (ValueError('bad payload'), 'error'),
    ],
)
def test_coordinator_demotes_only_the_rate_limit(error, expected_level) -> None:
    """Unexpected failures must stay loud; only the 429 goes quiet."""
    coordinator = MagicMock()
    coordinator.logger = MagicMock()

    FlightRadar24Coordinator._log_api_error(coordinator, error)

    assert getattr(coordinator.logger, expected_level).call_count == 1
    for level in ('debug', 'error'):
        if level != expected_level:
            assert getattr(coordinator.logger, level).call_count == 0


def test_rate_limit_never_reaches_the_error_log() -> None:
    """End to end over the real logger: a 429 produces no error record."""
    logger = getLogger('flightradar24.test.rate_limit')
    coordinator = MagicMock()
    coordinator.logger = logger

    records = []
    handler = type('Collect', (), {
        'handle': lambda _self, record: records.append(record),
        'level': 0,
        'filters': [],
        'lock': None,
        'acquire': lambda _self: None,
        'release': lambda _self: None,
    })()
    logger.addHandler(handler)
    logger.setLevel('DEBUG')
    try:
        FlightRadar24Coordinator._log_api_error(coordinator, _http_error(429))
    finally:
        logger.removeHandler(handler)

    assert [record.levelname for record in records] == ['DEBUG']


def test_breaker_skips_the_endpoint_during_cooldown(monkeypatch) -> None:
    """A throttled endpoint is skipped instead of burning its backoff again."""
    monkeypatch.setattr(
        'custom_components.flightradar24.api.client.sleep', lambda _seconds: None
    )
    api = MagicMock()
    api.get_flights.side_effect = _http_error(429)
    client = FlightRadarClient(api, MagicMock())

    with pytest.raises(HTTPError):
        client.get_flights(bounds='1,2,3,4')
    assert api.get_flights.call_count == REQUEST_ATTEMPTS

    # Second call must not reach FR24 at all.
    with pytest.raises(FeedCooldown):
        client.get_flights(bounds='1,2,3,4')
    assert api.get_flights.call_count == REQUEST_ATTEMPTS


def test_cooldown_is_per_endpoint(monkeypatch) -> None:
    """A throttled details endpoint must not take the area feed down with it."""
    monkeypatch.setattr(
        'custom_components.flightradar24.api.client.sleep', lambda _seconds: None
    )
    api = MagicMock()
    api.get_flight_details.side_effect = _http_error(429)
    api.get_flights.return_value = {'full_count': 1}
    client = FlightRadarClient(api, MagicMock())

    with pytest.raises(HTTPError):
        client.get_flight_details(MagicMock())

    assert client.get_flights(bounds='1,2,3,4') == {'full_count': 1}


def test_cooldown_expires(monkeypatch) -> None:
    clock = {'now': 1000.0}
    monkeypatch.setattr(
        'custom_components.flightradar24.api.client.sleep', lambda _seconds: None
    )
    monkeypatch.setattr(
        'custom_components.flightradar24.api.client.monotonic',
        lambda: clock['now'],
    )
    api = MagicMock()
    api.get_flights.side_effect = _http_error(429)
    client = FlightRadarClient(api, MagicMock())

    with pytest.raises(HTTPError):
        client.get_flights(bounds='1,2,3,4')
    with pytest.raises(FeedCooldown):
        client.get_flights(bounds='1,2,3,4')

    clock['now'] += FAILURE_COOLDOWN + 1
    api.get_flights.side_effect = None
    api.get_flights.return_value = {'full_count': 2}
    assert client.get_flights(bounds='1,2,3,4') == {'full_count': 2}


def test_success_clears_the_cooldown(monkeypatch) -> None:
    """A recovered endpoint must not stay broken for the rest of the session."""
    monkeypatch.setattr(
        'custom_components.flightradar24.api.client.sleep', lambda _seconds: None
    )
    api = MagicMock()
    api.get_flights.return_value = {'full_count': 3}
    client = FlightRadarClient(api, MagicMock())

    client._broken_until['get_flights'] = 0.0
    assert client.get_flights(bounds='1,2,3,4') == {'full_count': 3}
    assert 'get_flights' not in client._broken_until


def test_cooldown_stays_out_of_the_error_log() -> None:
    """The breaker firing is the fix working, not a new fault."""
    coordinator = MagicMock()
    coordinator.logger = MagicMock()

    FlightRadar24Coordinator._log_api_error(
        coordinator, FeedCooldown('get_flights is in cooldown after repeated failures')
    )

    assert coordinator.logger.debug.call_count == 1
    assert coordinator.logger.error.call_count == 0


def test_a_real_connection_error_still_reaches_the_error_log() -> None:
    """FeedCooldown subclasses ConnectionError; only the subclass goes quiet."""
    coordinator = MagicMock()
    coordinator.logger = MagicMock()

    FlightRadar24Coordinator._log_api_error(coordinator, ConnectionError('no route to host'))

    assert coordinator.logger.error.call_count == 1
    assert coordinator.logger.debug.call_count == 0
