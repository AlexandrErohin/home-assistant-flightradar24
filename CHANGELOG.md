# Changelog

All notable changes to this project are documented in this file.

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
