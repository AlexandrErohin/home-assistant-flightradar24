from __future__ import annotations

import re
from typing import Any


def normalize_flight_key(value: Any) -> str:
    """Normalize a flight identifier for stable Home Assistant unique IDs."""
    return re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower()).strip("_")


def flight_tracker_key(flight: dict[str, Any]) -> str | None:
    """Return a stable key for a recurring tracked flight."""
    for field in ("flight_number", "callsign", "aircraft_registration", "id"):
        if value := flight.get(field):
            if normalized := normalize_flight_key(value):
                return f"{field}_{normalized}"
    return None


def flight_display_name(flight: dict[str, Any]) -> str:
    """Return a readable name for a tracked flight sensor."""
    return (
        flight.get("flight_number")
        or flight.get("callsign")
        or flight.get("aircraft_registration")
        or flight.get("id")
        or "Tracked flight"
    )
