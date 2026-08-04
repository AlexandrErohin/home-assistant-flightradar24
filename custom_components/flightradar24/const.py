from pathlib import Path
import json

DEFAULT_NAME = "FlightRadar24"
DOMAIN = "flightradar24"
URL = 'https://www.flightradar24.com/'

with open(Path(__file__).parent / "manifest.json", encoding="utf-8") as _manifest:
    INTEGRATION_VERSION = json.load(_manifest).get("version", "0.0.0")

# Lovelace card static path and modules
URL_BASE = f"/{DOMAIN}"
JSMODULES = [
    {
        "name": "Flightradar24 Card",
        "filename": "flightradar24-card.js",
        "version": INTEGRATION_VERSION,
    },
]

CONF_MIN_ALTITUDE = "min_altitude"
CONF_MAX_ALTITUDE = "max_altitude"
CONF_ENABLE_TRACKER = "enable_tracker"
CONF_AUTO_CLEANUP = "auto_cleanup"
CONF_ENABLE_TRACKER_DEFAULT = False
CONF_AUTO_CLEANUP_DEFAULT = False

CONF_TRACKER_NAME_STYLE = "tracker_name_style"
TRACKER_NAME_CALLSIGN = "callsign"
TRACKER_NAME_CALLSIGN_ROUTE = "callsign_route"
TRACKER_NAME_REG_ROUTE = "reg_route"
CONF_TRACKER_NAME_DEFAULT = TRACKER_NAME_CALLSIGN

TRACKER_NAME_OPTIONS = [
    TRACKER_NAME_CALLSIGN,
    TRACKER_NAME_CALLSIGN_ROUTE,
    TRACKER_NAME_REG_ROUTE,
]

EVENT_ENTRY = f"{DOMAIN}_entry"
EVENT_EXIT = f"{DOMAIN}_exit"
EVENT_AREA_LANDED = f"{DOMAIN}_area_landed"
EVENT_AREA_TOOK_OFF = f"{DOMAIN}_area_took_off"
EVENT_TRACKED_LANDED = f"{DOMAIN}_tracked_landed"
EVENT_TRACKED_TOOK_OFF = f"{DOMAIN}_tracked_took_off"
EVENT_MOST_TRACKED_NEW = f"{DOMAIN}_most_tracked_new"
EVENT_TRACKED_ARRIVED_GATE = f"{DOMAIN}_tracked_arrived_gate"
EVENT_TRACKED_LEFT_GATE = f"{DOMAIN}_tracked_left_gate"

MIN_ALTITUDE = -1
MAX_ALTITUDE = 100000

# FR24's bot mitigation can hand out a session that only ever receives valid
# but empty feed responses, and a session keeps that fate for its entire
# lifetime (issues #278 / #271). A session is considered healthy when it sees
# traffic in at least one of these bounds (y1,y2,x1,x2) - regions busy enough
# that a healthy session never finds all of them empty, no matter the time of day.
CANARY_BOUNDS = [
    '54.0,44.0,-2.0,20.0',    # Central/Western Europe
    '42.0,30.0,-95.0,-75.0',  # US East
]
# Keep this low: every attempt costs blocking requests inside async_setup_entry,
# and an unverified session is no longer a reason to fail setup - the runtime
# guard below recovers it without leaving every entity unavailable meanwhile.
SESSION_SETUP_MAX_TRIES = 2
# Runtime guard: only canary-check when the area feed has been empty this long,
# and at most once per throttle window, to keep extra API calls negligible.
SESSION_GUARD_EMPTY_SECONDS = 1800
SESSION_GUARD_CHECK_THROTTLE = 1800

# Flightradar24 rate limits clients that request flight details too quickly.
# Space the per-flight detail lookups out and retry them with a backoff instead
# of letting a single failure abort the whole update cycle.
REQUEST_INTERVAL = 0.2
REQUEST_ATTEMPTS = 3
RETRY_BASE_DELAY = 2
# Once a request has exhausted its retries, fail fast for this long instead of
# letting every remaining call of the cycle burn its own backoff (circuit breaker).
# The cooldown is kept per endpoint - a rate limited details endpoint must not
# take the area feed (and with it every count sensor) down with it.
FAILURE_COOLDOWN = 30

# Per-flight position history stored on each flight dict as `coordinates`
# ([[lat, lon], ...]). Capped so sensor attributes stay bounded.
COORDINATES_MAX_POINTS = 50
