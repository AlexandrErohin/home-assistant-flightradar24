# CREATED BY DONTRANQUIL
import pytest
from unittest.mock import patch, MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flightradar24.const import DOMAIN
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
)

# =========================================================================
# 1. CONFIG FLOW TESTS
# =========================================================================


@pytest.mark.asyncio
async def test_setup_integration_mocked_api(hass: HomeAssistant):
    """Test that all platforms initialize successfully when the API is mocked."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FlightRadar24",
        data={
            CONF_LATITUDE: 52.0,
            CONF_LONGITUDE: 5.0,
            CONF_RADIUS: 1000.0,
            CONF_SCAN_INTERVAL: 10,
        },
        options={},
        entry_id="fr24_mock_id",
    )
    entry.add_to_hass(hass)

    mock_client = MagicMock()
    mock_client.get_bounds_by_point.return_value = "53.0,51.0,4.0,6.0"

    # We aggressively patch the processors to avoid hitting live flight data loops
    with (
        patch(
            "custom_components.flightradar24.FlightRadar24API", return_value=mock_client
        ),
        patch("custom_components.flightradar24.coordinator.FlightProcessor"),
        patch("custom_components.flightradar24.coordinator.AirportProcessor"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # 1. Verify Switch platform loaded (using correct HA-generated ID)
        scan_switch = hass.states.get("switch.flightradar24_api_data_fetching")
        assert scan_switch is not None
        assert scan_switch.state == "on"

        # 2. Verify Button platform loaded (using correct HA-generated ID)
        clear_button = hass.states.get("button.flightradar24_clear_additional_tracked")
        assert clear_button is not None

        # 3. Verify Text platform loaded (using correct HA-generated ID)
        add_track_text = hass.states.get("text.flightradar24_add_to_track")
        assert add_track_text is not None

        # 4. Verify basic Sensors loaded (using correct HA-generated ID)
        in_area_sensor = hass.states.get("sensor.flightradar24_current_in_area")
        assert in_area_sensor is not None
