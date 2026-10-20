"""Setup must retry, not fail permanently, when the FR24 login is rate limited."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PASSWORD,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flightradar24 import async_setup_entry
from custom_components.flightradar24.const import DOMAIN


def _http_error(status: int) -> Exception:
    error = Exception('HTTP Error {}: '.format(status))
    error.response = SimpleNamespace(status_code=status)  # type: ignore[attr-defined]
    return error


@pytest.mark.asyncio
async def test_login_rate_limit_raises_config_entry_not_ready(hass):
    """An HTTP 429 from login() becomes ConfigEntryNotReady so HA retries setup (#301)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LATITUDE: 52.0,
            CONF_LONGITUDE: 13.0,
            CONF_RADIUS: 1000.0,
            CONF_SCAN_INTERVAL: 20,
            CONF_USERNAME: 'user@example.com',
            CONF_PASSWORD: 'secret',
        },
    )
    entry.add_to_hass(hass)
    client = MagicMock()
    client.login.side_effect = _http_error(429)

    with patch('custom_components.flightradar24.FlightRadar24API', return_value=client):
        with pytest.raises(ConfigEntryNotReady, match='429'):
            await async_setup_entry(hass, entry)

    client.login.assert_called_once_with('user@example.com', 'secret')


@pytest.mark.asyncio
async def test_login_auth_error_is_not_not_ready(hass):
    """401/403 must fail as auth, not an endless NotReady loop (#328)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LATITUDE: 52.0,
            CONF_LONGITUDE: 13.0,
            CONF_RADIUS: 1000.0,
            CONF_SCAN_INTERVAL: 20,
            CONF_USERNAME: 'user@example.com',
            CONF_PASSWORD: 'wrong',
        },
    )
    entry.add_to_hass(hass)
    client = MagicMock()
    client.login.side_effect = _http_error(401)

    with patch('custom_components.flightradar24.FlightRadar24API', return_value=client):
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)
