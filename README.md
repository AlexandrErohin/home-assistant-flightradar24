# Cached Flightradar24 Integration for Home Assistant

This is a fork of the original [Flightradar24 integration](https://github.com/AlexandrErohin/home-assistant-flightradar24) by [AlexandrErohin](https://github.com/AlexandrErohin), extended with request‑throttling and caching to reduce 429 API errors.

Track flights around your home or specific aircraft, get Home Assistant events when flights enter, exit, land or take off, and optionally monitor the most‑tracked flights.

## Key features

- Follow flights in a defined area with altitude limits and a center point.
- Track individual aircraft by registration, callsign, or flight number.
- Receive events:
  - `flight_radar24_entry` and `_exit`
  - `flight_radar24_area_landed` and `_area_took_off`
  - `flight_radar24_tracked_landed` and `_tracked_took_off`
  - `flight_radar24_most_tracked_new`
- Caching and cooldown logic to avoid 429 errors:
  - Tracked flights: detail data refreshed at most every 10 minutes.
  - Flights in area: detail data refreshed at most every 30 minutes.
  - Failed detail calls back off for 1 hour, using cached data in the meantime.

## Installation via HACS

[![Open your Home Assistant instance and open Flightradar24 integration in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=melounusaty&repository=home-assistant-flightradar24&category=integration)

1. In HACS, go to **Settings** → **Custom repositories**.
2. Add:
   - Repository: `melounusaty/home-assistant-flightradar24`
   - Category: `Integration`
3. Click **Add** and then install the integration.

## Manual install (optional)

```sh
git clone https://github.com/melounusaty/home-assistant-flightradar24.git
cp -r home-assistant-flightradar24/custom_components/flight_radar24 /config/custom_components/
```

Restart Home Assistant.

## Configuration of the integration

- Radius in meters
- Latitude (eg. 40.0755367)
- Longtitude (eg. 16.4378)
- Scan interval for telemetry updates in seconds
- The minimum altitude in feet abowe all aircraft will be tracked
- The maximum altitude in feed bellow all aircraft will be tracked
- username: "your_fr24_login" # optional - currently not being used for anything
- password: "your_fr24_password"  # optional - currently not being used for anything
- Enable Most Tracked Flight list
- Enable Device_tracker for additional tracking # optional - required for tracking specific flights

## Configuration of the FlightRadar24 device added by integration

- Add to track # add flight - ie BA123)
- Airport track # add airport code in IATA or ICAO format (Ie LAX or KLAX, AMS or EHAM)
- Enable API data fetching
- Clear Additional Tracked
- Remove from track 

Entities created:

- `sensor.flightradar24_in_area`
- `sensor.flightradar24_tracked`
- `sensor.flightradar24_most_tracked`

After restart, the integration will start polling and updating these sensors.

## License and credits

Forked from [AlexandrErohin/home-assistant-flightradar24](https://github.com/AlexandrErohin/home-assistant-flightradar24).  
Modifications by `melounusaty`, including the request‑throttling and caching logic.  
MIT‑licensed.
