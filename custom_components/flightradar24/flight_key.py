from __future__ import annotations

import re
from typing import Any

TRACKING_KEY = "tracking_key"


def normalize_flight_key(value: Any) -> str:
    """Normalize a flight identifier for stable Home Assistant unique IDs."""
    return re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower()).strip("_")


def tracked_input_key(value: Any) -> str | None:
    """Return a stable key based on the value the user asked to track."""
    if normalized := normalize_flight_key(value):
        return f"tracked_{normalized}"
    return None


def flight_tracker_key(flight: dict[str, Any]) -> str | None:
    """Return a stable key for a recurring tracked flight."""
    if tracking_key := flight.get(TRACKING_KEY):
        return tracking_key

    for field in ("flight_number", "callsign", "aircraft_registration", "id"):
        if value := flight.get(field):
            if normalized := normalize_flight_key(value):
                return f"{field}_{normalized}"
    return None


def ensure_tracking_key(
        flight: dict[str, Any],
        fallback: Any = None,
        prefer_fallback: bool = False,
) -> str | None:
    """Set and return the stable key for a tracked flight."""
    if tracking_key := flight.get(TRACKING_KEY):
        return tracking_key

    if prefer_fallback:
        tracking_key = tracked_input_key(fallback) or flight_tracker_key(flight)
    else:
        tracking_key = flight_tracker_key(flight) or tracked_input_key(fallback)
    if tracking_key:
        flight[TRACKING_KEY] = tracking_key
    return tracking_key


def flight_display_name(flight: dict[str, Any]) -> str:
    """Return a readable name for a tracked flight sensor."""
    return (
        flight.get("flight_number")
        or flight.get("callsign")
        or flight.get("aircraft_registration")
        or flight.get("id")
        or "Tracked flight"
    )
