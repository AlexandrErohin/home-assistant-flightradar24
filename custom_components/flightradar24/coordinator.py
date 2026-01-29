from __future__ import annotations
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.device_registry import DeviceInfo
from .const import (
    DOMAIN,
    URL,
    DEFAULT_NAME,
)
from .api.event import EventManager, Event
from .api.flight import FlightProcessor
from .api.airport import AirportProcessor
from logging import Logger
from FlightRadar24 import FlightRadar24API, Entity


class FlightRadar24Coordinator(DataUpdateCoordinator[int]):

    def __init__(
            self,
            hass: HomeAssistant,
            bounds: str,
            client: FlightRadar24API,
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

    async def _async_update_data(self):
        if not self.scanning:
            return
        try:
            await self.hass.async_add_executor_job(self.flight.update_flights_in_area)
            await self.hass.async_add_executor_job(self.flight.update_flights_tracked)
            await self.hass.async_add_executor_job(self.flight.update_most_tracked)
            await self.hass.async_add_executor_job(self.airport.update_airport_info)
        except Exception as e:
            self.logger.error("FlightRadar24: %s", e)

        def fire(event: Event) -> None:
            self.hass.bus.fire(event.event, event.data)

        self.event_manager.fire_events(self.config_entry.title, fire)
