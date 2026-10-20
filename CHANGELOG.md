# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Added

- Map card option `show_area` to hide the monitored area outline and tint; default remains visible ([#336](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/336), [#339](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/339))
- Map card options `altitude_unit`, `distance_unit`, and `speed_unit` for independent display units in the flight list and popups ([#326](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/326), [#337](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/337))
- Map card shows a helicopter icon in the flight list and on the map when `aircraft_category` is `Helicopter` ([#340](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/340))
- Local brand assets under `custom_components/flightradar24/brand/` for Home Assistant 2026.3+ ([#344](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/344))

### Fixed

- Map card calls `invalidateSize` when its container resizes (e.g. sections `column_span`), so tiles fill the full width without needing a manual zoom ([#327](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/327), [#334](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/334))
- HTTP 429 storms after v2.1.2: disable FlightRadarAPI empty-feed rerolls (`FEED_EMPTY_RETRIES=0`), do not retry 429, and pause the affected endpoint with exponential back-off up to 15 minutes (honours `Retry-After` when present) ([#254](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/254), [#330](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/330), [#332](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/332), [#333](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/333), [#341](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/341))
- Tracked flights keep updating when the area feed fails or is rate-limited ([#341](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/341))
- Setup continues with an unverified session on canary HTTP 429 instead of leaving every entity unavailable; login 429 becomes `ConfigEntryNotReady` so Home Assistant retries, while 401/403 stay auth failures ([#301](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/301), [#328](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/328))
- Fetch `get_flight_details` for every flight that needs it until the details endpoint is paused (429 or other failure; pause lasts across cycles until cooldown expires); new flights without successful details are not published as feed-only stubs; share request spacing process-wide so multiple entries are less likely to re-trigger IP limits ([#341](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/341))

## [2.3.0] - 2026-10-06

### Added

- Map card option `map_style` to switch basemap without an API key: `osm` (default), `satellite` (Esri), `topo` (OpenTopoMap)
- Map card option `interactive_map` for opt-in mouse/touch dragging and pinch zoom, with fixed Close details and Reset view controls; default static dashboards are unchanged ([#324](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/324))

### Fixed

- Adding or removing a tracked flight updates `Additional tracked` and clears the Add/Remove text inputs immediately, instead of waiting for the next poll ([#318](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/318), [#323](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/323))

## [2.2.2] - 2026-10-02

### Fixed

- `scan_interval` of `0` or negative no longer schedules back-to-back API polls; setup and options require at least 10 seconds, and existing entries below the minimum are rewritten once to the 20-second default ([#319](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/319), [#321](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/321))
- Options form prefills a valid scan interval when a stored value is below the minimum, so Configure can be saved without first clearing a bad field
- `airport_origin_code_iata` on tracked/most-tracked flight data now uses the IATA code instead of the full airport name ([#322](https://github.com/AlexandrErohin/home-assistant-flightradar24/pull/322))

## [2.2.1] - 2026-09-22

### Fixed

- False `flightradar24_tracked_arrived_gate` events when a tracked flight briefly disappears from the live feed mid-air (ADS-B gaps) or during pre-departure taxi; arrival now requires landing evidence (`has_landed` / `time_real_arrival`) ([#315](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/315))
- False `flightradar24_tracked_left_gate` events on live-feed reappearances; the event fires only on a real `schedule`/`aircraft` → `live` transition, and gate lifecycle flags reset for the next segment

## [2.2.0] - 2026-09-08

### Added

- Map card option `show_header` to hide the title/count bar above the map (combine with `show_flights: false` for a map-only card)

### Changed

- Reverted dependency `pycountry` from `26.2.16` (introduced in 2.1.2) back to `24.6.1` to match Home Assistant core (e.g. `radio_browser`), fixing the install conflict with HA 2026.9.0 ([#313](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/313))

### Fixed

- Stop re-fetching flight details every scan for aircraft without a `flight_number` (common for GA/private); recent details now count as valid for the 2–6 minute window, reducing HTTP 429 near airports ([#254](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/254))

## [2.1.2] - 2026-09-02

### Changed

- Fixed Entity IDs are always English regardless of Home Assistant language; UI names stay translated ([#265](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/265)) Home Assistant does not rename existing entities. To get English IDs: rename them manually under **Settings → Devices & Services → Entities**, or remove and re-add the integration
- Updated dependency `FlightRadarAPI` from `1.5.1` to `1.6.1`
- Updated dependency `pycountry` from `24.6.1` to `26.2.16`

## [2.1.1] - 2026-08-25

### Break change

- Removed the custom `last_updated` attribute from sensors / most-tracked switch. Templates or automations that read `state_attr(..., 'last_updated')` need to use Home Assistant’s built-in `last_updated` / `last_changed` instead.

### Fixed

- Recorder no longer grows on every poll when area counts stay unchanged (e.g. `0`) — state is written only when the value or recorded attributes actually change ([#308](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/308), [#312](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/312))
- Map card flight list no longer rebuilds via `innerHTML` on each update — flags and rows update in place, fixing flag flicker ([#306](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/306))
- Map card popup text is readable again on dark / glass themes (forced light popup surface) ([#310](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/310))
- Session recreate pauses between attempts and keeps the current session if login fails, reducing HTTP 429 during bot-mitigation recovery ([#254](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues/254))
