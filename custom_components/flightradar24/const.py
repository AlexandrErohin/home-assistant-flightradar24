DEFAULT_NAME = "FlightRadar24"
DOMAIN = "flightradar24"
URL = 'https://www.flightradar24.com/'

CONF_MIN_ALTITUDE = "min_altitude"
CONF_MAX_ALTITUDE = "max_altitude"
CONF_MOST_TRACKED = "most_tracked"
CONF_ENABLE_TRACKER = "enable_tracker"
CONF_AUTO_CLEANUP = "auto_cleanup"
CONF_MOST_TRACKED_DEFAULT = True
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
# Details are the chatty endpoint and the first to get rate limited. Fail fast
# there and let the next cycle retry, instead of blocking the executor for
# RETRY_BASE_DELAY * 2**n seconds per flight.
DETAILS_REQUEST_ATTEMPTS = 1
# A details lookup only enriches the `flights` attribute - the counts come
# straight from the area feed. Cap the lookups per cycle so a busy area, or a
# cold cache right after a restart, can never stretch one update past the scan
# interval. Flights beyond the cap are still counted and get enriched later.
MAX_DETAILS_PER_UPDATE = 25
# Traffic without a schedule (GA, military, ferry flights) never fills the fields
# _is_valid asks for. Stop re-requesting details for such a flight on every
# single cycle after this many fruitless attempts.
DETAILS_MAX_TRIES = 3
