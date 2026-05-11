DEFAULT_NAME = "FlightRadar24"
DOMAIN = "flightradar24"
URL = 'https://www.flightradar24.com/'

CONF_MIN_ALTITUDE = "min_altitude"
CONF_MAX_ALTITUDE = "max_altitude"
CONF_MOST_TRACKED = "most_tracked"
CONF_ENABLE_TRACKER = "enable_tracker"
CONF_MOST_TRACKED_DEFAULT = True
CONF_ENABLE_TRACKER_DEFAULT = False

EVENT_ENTRY = f"{DOMAIN}_entry"
EVENT_EXIT = f"{DOMAIN}_exit"
EVENT_AREA_LANDED = f"{DOMAIN}_area_landed"
EVENT_AREA_TOOK_OFF = f"{DOMAIN}_area_took_off"
EVENT_TRACKED_LANDED = f"{DOMAIN}_tracked_landed"
EVENT_TRACKED_TOOK_OFF = f"{DOMAIN}_tracked_took_off"
EVENT_MOST_TRACKED_NEW = f"{DOMAIN}_most_tracked_new"

MIN_ALTITUDE = -1
MAX_ALTITUDE = 100000
