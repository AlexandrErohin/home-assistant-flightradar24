"""Regression coverage for scan interval validation and stored invalid values."""

from datetime import timedelta
from logging import getLogger
from unittest.mock import MagicMock

from FlightRadarAPI import Entity
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.flightradar24.config_flow import (
    FlightRadarConfigFlow,
)
from custom_components.flightradar24.const import DOMAIN
from custom_components.flightradar24.coordinator import FlightRadar24Coordinator


@pytest.mark.asyncio
@pytest.mark.parametrize("flow_type", ["user", "options"])
@pytest.mark.parametrize("interval", [-19, -1, 0])
async def test_forms_reject_nonpositive_scan_interval(hass, flow_type, interval):
    """Both setup forms reject intervals that would continuously poll the API."""
    data = {
        CONF_LATITUDE: 52.0,
        CONF_LONGITUDE: 13.0,
        CONF_RADIUS: 1000.0,
        CONF_SCAN_INTERVAL: interval,
    }
    if flow_type == "user":
        flow = FlightRadarConfigFlow()
        flow.hass = hass
        form = await flow.async_step_user()
    else:
        entry = MockConfigEntry(domain=DOMAIN, data=data)
        entry.add_to_hass(hass)
        flow = FlightRadarConfigFlow.async_get_options_flow(entry)
        flow.handler = entry.entry_id
        flow.hass = hass
        form = await flow.async_step_init()

    with pytest.raises(vol.Invalid):
        form["data_schema"](data)


@pytest.mark.asyncio
@pytest.mark.parametrize("flow_type", ["user", "options"])
@pytest.mark.parametrize("interval", [1, 20, 60])
async def test_forms_keep_positive_scan_interval(hass, flow_type, interval):
    """Existing positive integer intervals remain valid in both setup forms."""
    data = {
        CONF_LATITUDE: 52.0,
        CONF_LONGITUDE: 13.0,
        CONF_RADIUS: 1000.0,
        CONF_SCAN_INTERVAL: interval,
    }
    if flow_type == "user":
        flow = FlightRadarConfigFlow()
        flow.hass = hass
        form = await flow.async_step_user()
    else:
        entry = MockConfigEntry(domain=DOMAIN, data=data)
        entry.add_to_hass(hass)
        flow = FlightRadarConfigFlow.async_get_options_flow(entry)
        flow.handler = entry.entry_id
        flow.hass = hass
        form = await flow.async_step_init()

    assert form["data_schema"](data)[CONF_SCAN_INTERVAL] == interval


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_interval", "expected_interval"),
    [(-19, 20), (-1, 20), (0, 20), (1, 1), (20, 20), (60, 60)],
)
async def test_coordinator_uses_safe_interval(hass, stored_interval, expected_interval):
    """Old entries with invalid values must recover without reconfiguration."""
    coordinator = FlightRadar24Coordinator(
        hass=hass,
        bounds="53,51,12,14",
        client=MagicMock(),
        update_interval=stored_interval,
        logger=getLogger(__name__),
        unique_id="test_scan_interval",
        min_altitude=-1,
        max_altitude=100000,
        point=Entity(52.0, 13.0),
    )
    assert coordinator.update_interval == timedelta(seconds=expected_interval)
