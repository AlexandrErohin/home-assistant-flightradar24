from typing import Any, Callable
from dataclasses import dataclass


@dataclass
class Event:
    event: str
    data: dict[str, Any]


class EventManager:
    __slots__ = ('_events',)

    def __init__(self):
        self._events: list[Event] = []

    def add_events(self, event: str, flights: list[dict[str, Any]]) -> None:
        self._events.extend([Event(event, flight) for flight in flights])

    def fire_events(self, device: str, callback: Callable[[Event], None]) -> None:
        for event in self._events:
            event.data['tracked_by_device'] = device
            callback(event)
        self._events = []
