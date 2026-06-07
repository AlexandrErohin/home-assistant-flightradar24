# Flightradar24 integration for Home Assistant
[![version](https://img.shields.io/github/manifest-json/v/AlexandrErohin/home-assistant-flightradar24?filename=custom_components%2Fflightradar24%2Fmanifest.json&color=slateblue)](https://github.com/AlexandrErohin/home-assistant-flightradar24/releases/latest)
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg?logo=HomeAssistantCommunityStore&logoColor=white)](https://github.com/hacs/integration)
[![Community Forum](https://img.shields.io/static/v1.svg?label=Community&message=Forum&color=41bdf5&logo=HomeAssistant&logoColor=white)](https://community.home-assistant.io/t/custom-component-flightradar24)
![Stars](https://img.shields.io/github/stars/AlexandrErohin/home-assistant-flightradar24?style=social)
![Downloads](https://img.shields.io/github/downloads/AlexandrErohin/home-assistant-flightradar24/total)


[![Latest Release](https://img.shields.io/github/v/release/AlexandrErohin/home-assistant-flightradar24?style=for-the-badge&color=007ec6)](https://github.com/AlexandrErohin/home-assistant-flightradar24/releases)
[![Home Assistant CI](https://img.shields.io/github/actions/workflow/status/AlexandrErohin/home-assistant-flightradar24/hass-ci.yml?label=Home%20Assistant%20CI&style=for-the-badge)](https://github.com/AlexandrErohin/home-assistant-flightradar24/actions/workflows/hass-ci.yml)
[![Code Checks](https://img.shields.io/github/actions/workflow/status/AlexandrErohin/home-assistant-flightradar24/codechecker.yml?style=for-the-badge&label=CODE%20CHECKS&color=5dbb0f)](https://github.com/AlexandrErohin/home-assistant-flightradar24/actions)
[![Tests](https://img.shields.io/github/actions/workflow/status/AlexandrErohin/home-assistant-flightradar24/pytest.yml?style=for-the-badge&label=TESTS&color=5dbb0f)](https://github.com/AlexandrErohin/home-assistant-flightradar24/actions)
[![HACS Validation](https://img.shields.io/github/actions/workflow/status/AlexandrErohin/home-assistant-flightradar24/hacs.yaml?style=for-the-badge&label=HACS%20VALIDATION&color=5dbb0f)](https://github.com/AlexandrErohin/home-assistant-flightradar24/actions)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-5dbb0f?style=for-the-badge)](https://github.com/pre-commit/pre-commit)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000?style=for-the-badge)](https://github.com/astral-sh/ruff)
[![Home Assistant Version](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-007ec6?style=for-the-badge)](https://www.home-assistant.io/)
[![Maintainer](https://img.shields.io/badge/maintainer-%40AlexandrErohin-007ec6?style=for-the-badge)](https://github.com/AlexandrErohin)
[![CodeQL](https://img.shields.io/github/actions/workflow/status/AlexandrErohin/home-assistant-flightradar24/codeql.yml?label=CodeQL&style=for-the-badge)](https://github.com/AlexandrErohin/home-assistant-flightradar24/actions/workflows/codeql.yml)









## 📡 Overview

The **Flightradar24** integration brings real-time aviation tracking into Home Assistant.

Track flights above your location, monitor airports, follow specific aircraft worldwide, and trigger powerful automations based on live flight events.

> ✅ **No Flightradar24 subscription required**


---

# ✨ Features

- 🌍 Track flights currently in your area
- ✈️ Follow aircraft anywhere in the world
- 🛬 Monitor airport arrivals and departures
- 🔔 Create flight-based notifications and automations
- 📊 View airport delay and cancellation statistics
- 🗺️ Add live flight maps to Home Assistant dashboards
- 📱 Track flights as Home Assistant `device_tracker`
- 🔥 Monitor the top 10 most tracked flights on Flightradar24

---


It allows you:
1. Know how many flights in your area right now, or just have entered or exited it. And get list of flights with [full information](#flight) by every relevant flight for the sensor 
2. Track a particular plane or planes no matter where it currently is, even if it is a scheduled flight
3. Monitor daily statistics (like on time/delayed/canceled flights) of the [selected airport](https://github.com/AlexandrErohin/home-assistant-flightradar24#configuration)
4. Get [top 10 most tracked flights on FlightRadar24](#most-tracked) 
5. Create notifications (example - [Get a notification when a flight enters or exits your area](#notification-enters), [Get a notification when a tracked scheduled flight takes off](#notification-scheduled))
6. Create automations (example - [Automatically track a flight by your needs](#automation))
7. Add flights table for your area to your [Home Assistant dashboard](https://www.home-assistant.io/dashboards/) by [Lovelace Card](#lovelace))
8. Add departures/arrivals boards of the selected airport to your [Home Assistant dashboard](https://www.home-assistant.io/dashboards/) by [Lovelace Airport Card](#lovelace-airport))
9. Track your flight as [Device Tracker](#device-tracker) 
10. Get info for last flights which were in your area or get info about latest exited flight by creating [Last Flights History Sensor](#last-flights) 

<img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/map.png" width="48%"><img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/lovelace.png" width="48%">
<img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/sensors1.png" width="48%"><img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/sensors2.png" width="48%">
<img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/airport_departures.jpg" width="48%"><img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/airport_arrivals.jpg" width="48%">


# 🚀 Installation

## HACS (Recommended)

1. Install [HACS](https://hacs.xyz/)
2. Open **HACS**
3. Search for `Flightradar24`
4. Click **Download**
5. Restart Home Assistant

### One-click install

<div align="left">

<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=AlexandrErohin&repository=home-assistant-flightradar24&category=integration" target="_blank"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open a repository inside the Home Assistant Community Store." /></a>

</div>

---

## Manual Installation

1. Locate the `custom_components` directory in your Home Assistant configuration directory. It may need to be created.
2. Copy the `custom_components/flightradar24` directory into the `custom_components` directory.
3. Restart Home Assistant.

## Configuration
Flightradar24 is configured via the GUI. See [the HA docs](https://www.home-assistant.io/getting-started/integration/) for more details.

The default data is preset already

<p align="center"><img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/config_flow.png" width="48%"></p>

1. Go to the <b>Settings</b>-><b>Devices & services</b>.
2. Click on `+ ADD INTEGRATION`, search for `Flightradar24`.
3. You may change the default values for Radius, Latitude and Longitude
4. Click `SUBMIT`

### <a id="edit-configuration">Edit Configuration</a>
You may edit configuration data like:
1. Latitude and longitude of your point
2. Radius of your zone
3. Scan interval for updates in seconds
4. The minimum and maximum altitudes in foots between which the aircraft will be tracked
5. Enable/Disable [top 10 most tracked flights on FlightRadar24](#most-tracked)
6. Enable/Disable [device_tracker for flights](#device-tracker)
7. Optional: Username and password if you have FlightRadar24 subscription
8. Enable/Disable Enable auto-cleanup of landed tracked flights. That automatically removes flights from the "Additional tracked" list once they arrive at the gate
10. Map Tracker Naming Style.
 - Callsign Only (e.g., KLM1412) - Default
 - Callsign + Route (e.g., KLM1412 (CDG - AMS))
 - Registration + Route (e.g., PH-BXE (CDG - AMS))

To do that:

1. Go to the <b>Settings</b>-><b>Devices & services</b>.
2. Search for `Flightradar24`, and click on it.
3. Click on `CONFIGURE`
4. Edit the options you need and click `SUBMIT`

3. Restart Home Assistant

---

# ⚙️ Configuration

The integration is fully configured through the Home Assistant UI.

## Initial Setup

1. Open:

```text
Settings → Devices & Services
```

2. Click:

```text
+ ADD INTEGRATION
```

3. Search for:

```text
Flightradar24
```

4. Configure:
   - Latitude
   - Longitude
   - Radius

5. Click `SUBMIT`

---

## Configuration Options

You can configure:

| Option | Description |
|---|---|
| Radius | Flight detection radius |
| Coordinates | Monitoring location |
| Scan interval | Update frequency |
| Altitude filters | Minimum & maximum altitude |
| Most tracked flights | Enable/disable top 10 tracking |
| Device tracker | Enable aircraft tracking entity |
| FR24 credentials | Optional premium login |
| Auto cleanup | Remove landed tracked flights |
| Naming style | Customize map tracker names |

---

# 🧩 Components

## Events

| Event | Description |
|---|---|
| `flightradar24_entry` | Flight entered your area |
| `flightradar24_exit` | Flight exited your area |
| `flightradar24_area_landed` | Aircraft landed nearby |
| `flightradar24_area_took_off` | Aircraft took off nearby |
| `flightradar24_tracked_took_off` | Tracked aircraft departed |
| `flightradar24_tracked_landed` | Tracked aircraft landed |
| `flightradar24_tracked_arrived_gate` | Flight arrived at gate |
| `flightradar24_tracked_left_gate` | Flight left gate |

---

## Sensors

| Area tracking | Description |
|---|---|
| `Current in area` | Flight entered your area |
| `Entered area` |  Flights that just have exited your area |
| `Exited area` | Flights that just have entered your area |
| `Additional tracked` | Your additional tracked outside your area |
| `Most tracked` | Most tracked flights on FlightRadar24. You may disable it via configuration |


| Airport tracking | Description |
|---|---|
| `Airport arrivals ` | List of current arrival flights for the selected airport |
| `Airport departures` |  List of current departure flights for the selected airport |
| `Airport arrivals on time` | Amount of arrivals on time for the selected airport today |
| `Airport arrivals delayed` | Amount of delayed arrivals for the selected airport today |
| `Airport arrivals delay average` | Disruption arrivals index for the selected airport today |
| `Airport arrivals delay index` | Amount of canceled arrivals for the selected airport today |
| `Airport arrivals canceled` | Amount of canceled arrivals for the selected airport today |
| `Airport departures on time` | Amount of departures on time for the selected airport today |
| `Airport departures delayed` | Amount of delayed departures for the selected airport today |
| `Airport departures delay average` | Average departures delay for the selected airport today |
| `Airport departures delay index` | Disruption departures index for the selected airport today |
| `Airport departures canceled` |  Amount of canceled departures for the selected airport today |

### Other
| Other tracking | Description |
|---|---|
| `Most tracked flights` | The most tracked flights |


<br>

> **⚠️ IMPORTANT NOTE ON ENTITY IDs & TRANSLATIONS ⚠️**  
> Home Assistant automatically generates the underlying `entity_id` for your sensors based on your system's default language at the time of installation. For example, `sensor.flightradar24_current_in_area` might automatically become `sensor.flightradar24_bereich_betreten` on a German system. 
> 
> **Before copying and pasting any YAML or Lovelace code from this README**, please verify your exact entity IDs by navigating to **Settings -> Devices & Services -> Entities** and update the code examples to match your localized IDs!

<br>
Home Assistant may translate entity IDs based on your system language.

Example:

```text
sensor.flightradar24_current_in_area
```

might become:

```text
sensor.flightradar24_bereich_betreten
```

Always verify your entity IDs here:

```text
Settings → Devices & Services → Entities
```

before copying YAML examples.

---


### <a id="device-tracker">Device Tracker</a>
You may be interested to add a live flight as device_tracker with the flight information to a person in HA.
To use it - you need to activate this feature in [Edit Configuration](#edit-configuration).
When it is enabled, this integration creates a separate `device_tracker` for each flight in the additional tracked list.
Each tracker uses the configured map tracker naming style and updates independently while that flight remains additional tracked.

### Tracked Flight Card Sensors
For each flight in the Additional tracked list, the integration also creates a separate sensor named like `sensor.flightradar24_tracked_flight_<flight>`.
Each of these sensors exposes a single flight in its `flights` attribute, so it can be used directly with cards that expect a Flightradar24 sensor, such as [flightradar-flight-card](https://github.com/plckr/flightradar-flight-card).

```yaml
type: custom:flightradar-flight-card
entities:
  - entity_id: sensor.flightradar24_tracked_flight_ba123
    title: BA123
```

### Configuration
 - Add to track - Pass flight number or call sign or aircraft registration number to track flight outside your area. It adds flight to Additional tracked sensor
 - Remove from track - Pass flight number or call sign or aircraft registration number to remove a flight from Additional tracked sensor
 - Airport track - Pass IATA or ICAO airport code to start receiving data in Airport sensors. To stop receiving airport data just pass an empty string
 - API data fetching - you may disable FlightRadar API calls when not needed to prevent unnecessary API calls and save bandwidth and server load.
 - Clear Additional tracked - Clear all flights in Additional tracked sensor

Sensors (Current in area, Entered area, Exited area, Additional tracked) shows how many flights in the given area, additional tracked, just have entered or exited it. All these sensors have attribute `flights` with list of [flight object](#flight) contained a full information by every relevant flight for the sensor

Sensor Most tracked has attribute `flights` with list of [most tracked object](#most-tracked)

Sensors Airport arrivals and Airport departures have attribute `flights` with list of the next 50 [airport flights](#airport-flight)


## Uses
### <a id="notification-enters">Notification - When a flight enters or exits your area</a>
To receive notifications of the entering flights add following lines to your `configuration.yaml` file:
```yaml
automation:
  - alias: "Flight entry notification"
    trigger:
      platform: event
      event_type: flightradar24_entry
    action:
      service: notify.mobile_app_<device_name>
      data:
        message: >-
          Flight entry of {{ trigger.event.data.callsign }} to {{ trigger.event.data.airport_destination_city }}
          [Open FlightRadar](https://www.flightradar24.com/{{ trigger.event.data.callsign }})
        data:
          url: >-
            [https://fr24.com/](https://fr24.com/){{ trigger.event.data.callsign }}/{{
            trigger.event.data.id }}
          clickAction: >-
            [https://fr24.com/](https://fr24.com/){{ trigger.event.data.callsign }}/{{
            trigger.event.data.id }}
          image: "{{ trigger.event.data.aircraft_photo_medium }}"
```

All available fields in `trigger.event.data` you can check [here](#flight)

If you have defined more than one device of FlightRadar24 for more places to observe - you may be interested to know what device has fired the event
It is stored in 
#### <a id="tracked_by_device">`trigger.event.data.tracked_by_device`</a>

To change name in tracked_by_device
1. Go to the <b>Settings</b>-><b>Devices & services</b>.
2. Search for `Flightradar24`, and click on it.
3. Click on three-dot near of device you wanted
4. Click on `Rename` in the opened sub-menu
5. Enter new name and click `OK`

### <a id="notification-scheduled">Notification - When a tracked scheduled flight takes off</a>
To receive notification of taking off tracked scheduled flight add following lines to your `configuration.yaml` file:
```yaml
automation:
  - alias: "Scheduled flight takes off"
    trigger:
      platform: event
      event_type: flightradar24_tracked_took_off
    action:
      service: notify.mobile_app_<device_name>
      data:
        message: >-
          Flight takes off {{ trigger.event.data.callsign }} to {{ trigger.event.data.airport_destination_city }}
          [Open FlightRadar](https://www.flightradar24.com/{{ trigger.event.data.callsign }})
        data:
          url: >-
            [https://fr24.com/](https://fr24.com/){{ trigger.event.data.callsign }}/{{
            trigger.event.data.id }}
          clickAction: >-
            [https://fr24.com/](https://fr24.com/){{ trigger.event.data.callsign }}/{{
            trigger.event.data.id }}
          image: "{{ trigger.event.data.aircraft_photo_medium }}"
```

### <a id="automation">Automation</a>
To automatically add a flight to additional tracking add following lines to your `configuration.yaml` file:

> **Note:** Ensure `text.flightradar24_add_to_track` matches your actual localized entity ID in HA.

```yaml
automation:
  - alias: "Track flights"
    trigger:
      platform: event
      event_type: flightradar24_exit
    condition:
      - condition: template
        value_template: "{{ 'Frankfurt' == trigger.event.data.airport_origin_city }}"
    action:
      - service: text.set_value
        data:
          value: "{{ trigger.event.data.aircraft_registration }}"
        target:
          entity_id: text.flightradar24_add_to_track
```

This is an example to filter flights to track, change the conditions for your needs

### <a id="last-flights">Last Flights History Sensor</a>
You may get info for last flights which were in your area. Or get info about latest exited flight.
Here is an example for recording history for the last 5 flights.
The sensor has the same structure as `sensor.flightradar24_current_in_area` and so you can use the same markdown code.
Only the sensor state is different - it shows the latest exited flight.
You may change it for your needs.
Add following lines to your `configuration.yaml` file:
```yaml
template:
  - trigger:
      - platform: event
        event_type: flightradar24_exit

    sensor:
      - unique_id: flightradar24_last_5_flights
        name: "FlightRadar24 Last 5 Flights"
        state: >-
          {% set flight = trigger.event.data %}
          {{ flight.flight_number }} - {{ flight.airline_short }} - {{ flight.aircraft_model }} ({{ flight.aircraft_registration }})
          {{ flight.airport_origin_city }} > {{ flight.airport_destination_city }}
        attributes:
          flights: >-
            {% set n = 5 %}
            {% set m = this.attributes.flights | count | default(0) %}
            {{ [ trigger.event.data ] + 
               ( [] if m == 0 else 
                 this.attributes.flights[0:n-1] )
            }}
          icon: mdi:airplane
```

### <a id="lovelace">Lovelace Card</a>
You can add flight table to your [Home Assistant dashboard](https://www.home-assistant.io/dashboards/)

<p align="center"><img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/lovelace.png" width="48%"></p>

1. Go to your [Home Assistant dashboard](https://www.home-assistant.io/dashboards/)
2. In the top right corner, select the three-dot menu, then select Edit dashboard
3. Click on `+ ADD CARD`, search for `Manual`, click on `Manual`. 
4. Add following code to the input window and click `SAVE`

> **Note:** If your Home Assistant system is not in English, your sensor names may be translated. Please replace all instances of `sensor.flightradar24_current_in_area` below with your exact local entity ID!

```yaml
type: vertical-stack
title: Flightradar24
cards:
  - type: entities
    entities:
      - entity: sensor.flightradar24_current_in_area
        name: In area
  - type: conditional
    conditions:
      - condition: numeric_state
        entity: sensor.flightradar24_current_in_area
        above: 0
    card:
      type: markdown
      content: >-
        {% set data = state_attr('sensor.flightradar24_current_in_area',
        'flights') | default([], true) %} {% for flight in data %}{% if (flight.tracked_type | default('live')) == 'live' %}
          <ha-icon icon="mdi:airplane"></ha-icon>{{ flight.flight_number }} - {{ flight.airline_short }} - {{ flight.aircraft_model }}
          {{ flight.airport_origin_city }}{%if flight.airport_origin_city %}<img src="[https://flagsapi.com/](https://flagsapi.com/){{ flight.airport_origin_country_code }}/shiny/16.png" title='{{ flight.airport_origin_country_name }}'/>{% endif %} -> {{ flight.airport_destination_city }}{%
          if flight.airport_destination_country_code %}<img src="[https://flagsapi.com/](https://flagsapi.com/){{ flight.airport_destination_country_code }}/shiny/16.png" title='{{ flight.airport_destination_country_name }}'/>{% endif %}
          {%if flight.time_scheduled_departure %}Departure - {{ flight.time_scheduled_departure | timestamp_custom('%H:%M') }}; {% endif %}{%if flight.time_scheduled_arrival%}Arrival - {{ flight.time_scheduled_arrival | timestamp_custom('%H:%M') }}{% endif %}
          Altitude - {{ flight.altitude }} ft{%if flight.altitude > 0 %} ({{(flight.altitude * 0.3048)| round(0)}} m){% endif%}; Gr. speed - {{ flight.ground_speed }} kts{%if flight.ground_speed > 0 %} ({{(flight.ground_speed * 1.852)| round(0)}} km/h){% endif%}
          {% else%}
          <ha-icon icon="mdi:airplane"></ha-icon>{{ flight.flight_number }} - {{ flight.callsign }} - {{ flight.tracked_type }}
          {% endif%}{% endfor %}
```

This example for `sensor.flightradar24_current_in_area` which shows flights in your area, to show additional tracked flights replace sensor name to `sensor.flightradar24_additional_tracked`

All available fields for flight you can check [here](#flight)

### Lovelace Card with Map
<p align="center"><img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/map2.png" width="55%"></p>

1. Go to your [Home Assistant dashboard](https://www.home-assistant.io/dashboards/)
2. In the top right corner, select the three-dot menu, then select Edit dashboard 
3. Click on `+ ADD CARD`, search for `Manual`, click on `Manual`. 
4. Add following code to the input window. Replace LATITUDE, LONGITUDE with your coordinates. URL example: https://globe.adsb.fi/?enableLabels&trackLabels&zoom=12&hideSideBar&lat=50.984944839678334&lon=11.311357147743463
5. Click `SAVE`

> **Note:** If your Home Assistant system is not in English, please replace `sensor.flightradar24_current_in_area` below with your exact local entity ID!

```yaml
type: vertical-stack
title: Flightradar24
cards:
  - type: entities
    entities:
      - entity: sensor.flightradar24_current_in_area
        name: In area
  - type: conditional
    conditions:
      - condition: numeric_state
        entity: sensor.flightradar24_current_in_area
        above: 0
    card:
      type: markdown
      content: >-
        {% set data = state_attr('sensor.flightradar24_current_in_area',
        'flights') | default([], true) %} {% for flight in data %}
          <ha-icon icon="mdi:airplane"></ha-icon>{{ flight.flight_number }}({{ flight.aircraft_registration }}) - {{ flight.airline_short }} - {{ flight.aircraft_model }}
          {{ flight.airport_origin_city }}{%if flight.airport_origin_city %}<img src="[https://flagsapi.com/](https://flagsapi.com/){{ flight.airport_origin_country_code }}/shiny/16.png" title='{{ flight.airport_origin_country_name }}'/>{% endif %} -> {{ flight.airport_destination_city }}{%
          if flight.airport_destination_country_code %}<img src="[https://flagsapi.com/](https://flagsapi.com/){{ flight.airport_destination_country_code }}/shiny/16.png" title='{{ flight.airport_destination_country_name }}'/>{% endif %}
          {%if flight.time_scheduled_departure %}Departure - {{ flight.time_scheduled_departure | timestamp_custom('%H:%M') }}; {% endif %}{%if flight.time_scheduled_arrival%}Arrival - {{ flight.time_scheduled_arrival | timestamp_custom('%H:%M') }}{% endif %}
          Altitude - {{ flight.altitude }} ft{%if flight.altitude > 0 %} ({{(flight.altitude * 0.3048)| round(0)}} m){% endif%}; Gr. speed - {{ flight.ground_speed }} kts{%if flight.ground_speed > 0 %} ({{(flight.ground_speed * 1.852)| round(0)}} km/h){% endif%}
          {% endfor %}
  - type: iframe
    url: >-
      [https://globe.adsb.fi/?enableLabels&trackLabels&zoom=12&hideSideBar&lat=LATITUDE&lon=LONGITUDE](https://globe.adsb.fi/?enableLabels&trackLabels&zoom=12&hideSideBar&lat=LATITUDE&lon=LONGITUDE)
    aspect_ratio: 100%
```

# 🧾 Recorder Database Optimization
To decrease data stored by [Recorder](https://www.home-assistant.io/integrations/recorder/) in database add following lines to your `configuration.yaml` file:
Exclude Flightradar24 sensors from Home Assistant Recorder:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.flightradar24*
```

## <a id="flight">Flight fields</a>
| Field                               | Description                                                                                                                                                                                                 |
|-------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| tracked_by_device                   | If you have defined more than one device of FlightRadar24 for more places to observe - you may be interested to know what device has fired the event. To rename the device check [this](#tracked_by_device) |
| tracked_type                        | Only for tracked flights. It shows is flight live or scheduled                                                                                                                                              |
| flight_number                       | Flight Number                                                                                                                                                                                               |
| latitude                            | Current latitude of the aircraft                                                                                                                                                                            |
| longitude                           | Current longitude of the aircraft                                                                                                                                                                           |
| altitude                            | Altitude (measurement: foot)                                                                                                                                                                                |
| on_ground                           | Is the aircraft on ground (measurement: 0 - in the air; 1 - on ground)                                                                                                                                      |
| distance                            | Distance between the aircraft and your point (measurement: kilometers)                                                                                                                                      |
| closest_distance                    | Closest distance the aircraft reached to your point while tracking (measurement: kilometers)                                                                                                                |
| ground_speed                        | Ground speed (measurement: knots)                                                                                                                                                                           |
| squawk                              | Squawk code are what air traffic control (ATC) use to identify aircraft when they are flying **(for subscription only)**                                                                                    |
| vertical_speed                      | Vertical speed                                                                                                                                                                                              |
| heading                             | The compass direction in which the craft's bow or nose is pointed (measurement: degrees)                                                                                                                    |
| callsign                            | Callsign of the flight                                                                                                                                                                                      |
| aircraft_registration               | Aircraft registration number                                                                                                                                                                                |
| aircraft_photo_small                | Aircraft small size photo url                                                                                                                                                                               |
| aircraft_photo_medium               | Aircraft medium size photo url                                                                                                                                                                              |
| aircraft_photo_large                | Aircraft large size photo url                                                                                                                                                                               |
| aircraft_model                      | Aircraft model                                                                                                                                                                                              |
| aircraft_code                       | Aircraft code                                                                                                                                                                                               |
| aircraft_icao_24bit                 | Unique aircraft ID                                                                                                                                                                                          |
| aircraft_category                   | Aircraft category (example: Helicopter or Airplane)                                                                                                                                                         |
| airline                             | Airline full name                                                                                                                                                                                           |
| airline_short                       | Airline short name                                                                                                                                                                                          |
| airline_iata                        | Airline IATA code                                                                                                                                                                                           |
| airline_icao                        | Airline ICAO code                                                                                                                                                                                           |
| airport_origin_name                 | Origin airport name                                                                                                                                                                                         |
| airport_origin_code_iata            | Origin airport IATA code                                                                                                                                                                                    |
| airport_origin_code_icao            | Origin airport ICAO code                                                                                                                                                                                    |
| airport_origin_country_name         | Origin airport country name                                                                                                                                                                                 |
| airport_origin_country_code         | Origin airport country code                                                                                                                                                                                 |
| airport_origin_city                 | Origin airport city name                                                                                                                                                                                    |
| airport_origin_timezone_offset      | Origin airport timezone offset (in seconds)                                                                                                                                                                 |
| airport_origin_timezone_abbr        | Origin airport timezone abbreviation                                                                                                                                                                        |
| airport_origin_terminal             | Origin airport terminal                                                                                                                                                                                     |
| airport_origin_latitude             | Origin airport latitude                                                                                                                                                                                     |
| airport_origin_longitude            | Origin airport longitude                                                                                                                                                                                    |
| airport_destination_name            | Destination airport name                                                                                                                                                                                    |
| airport_destination_code_iata       | Destination airport IATA code                                                                                                                                                                               |
| airport_destination_code_icao       | Destination airport ICAO code                                                                                                                                                                               |
| airport_destination_country_name    | Destination airport country name                                                                                                                                                                            |
| airport_destination_country_code    | Destination airport country code                                                                                                                                                                            |
| airport_destination_city            | Destination airport city name                                                                                                                                                                               |
| airport_destination_timezone_offset | Destination airport timezone offset (in seconds)                                                                                                                                                            |
| airport_destination_timezone_abbr   | Destination airport timezone abbreviation                                                                                                                                                                   |
| airport_destination_terminal        | Destination airport terminal                                                                                                                                                                                |
| airport_destination_latitude        | Destination airport latitude                                                                                                                                                                                |
| airport_destination_longitude       | Destination airport longitude                                                                                                                                                                               |
| time_scheduled_departure            | Scheduled departure time                                                                                                                                                                                    |
| time_scheduled_arrival              | Scheduled arrival time                                                                                                                                                                                      |
| time_real_departure                 | Real departure time                                                                                                                                                                                         |
| time_real_arrival                   | Real arrival time                                                                                                                                                                                           |
| time_estimated_departure            | Estimated departure time                                                                                                                                                                                    |
| time_estimated_arrival              | Estimated arrival time                                                                                                                                                                                      |

## <a id="most-tracked">Most tracked</a>
Sensor `Most tracked` shows top 10 most tracked flights on FlightRadar24 with next flight fields

| Field | Description |
|---|---|
| flight_number | Flight Number |
| callsign | Callsign of the flight |
| squawk | Squawk code are what air traffic control (ATC) use to identify aircraft when they are flying |
| aircraft_model | Aircraft model |
| aircraft_code | Aircraft code |
| clicks | How many people track this flight |
| airport_origin_code_iata | Origin airport IATA code |
| airport_origin_city | Origin airport city name |
| airport_destination_code_iata | Destination airport IATA code |
| airport_destination_city | Destination airport city name |

### <a id="lovelace-airport">Lovelace Airport Card</a>
You can add departures/arrivals boards of the selected airport to your [Home Assistant dashboard](https://www.home-assistant.io/dashboards/)

<p align="center"><img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/airport.jpg" width="48%"></p>

1. Go to your [Home Assistant dashboard](https://www.home-assistant.io/dashboards/)
2. In the top right corner, select the three-dot menu, then select Edit dashboard
3. Click on `+ ADD CARD`, search for `Manual`, click on `Manual`. 
4. Add following code to the input window and click `SAVE`

> **Note:** If your Home Assistant system is not in English, please replace `sensor.flightradar24_airport_arrivals_canceled` and the other entity IDs below with your exact local entity IDs!



# 🗺️ Lovelace Flight Dashboard

```yaml
type: vertical-stack
title: Flightradar24

cards:
  - type: entities
    entities:
      - entity: sensor.flightradar24_current_in_area
        name: Flights In Area

  - type: conditional
    conditions:
      - condition: numeric_state
        entity: sensor.flightradar24_current_in_area
        above: 0

    card:
      type: markdown
      content: >-
        {% set flights =
        state_attr('sensor.flightradar24_current_in_area','flights')
        | default([], true) %}

        {% for flight in flights %}

        ### ✈️ {{ flight.flight_number }}

        **Airline:** {{ flight.airline_short }}

        **Aircraft:** {{ flight.aircraft_model }}

        **Route:** {{ flight.airport_origin_city }}
        → {{ flight.airport_destination_city }}

        **Altitude:** {{ flight.altitude }} ft

        **Speed:** {{ flight.ground_speed }} kts

        ---

        {% endfor %}
```

# 🌍 Live Flight Map Card

```yaml
type: iframe
url: >-
  https://globe.adsb.fi/?enableLabels&trackLabels&zoom=12&hideSideBar&lat=LATITUDE&lon=LONGITUDE
aspect_ratio: 100%
```

Replace:

```text
LATITUDE
LONGITUDE
```

with your coordinates.

---


# 🗺️ Lovelace Flight Dashboard
```yaml
type: vertical-stack
title: Flightradar24
cards:
  - type: entities
    entities:
      - entity: sensor.flightradar24_airport_arrivals_canceled
        name: Arrivals canceled
      - entity: sensor.flightradar24_airport_arrivals_delayed
        name: Arrivals delayed
      - entity: sensor.flightradar24_airport_arrivals_on_time
        name: Arrivals on time
  - type: markdown
    title: Arrivals
    content: >
      {% set flights =
      state_attr('sensor.flightradar24_airport_arrivals','flights') |
      default([], true) %}
        | TIME | FROM | FLIGHT | REMARK |
        | ---- | ---- | ------ | ------ | {% for f in flights %}
        | {{ f.time_scheduled_arrival | timestamp_custom('%H:%M') if f.time_scheduled_departure else '--:--' }} | {{ f.airport_city |  default('---', true) }} | {{ f.flight_number |  default('---', true) }} | {{ f.status_text |  default('---', true) }} | {% endfor %}
  - type: entities
    entities:
      - entity: sensor.flightradar24_airport_departures_canceled
        name: Departures canceled
      - entity: sensor.flightradar24_airport_departures_delayed
        name: Departures delayed
      - entity: sensor.flightradar24_airport_departures_on_time
        name: Departures on time
  - type: markdown
    title: Departures
    content: >
      {% set flights = state_attr('sensor.flightradar24_airport_departures',
      'flights') |  default([], true) %}
        | TIME | TO | FLIGHT | REMARK |
        | ---- | ---- | ------ | ------ | {% for f in flights %}
        | {{ f.time_scheduled_departure | timestamp_custom('%H:%M') if f.time_scheduled_departure else '--:--' }} | {{ f.airport_city |  default('---', true) }} | {{ f.flight_number |  default('---', true) }} | {{ f.status_text |  default('---', true) }} |{% endfor %}
```

# 🛬 Airport Arrivals & Departures Board

```yaml
type: vertical-stack

cards:
  - type: markdown
    title: Arrivals
    content: >
      {% set flights =
      state_attr('sensor.flightradar24_airport_arrivals',
      'flights') | default([], true) %}

      | Time | From | Flight | Status |
      |---|---|---|---|

      {% for f in flights %}

      | {{ f.time_scheduled_arrival |
      timestamp_custom('%H:%M') if
      f.time_scheduled_arrival else '--:--' }}

      | {{ f.airport_city }}

      | {{ f.flight_number }}

      | {{ f.status_text }} |

      {% endfor %}
```

---


All available fields for flight you can check [here](#airport-flight)

To start receiving data for an airport - Pass IATA or ICAO airport code to `text.flightradar24_airport_track`. To stop receiving airport data just pass an empty string

### <a id="airport-flight">Airport Flight fields</a>
Sensor `sensor.flightradar24_airport_arrivals` and `sensor.flightradar24_airport_departures` shows flights with next flight fields

| Field | Description |
|---|---|
| status_text | Flight status test (example: Delayed 17:02) |
| status | Flight status (example: delayed) |
| flight_id | Flight id on FlightRadar24 |
| flight_number | Flight Number |
| callsign | Callsign of the flight |
| aircraft_model | Aircraft model |
| aircraft_code | Aircraft code |
| aircraft_registration | Aircraft registration number |
| airline | Airline full name |
| airline_short | Airline short name |
| airline_iata | Airline IATA code |
| airline_icao | Airline ICAO code |
| airport_name | Airport name |
| airport_code_iata | Airport IATA code |
| airport_code_icao | Airport ICAO code |
| airport_country_name | Airport country name |
| airport_country_code | Airport country code |
| airport_city | Airport city |
| time_scheduled_departure | Scheduled departure time |
| time_scheduled_arrival | Scheduled arrival time |
| time_real_departure | Real departure time |
| time_real_arrival | Real arrival time |
| time_estimated_departure | Estimated departure time |
| time_estimated_arrival | Estimated arrival time |

## Thanks To
 - [FlightRadarAPI](https://github.com/JeanExtreme002/FlightRadarAPI) by [@JeanExtreme002](https://github.com/JeanExtreme002)
 - [The OpenSky integration](https://github.com/home-assistant/core/tree/dev/homeassistant/components/opensky)

This integration should only be used for your own educational purposes. If you are interested in accessing Flightradar24 data commercially, please contact business@fr24.com. See more information at [Flightradar24's terms and conditions](https://www.flightradar24.com/terms-and-conditions).
```
