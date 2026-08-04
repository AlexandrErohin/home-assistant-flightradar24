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
    CANARY_BOUNDS,
    SESSION_GUARD_EMPTY_SECONDS,
    SESSION_GUARD_CHECK_THROTTLE,
    SESSION_SETUP_MAX_TRIES,
)
from .api.client import FlightRadarClient
from .api.event import EventManager, Event
from .api.flight import FlightProcessor
from .api.airport import AirportProcessor
from logging import Logger
from FlightRadarAPI import FlightRadar24API, Entity


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
            session_verified: bool = True,
            auto_cleanup: bool = False,
    ) -> None:
        self.unique_id = unique_id
        self.event_manager = EventManager()
        self.flight = FlightProcessor(client, self.event_manager, min_altitude, max_altitude, point, bounds,
                                      auto_cleanup)
        self.airport = AirportProcessor(client)
        self.enable_tracker: bool = False
        self.scanning: bool = True
        # Setup no longer fails on an unverified session (that would leave every
        # entity unavailable through HA's retry backoff). Instead, pretend the
        # feed has been empty for a full window so the very first empty cycle
        # runs the canary and swaps the session out straight away.
        self._guard_last_seen: float = (
            monotonic() if session_verified else monotonic() - SESSION_GUARD_EMPTY_SECONDS
        )
        self._guard_last_check: float = 0.0
        self._first_start: bool = True
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

        if self._first_start:
            try:
                await self._update_most_tracked_and_airport()
            except Exception as e:
                self.logger.error("FlightRadar24: %s", e)

            try:
                await self._update_area_and_tracked()
                await self._check_session()
            except Exception as e:
                self.logger.error("FlightRadar24: %s", e)
        else:
            try:
                await self._update_area_and_tracked()
            except Exception as e:
                self.logger.error("FlightRadar24: %s", e)

            try:
                await self._update_most_tracked_and_airport()
                await self._check_session()
            except Exception as e:
                self.logger.error("FlightRadar24: %s", e)

        self._first_start = False

    async def _update_most_tracked_and_airport(self) -> None:
        await self.hass.async_add_executor_job(self.flight.update_most_tracked)
        self.async_set_updated_data(self.flight.most_tracked_list)
        self.event_manager.fire_events(self.config_entry.title, self._fire)

        await self.hass.async_add_executor_job(self.airport.update_airport_info)
        self.async_set_updated_data(self.airport)

    async def _update_area_and_tracked(self) -> None:
        await self.hass.async_add_executor_job(self.flight.update_flights_in_area)
        self.async_set_updated_data(self.flight.in_area_list)
        self.async_set_updated_data(self.flight.entered_list)
        self.async_set_updated_data(self.flight.exited_list)
        self.event_manager.fire_events(self.config_entry.title, self._fire)

        await self.hass.async_add_executor_job(self.flight.update_flights_tracked)
        self.async_set_updated_data(self.flight.tracked)
        self.async_set_updated_data(self.flight.tracked_list)
        self.event_manager.fire_events(self.config_entry.title, self._fire)

    def _fire(self, event: Event) -> None:
        self.hass.bus.fire(event.event, event.data)

    def _renew_client(self) -> FlightRadarClient:
        client = FlightRadar24API()
        username = self.config_entry.data.get(CONF_USERNAME)
        password = self.config_entry.data.get(CONF_PASSWORD)
        if username and password:
            client.login(username, password)
        return FlightRadarClient(client, self.logger)

    def _renew_verified_client(self) -> tuple[FlightRadarClient, bool]:
        """Create a replacement session and canary-verify it before handing it over.

        Without this, a bad session replaced by another bad session (the dice
        roll is ~1 in 5 per fresh session) would sit unnoticed until the guard's
        next throttle window - half an hour of zeros. Bounded like setup.
        """
        client = None
        for attempt in range(1, SESSION_SETUP_MAX_TRIES + 1):
            client = self._renew_client()
            try:
                if is_session_healthy(client):
                    return client, True
            except Exception as e:
                self.logger.warning('FlightRadar24: could not verify the replacement session - %s', e)
                return client, False
            self.logger.warning(
                'FlightRadar24: replacement session is empty as well (bot mitigation), recreating (%d/%d)',
                attempt, SESSION_SETUP_MAX_TRIES,
            )
        return client, False

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
        client, verified = await self.hass.async_add_executor_job(self._renew_verified_client)
        self.flight.update_client(client)
        self.airport.update_client(client)
        if verified:
            # A verified session earns a fresh observation window; an unverified
            # one keeps the timers as they are, so the guard re-checks it after
            # the next throttle window instead of trusting it for a full one.
            self._guard_last_seen = monotonic()
