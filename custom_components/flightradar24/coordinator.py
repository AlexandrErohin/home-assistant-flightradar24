from __future__ import annotations
from datetime import timedelta
from time import monotonic
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from .const import (
    DOMAIN,
    URL,
    DEFAULT_NAME,
    CONF_AUTO_CLEANUP,
    CONF_AUTO_CLEANUP_DEFAULT,
    CANARY_BOUNDS,
    SESSION_GUARD_EMPTY_SECONDS,
    SESSION_GUARD_CHECK_THROTTLE,
)
from .api.client import FlightRadarClient
from .api.event import EventManager, Event
from .api.flight import FlightProcessor
from .api.airport import AirportProcessor
from logging import Logger
from FlightRadar24 import FlightRadar24API, Entity


def is_session_healthy(client: FlightRadarClient) -> bool:
    """Blocking canary check for the sticky empty-session issue (#278, #271).

    FR24's bot mitigation randomly hands out sessions that only ever receive
    valid but empty feed responses. A healthy session sees traffic in at least
    one of the known-busy canary regions.
    """
    for bounds in CANARY_BOUNDS:
        if client.get_flights(bounds=bounds):
            return True
    return False


class FlightRadar24Coordinator(DataUpdateCoordinator[int]):

    def __init__(
            self,
            hass: HomeAssistant,
            bounds: str,
            client: FlightRadarClient,
            update_interval: int,
            logger: Logger,
            unique_id: str,
            min_altitude: int,
            max_altitude: int,
            point: Entity,
    ) -> None:
        self.unique_id = unique_id
        self.event_manager = EventManager()
        self.flight = FlightProcessor(client, self.event_manager, min_altitude, max_altitude, point, bounds)
        self.airport = AirportProcessor(client)
        self.enable_tracker: bool = False
        self.scanning: bool = True
        self._guard_last_seen: float = monotonic()
        self._guard_last_check: float = 0.0
        self.device_info = DeviceInfo(
            configuration_url=URL,
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=DEFAULT_NAME,
            name=DEFAULT_NAME,
        )

        super().__init__(
            hass,
            logger,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def add_flight_track(self, number: str) -> None:
        if not self.scanning:
            self.logger.error('FlightRadar24: API data fetching if OFF')
            return
        try:
            found = await self.hass.async_add_executor_job(self.flight.add_track, number)
            if not found:
                self.logger.error('FlightRadar24: Add Track - No flight found by - {}'.format(number))
        except Exception as e:
            self.logger.error("FlightRadar24: %s", e)

    async def remove_flight_track(self, number: str) -> None:
        if not self.scanning:
            self.logger.error('FlightRadar24: API data fetching if OFF')
            return

        remove = await self.hass.async_add_executor_job(self.flight.remove_track, number)
        if not remove:
            self.logger.error('FlightRadar24: Remove Track - No flight found by - {}'.format(number))

    async def update_airport_track(self, code: str) -> None:
        if not self.scanning:
            self.logger.error('FlightRadar24: API data fetching if OFF')
            return

        try:
            if not code:
                await self.hass.async_add_executor_job(self.airport.remove_track)
            else:
                await self.hass.async_add_executor_job(self.airport.set_track, code)
        except Exception as e:
            self.logger.error("FlightRadar24: %s", e)
            return

        self.async_set_updated_data(self.data)

    async def _async_update_data(self):
        if not self.scanning:
            return

        self.flight._auto_cleanup = self.config_entry.data.get(CONF_AUTO_CLEANUP, CONF_AUTO_CLEANUP_DEFAULT)

        try:
            await self.hass.async_add_executor_job(self.flight.update_flights_in_area)
            await self.hass.async_add_executor_job(self.flight.update_flights_tracked)
            await self.hass.async_add_executor_job(self.flight.update_most_tracked)
            await self.hass.async_add_executor_job(self.airport.update_airport_info)
            await self._check_session()
        except Exception as e:
            self.logger.error("FlightRadar24: %s", e)

        def fire(event: Event) -> None:
            self.hass.bus.fire(event.event, event.data)

        self.event_manager.fire_events(self.config_entry.title, fire)

    def _renew_client(self) -> FlightRadarClient:
        client = FlightRadar24API()
        username = self.config_entry.data.get(CONF_USERNAME)
        password = self.config_entry.data.get(CONF_PASSWORD)
        if username and password:
            client.login(username, password)
        return FlightRadarClient(client, self.logger)

    async def _check_session(self) -> None:
        """Detect a session gone sticky-empty at runtime and replace it (#278).

        Cheap by design: no extra requests at all while the area feed sees
        traffic; once it has been empty for SESSION_GUARD_EMPTY_SECONDS, run
        the canary at most once per SESSION_GUARD_CHECK_THROTTLE.
        """
        now = monotonic()
        if self.flight.raw_in_area_count > 0:
            self._guard_last_seen = now
            return
        if (now - self._guard_last_seen < SESSION_GUARD_EMPTY_SECONDS
                or now - self._guard_last_check < SESSION_GUARD_CHECK_THROTTLE):
            return
        self._guard_last_check = now
        if await self.hass.async_add_executor_job(is_session_healthy, self.flight.client):
            return
        self.logger.warning(
            'FlightRadar24: session only receives empty feed data (bot mitigation), recreating session'
        )
        client = await self.hass.async_add_executor_job(self._renew_client)
        self.flight.update_client(client)
        self.airport.update_client(client)
