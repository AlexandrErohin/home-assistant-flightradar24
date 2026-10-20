"""Behaviour while FR24 rate limits the client (HTTP 429, #330 / #254)."""

from logging import getLogger
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from FlightRadarAPI import Entity, FlightRadar24API
import FlightRadarAPI.api as flightradar_api
import pytest

from custom_components.flightradar24.api import client as client_module
from custom_components.flightradar24.api.client import (
    EndpointCooldown,
    FlightRadarClient,
)
from custom_components.flightradar24.api.helper import http_status
from custom_components.flightradar24.const import (
    FAILURE_COOLDOWN,
    RATE_LIMIT_MAX_COOLDOWN,
    REQUEST_ATTEMPTS,
)
from custom_components.flightradar24.coordinator import FlightRadar24Coordinator


class FakeHTTPError(Exception):
    """Shaped like curl_cffi's HTTPError: the response hangs off the error."""

    def __init__(self, status: int, retry_after: str | None = None) -> None:
        super().__init__('HTTP Error {}: '.format(status))
        headers = {}
        if retry_after is not None:
            headers['Retry-After'] = retry_after
        self.response = SimpleNamespace(status_code=status, headers=headers)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def clean_cooldowns():
    client_module._cooldowns.clear()
    client_module._last_request = 0.0
    yield
    client_module._cooldowns.clear()
    client_module._last_request = 0.0


@pytest.fixture
def clock():
    clock = Clock()
    with patch.object(client_module, 'monotonic', clock), patch.object(client_module, 'sleep'):
        yield clock


def make_client(api: MagicMock) -> FlightRadarClient:
    return FlightRadarClient(api, getLogger(__name__))


def test_http_status_reads_the_response_not_the_message():
    assert http_status(FakeHTTPError(429)) == 429
    assert http_status(ValueError('HTTP Error 429: ')) is None


def test_curl_cffi_http_error_carries_the_status():
    """The real exception type the library raises must expose the status code."""
    from curl_cffi.requests.exceptions import HTTPError
    error = HTTPError('HTTP Error 429: ', response=SimpleNamespace(status_code=429))
    assert http_status(error) == 429


def test_429_is_not_retried_and_pauses_the_endpoint(clock):
    api = MagicMock()
    api.get_flights.side_effect = FakeHTTPError(429)
    client = make_client(api)

    with pytest.raises(FakeHTTPError):
        client.get_flights(bounds='1,0,0,1')
    assert api.get_flights.call_count == 1

    clock.now += FAILURE_COOLDOWN - 1
    with pytest.raises(EndpointCooldown):
        client.get_flights(bounds='1,0,0,1')
    assert api.get_flights.call_count == 1

    clock.now += 1
    with pytest.raises(FakeHTTPError):
        client.get_flights(bounds='1,0,0,1')
    assert api.get_flights.call_count == 2


def test_consecutive_429_double_the_pause_up_to_the_cap(clock):
    api = MagicMock()
    api.get_flights.side_effect = FakeHTTPError(429)
    client = make_client(api)

    pauses = []
    for _ in range(8):
        with pytest.raises(FakeHTTPError):
            client.get_flights()
        until, _ = client_module._cooldowns['get_flights']
        pauses.append(until - clock.now)
        clock.now = until

    assert pauses == [30, 60, 120, 240, 480, 900, 900, 900]
    assert RATE_LIMIT_MAX_COOLDOWN == 900


def test_retry_after_extends_the_pause(clock):
    api = MagicMock()
    api.get_flights.side_effect = FakeHTTPError(429, retry_after='120')
    client = make_client(api)

    with pytest.raises(FakeHTTPError):
        client.get_flights()
    until, _ = client_module._cooldowns['get_flights']
    assert until - clock.now == 120


def test_success_resets_the_backoff(clock):
    api = MagicMock()
    api.get_flights.side_effect = [FakeHTTPError(429), FakeHTTPError(429), [], FakeHTTPError(429)]
    client = make_client(api)

    for _ in range(2):
        with pytest.raises(FakeHTTPError):
            client.get_flights()
        clock.now = client_module._cooldowns['get_flights'][0]
    assert client.get_flights() == []
    assert 'get_flights' not in client_module._cooldowns

    with pytest.raises(FakeHTTPError):
        client.get_flights()
    assert client_module._cooldowns['get_flights'][0] - clock.now == FAILURE_COOLDOWN


def test_other_errors_keep_their_retries_then_pause(clock):
    api = MagicMock()
    api.get_flights.side_effect = TimeoutError('timed out')
    client = make_client(api)

    with pytest.raises(TimeoutError):
        client.get_flights()
    assert api.get_flights.call_count == REQUEST_ATTEMPTS
    assert client_module._cooldowns['get_flights'][0] - clock.now == FAILURE_COOLDOWN


def test_cooldown_is_per_endpoint(clock):
    api = MagicMock()
    api.get_flights.side_effect = FakeHTTPError(429)
    api.search.return_value = {'live': []}
    client = make_client(api)

    with pytest.raises(FakeHTTPError):
        client.get_flights()
    assert client.search('BA117') == {'live': []}


def test_cooldown_survives_a_new_session(clock):
    """FR24 limits the IP: a renewed client must not start from a clean slate."""
    first = MagicMock()
    first.get_flights.side_effect = FakeHTTPError(429)
    with pytest.raises(FakeHTTPError):
        make_client(first).get_flights()

    second = MagicMock()
    with pytest.raises(EndpointCooldown):
        make_client(second).get_flights()
    second.get_flights.assert_not_called()


def test_empty_area_costs_one_feed_request():
    """The library's empty-feed retry is off, so an empty small box is one request."""
    assert flightradar_api.FEED_EMPTY_RETRIES == 0

    api = FlightRadar24API()
    response = MagicMock()
    response.get_json_content.return_value = {'full_count': 14990, 'version': 4}
    inner = api._FlightRadar24API__client
    with patch.object(inner, 'request', return_value=response) as request:
        assert api.get_flights(bounds='0.010,0.001,-30.007,-30.000') == []
        assert request.call_count == 1


@pytest.fixture
def coordinator(hass):
    coordinator = FlightRadar24Coordinator(
        hass=hass,
        bounds='1,-1,-1,1',
        client=MagicMock(),
        update_interval=10,
        logger=MagicMock(),
        unique_id='test_rate_limit',
        min_altitude=-1,
        max_altitude=100000,
        point=Entity(0, 0),
    )
    coordinator.config_entry = MagicMock(title='FlightRadar24')
    coordinator._first_start = False
    return coordinator


@pytest.mark.asyncio
async def test_failing_area_does_not_stop_the_tracked_flights(coordinator):
    calls = []
    coordinator.flight = MagicMock()
    coordinator.flight.update_flights_tracked.side_effect = lambda: calls.append('tracked')

    def area():
        calls.append('area')
        raise FakeHTTPError(429)

    coordinator.flight.update_flights_in_area.side_effect = area
    with patch.object(coordinator, '_check_session') as check_session:
        await coordinator._async_update_data()

    assert calls == ['tracked', 'area']
    check_session.assert_not_called()
    coordinator.logger.error.assert_not_called()
    coordinator.logger.debug.assert_called()


@pytest.mark.asyncio
async def test_a_paused_endpoint_is_not_logged_as_an_error_every_scan(coordinator):
    coordinator.flight = MagicMock()
    coordinator.flight.update_flights_tracked.side_effect = EndpointCooldown('get_flights paused')
    coordinator.flight.update_flights_in_area.side_effect = EndpointCooldown('get_flights paused')

    await coordinator._async_update_data()

    coordinator.logger.error.assert_not_called()
    paused = [c for c in coordinator.logger.debug.call_args_list
              if any(isinstance(a, EndpointCooldown) for a in c.args)]
    assert len(paused) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [429, 503])
async def test_setup_survives_a_rate_limited_canary(hass, status):
    """A rate limited IP must not leave every entity unavailable after a restart."""
    from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_RADIUS, CONF_SCAN_INTERVAL
    from homeassistant.exceptions import ConfigEntryNotReady
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.flightradar24 import async_setup_entry
    from custom_components.flightradar24.const import DOMAIN

    api = MagicMock()
    api.get_flights.side_effect = FakeHTTPError(status)
    api.get_bounds_by_point.return_value = '1,-1,-1,1'
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_LATITUDE: 51.5, CONF_LONGITUDE: -0.12, CONF_RADIUS: 1000.0, CONF_SCAN_INTERVAL: 10,
    })
    entry.add_to_hass(hass)

    with patch('custom_components.flightradar24.FlightRadar24API', return_value=api), \
            patch.object(hass.config_entries, 'async_forward_entry_setups', AsyncMock()), \
            patch.object(entry, 'async_create_background_task', side_effect=lambda h, coro, name: coro.close()), \
            patch.object(client_module, 'sleep'):
        if status == 429:
            assert await async_setup_entry(hass, entry) is True
            assert entry.entry_id in hass.data[DOMAIN]
        else:
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)
            assert api.get_flights.call_count == REQUEST_ATTEMPTS
            return
        assert api.get_flights.call_count == 1
