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
    FlightRadarClient,
    http_status,
)
from custom_components.flightradar24.const import (
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
