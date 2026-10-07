"""Setup must retry, not fail permanently, when the FR24 login is rate limited."""

from unittest.mock import MagicMock, patch

from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PASSWORD,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.exceptions import ConfigEntryNotReady
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flightradar24 import async_setup_entry
from custom_components.flightradar24.const import DOMAIN


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
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
        },
    )
    entry.add_to_hass(hass)
    client = MagicMock()
    client.login.side_effect = Exception("HTTP Error 429: ")

    with patch("custom_components.flightradar24.FlightRadar24API", return_value=client):
        with pytest.raises(ConfigEntryNotReady, match="429"):
            await async_setup_entry(hass, entry)

    client.login.assert_called_once_with("user@example.com", "secret")
