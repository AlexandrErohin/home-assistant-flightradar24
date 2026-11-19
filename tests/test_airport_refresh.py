"""Airport details refresh on their own interval and a timeout is not retried (#347)."""

import asyncio
from logging import getLogger
from unittest.mock import AsyncMock, MagicMock, patch

from curl_cffi.requests.exceptions import HTTPError, Timeout
from FlightRadarAPI import Entity
import pytest

from custom_components.flightradar24 import coordinator as coordinator_module
from custom_components.flightradar24.api import client as client_module
from custom_components.flightradar24.api.client import EndpointCooldown, FlightRadarClient
from custom_components.flightradar24.api.helper import is_timeout
from custom_components.flightradar24.const import (
    AIRPORT_REFRESH_INTERVAL,
    CURL_TIMEOUT_CODE,
    FAILURE_COOLDOWN,
    REQUEST_ATTEMPTS,
)
from custom_components.flightradar24.coordinator import FlightRadar24Coordinator


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
    with patch.object(coordinator_module, 'monotonic', clock):
        yield clock


@pytest.fixture
def coordinator(hass, clock):
    coordinator = FlightRadar24Coordinator(
        hass=hass,
        bounds='1,-1,-1,1',
        client=MagicMock(),
        update_interval=10,
        logger=MagicMock(),
        unique_id='test_airport_refresh',
        min_altitude=-1,
        max_altitude=100000,
        point=Entity(0, 0),
    )
    coordinator.config_entry = MagicMock(title='FlightRadar24')
    coordinator._first_poll = False
    coordinator.flight = MagicMock()
    coordinator.airport = MagicMock()
    return coordinator


async def _refresh_most_and_airport(coordinator):
    """Exercise most-tracked then airport like a normal poll pair."""
    await coordinator._update_most_tracked()
    await coordinator._update_airport()


@pytest.mark.asyncio
async def test_airport_is_not_requested_on_every_poll(coordinator, clock):
    for _ in range(3):
        await _refresh_most_and_airport(coordinator)
        clock.now += 20
    assert coordinator.airport.update_airport_info.call_count == 1
    # The fast feed is untouched by the airport interval.
    assert coordinator.flight.update_most_tracked.call_count == 3

    clock.now += AIRPORT_REFRESH_INTERVAL
    await _refresh_most_and_airport(coordinator)
    assert coordinator.airport.update_airport_info.call_count == 2


@pytest.mark.asyncio
async def test_failed_airport_request_waits_for_the_next_interval(coordinator, clock):
    coordinator.airport.update_airport_info.side_effect = TimeoutError('slow')

    with pytest.raises(TimeoutError):
        await _refresh_most_and_airport(coordinator)
    clock.now += 20
    await _refresh_most_and_airport(coordinator)
    assert coordinator.airport.update_airport_info.call_count == 1

    clock.now += AIRPORT_REFRESH_INTERVAL
    with pytest.raises(TimeoutError):
        await _refresh_most_and_airport(coordinator)
    assert coordinator.airport.update_airport_info.call_count == 2


@pytest.mark.asyncio
async def test_setting_the_airport_refreshes_it_at_once(coordinator, clock):
    await _refresh_most_and_airport(coordinator)
    clock.now += 5

    await coordinator.update_airport_track('LJU')
    coordinator.airport.set_track.assert_called_once_with('LJU')

    # set_track fetched the details, so the next poll does not fetch them again.
    clock.now += 20
    await _refresh_most_and_airport(coordinator)
    assert coordinator.airport.update_airport_info.call_count == 1


@pytest.mark.asyncio
async def test_failed_set_track_does_not_advance_refresh_clock(coordinator, clock):
    """A failed set must not stamp the interval, so the next poll can retry."""
    coordinator.airport.set_track.side_effect = TimeoutError('slow')

    await coordinator.update_airport_track('LJU')

    assert coordinator._airport_last_refresh is None
    await coordinator._update_airport()
    assert coordinator.airport.update_airport_info.call_count == 1


@pytest.mark.asyncio
async def test_poll_does_not_wait_for_airport_hang(coordinator, hass):
    """Listeners for area/tracked must not wait on a slow airport.json (#347)."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocking_airport():
        started.set()
        await release.wait()

    coordinator._airport_last_refresh = None
    with patch.object(coordinator, '_update_tracked', new_callable=AsyncMock), \
            patch.object(coordinator, '_update_area', new_callable=AsyncMock), \
            patch.object(coordinator, '_update_most_tracked', new_callable=AsyncMock), \
            patch.object(coordinator, '_check_session', new_callable=AsyncMock), \
            patch.object(coordinator, '_fetch_airport', side_effect=blocking_airport):
        done = await coordinator._async_update_data()
        assert done is coordinator.data
        await asyncio.wait_for(started.wait(), timeout=1)
        assert coordinator._airport_task is not None
        assert not coordinator._airport_task.done()
        release.set()
        await coordinator._airport_task


@pytest.mark.asyncio
async def test_most_tracked_still_runs_when_airport_would_fail(coordinator, clock):
    """Separate _run paths: airport failure must not skip most-tracked."""
    coordinator.airport.update_airport_info.side_effect = TimeoutError('slow')
    await coordinator._run(coordinator._update_most_tracked)
    assert coordinator.flight.update_most_tracked.call_count == 1
    assert await coordinator._run(coordinator._update_airport) is False
    assert coordinator.airport.update_airport_info.call_count == 1


def test_a_timeout_is_not_retried_and_pauses_the_endpoint():
    api = MagicMock()
    api.get_airport_details.side_effect = Timeout('Operation timed out', CURL_TIMEOUT_CODE)
    client = FlightRadarClient(api, getLogger(__name__))

    with patch.object(client_module, 'sleep') as sleep, pytest.raises(Timeout):
        client.get_airport_details('LJU')
    assert api.get_airport_details.call_count == 1
    sleep.assert_not_called()

    with pytest.raises(EndpointCooldown):
        client.get_airport_details('LJU')
    assert api.get_airport_details.call_count == 1
    assert client_module._cooldown_remaining('get_airport_details') <= FAILURE_COOLDOWN


def test_other_errors_are_still_retried():
    api = MagicMock()
    api.get_airport_details.side_effect = HTTPError('HTTP Error 502: ', 0, MagicMock(status_code=502))
    client = FlightRadarClient(api, getLogger(__name__))

    with patch.object(client_module, 'sleep'), pytest.raises(HTTPError):
        client.get_airport_details('LJU')
    assert api.get_airport_details.call_count == REQUEST_ATTEMPTS


def test_is_timeout_recognises_curl_error_28():
    assert is_timeout(Timeout('timed out'))
    coded = RuntimeError('Failed to perform, curl: (28)')
    coded.code = CURL_TIMEOUT_CODE
    assert is_timeout(coded)
    assert not is_timeout(RuntimeError('boom'))
    assert not is_timeout(HTTPError('HTTP Error 502: ', 0, MagicMock(status_code=502)))
