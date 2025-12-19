# Flightradar24 integration for Home Assistant
[![version](https://img.shields.io/github/manifest-json/v/AlexandrErohin/home-assistant-flightradar24?filename=custom_components%2Fflightradar24%2Fmanifest.json&color=slateblue)](https://github.com/AlexandrErohin/home-assistant-flightradar24/releases/latest)
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg?logo=HomeAssistantCommunityStore&logoColor=white)](https://github.com/hacs/integration)
[![Community Forum](https://img.shields.io/static/v1.svg?label=Community&message=Forum&color=41bdf5&logo=HomeAssistant&logoColor=white)](https://community.home-assistant.io/t/custom-component-flightradar24)

Flightradar24 integration allows one to track overhead flights in a given region or particular planes. It will also fire Home Assistant events when flights enter/exit/landed/took off.

<b>IMPORTANT: No need FlightRadar24 subscription!</b>

It allows you:
1. Know how many flights in your area right now, or just have entered or exited it. And get list of flights with [full information](#flight) by every relevant flight for the sensor 
2. Track a particular plane or planes no matter where it currently is, even if it is a scheduled flight
3. Get [top 10 most tracked flights on FlightRadar24](#most-tracked) 
4. Create notifications (example - [Get a notification when a flight enters or exits your area](#notification-enters), [Get a notification when a tracked scheduled flight takes off](#notification-scheduled))
5. Create automations (example - [Automatically track a flight by your needs](#automation))
6. Add flights table to your [Home Assistant dashboard](https://www.home-assistant.io/dashboards/) by [Lovelace Card](#lovelace))
7. Track your flight as [Device Tracker](#device-tracker) 
8. Get info for last flights which were in your area or get info about latest exited flight by creating [Last Flights History Sensor](#last-flights) 

<img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/map.png" width="48%"><img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/sensors.png" width="48%">
<p align="center"><img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/lovelace.png" width="50%"></p>

## Components
### Events
 - flightradar24_entry: Fired when a flight enters the region.
 - flightradar24_exit: Fired when a flight exits the region.
 - flightradar24_most_tracked_new: Fired when a new flight appears in top 10 most tracked flights on FlightRadar24
 - flightradar24_area_landed: Fired when a flight lands in your area.
 - flightradar24_area_took_off: Fired when a flight takes off in your area.
 - flightradar24_tracked_landed: Fired when a tracked flight lands.
 - flightradar24_tracked_took_off: Fired when a tracked flight takes off.

### Sensors
 - Current in area
 - Entered area
 - Exited area
 - Additional tracked
 - Most tracked flights (You may disable it via configuration)

### <a id="device-tracker">Device Tracker</a>
You may be interested to add a live flight as device_tracker with the flight information to a person in HA.
To use it - you need to activate this feature in [Edit Configuration](#edit-configuration).
When it is enabled - this integration creates device_tracker with static name `device_tracker.flightradar24` and
this device_tracker updates when there is a live flight in the additional tracked list.
It works ONLY with one live flight from the additional tracked list at a time!

### Configuration
 - Add to track
 - Remove from track
 - API data fetching - you may disable FlightRadar API calls when not needed to prevent unnecessary API calls and save bandwidth and server load.
 - Clear Additional tracked - Clear all flights in Additional tracked sensor

Sensors shows how many flights in the given area, additional tracked, just have entered or exited it. All sensors have attribute `flights` with list of [flight object](#flight) contained a full information by every relevant flight for the sensor

Configuration inputs fields allows to add or remove a flight to/from sensor - Additional tracked. Adding/Removing supports flight number, call sign, aircraft registration number

## Installation

### HACS (recommended)

Have [HACS](https://hacs.xyz/) installed, this will allow you to update easily.

<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=AlexandrErohin&repository=home-assistant-flightradar24&category=integration" target="_blank"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open a repository inside the Home Assistant Community Store." /></a>

or go to <b>Hacs</b> and search for `Flightradar24`.

### Manual

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
7. Username and password if you have FlightRadar24 subscription

To do that:

1. Go to the <b>Settings</b>-><b>Devices & services</b>.
2. Search for `Flightradar24`, and click on it.
3. Click on `CONFIGURE`
4. Edit the options you need and click `SUBMIT`

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
            https://fr24.com/{{ trigger.event.data.callsign }}/{{
            trigger.event.data.id }}
          clickAction: >-
            https://fr24.com/{{ trigger.event.data.callsign }}/{{
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
            https://fr24.com/{{ trigger.event.data.callsign }}/{{
            trigger.event.data.id }}
          clickAction: >-
            https://fr24.com/{{ trigger.event.data.callsign }}/{{
            trigger.event.data.id }}
          image: "{{ trigger.event.data.aircraft_photo_medium }}"
```

### <a id="automation">Automation</a>
To automatically add a flight to additional tracking add following lines to your `configuration.yaml` file:
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
The sensor has the same structure as `sensor.flighradar24_current_in_area` and so you can use the same markdown code.
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

```markdown
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
        'flights') %} {% for flight in data %}{% if (flight.tracked_type | default('live')) == 'live' %}
          <ha-icon icon="mdi:airplane"></ha-icon>{{ flight.flight_number }} - {{ flight.airline_short }} - {{ flight.aircraft_model }}
          {{ flight.airport_origin_city }}{%if flight.airport_origin_city %}<img src="https://flagsapi.com/{{ flight.airport_origin_country_code }}/shiny/16.png" title='{{ flight.airport_origin_country_name }}'/>{% endif %} -> {{ flight.airport_destination_city }}{%
          if flight.airport_destination_country_code %}<img src="https://flagsapi.com/{{ flight.airport_destination_country_code }}/shiny/16.png" title='{{ flight.airport_destination_country_name }}'/>{% endif %}
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
4. Add following code to the input window. Replace LATITUDE, LONGITUDE with your coordinates
5. Click `SAVE`

```markdown
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
        'flights') %} {% for flight in data %}
          <ha-icon icon="mdi:airplane"></ha-icon>{{ flight.flight_number }}({{ flight.aircraft_registration }}) - {{ flight.airline_short }} - {{ flight.aircraft_model }}
          {{ flight.airport_origin_city }}{%if flight.airport_origin_city %}<img src="https://flagsapi.com/{{ flight.airport_origin_country_code }}/shiny/16.png" title='{{ flight.airport_origin_country_name }}'/>{% endif %} -> {{ flight.airport_destination_city }}{%
          if flight.airport_destination_country_code %}<img src="https://flagsapi.com/{{ flight.airport_destination_country_code }}/shiny/16.png" title='{{ flight.airport_destination_country_name }}'/>{% endif %}
          {%if flight.time_scheduled_departure %}Departure - {{ flight.time_scheduled_departure | timestamp_custom('%H:%M') }}; {% endif %}{%if flight.time_scheduled_arrival%}Arrival - {{ flight.time_scheduled_arrival | timestamp_custom('%H:%M') }}{% endif %}
          Altitude - {{ flight.altitude }} ft{%if flight.altitude > 0 %} ({{(flight.altitude * 0.3048)| round(0)}} m){% endif%}; Gr. speed - {{ flight.ground_speed }} kts{%if flight.ground_speed > 0 %} ({{(flight.ground_speed * 1.852)| round(0)}} km/h){% endif%}
          {% endfor %}
  - type: iframe
    url: >-
      https://globe.adsb.fi/?enableLabels&trackLabels&zoom=12&hideSideBar&SiteLat=LATITUDE&SiteLon=LONGITUDE
    aspect_ratio: 100%
```

## Database decrease
To decrease data stored by [Recorder](https://www.home-assistant.io/integrations/recorder/) in database add following lines to your `configuration.yaml` file:
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
| airport_origin_terminal             | Origin airport terminal
| airport_origin_latitude             | Origin airport latitude
| airport_origin_longitude            | Origin airport longitude
| airport_destination_name            | Destination airport name                                                                                                                                                                                    |
| airport_destination_code_iata       | Destination airport IATA code                                                                                                                                                                               |
| airport_destination_code_icao       | Destination airport ICAO code                                                                                                                                                                               |
| airport_destination_country_name    | Destination airport country name                                                                                                                                                                            |
| airport_destination_country_code    | Destination airport country code                                                                                                                                                                            |
| airport_destination_city            | Destination airport city name                                                                                                                                                                               |
| airport_destination_timezone_offset | Destination airport timezone offset (in seconds)                                                                                                                                                                 |
| airport_destination_timezone_abbr   | Destination airport timezone abbreviation                                                                                                                                                                        |
| airport_destination_terminal        | Destination airport terminal    
| airport_destination_latitude        | Destination airport latitude
| airport_destination_longitude       | Destination airport longitude
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

## Thanks To
 - [FlightRadarAPI](https://github.com/JeanExtreme002/FlightRadarAPI) by [@JeanExtreme002](https://github.com/JeanExtreme002)
 - [The OpenSky integration](https://github.com/home-assistant/core/tree/dev/homeassistant/components/opensky)

This integration should only be used for your own educational purposes. If you are interested in accessing Flightradar24 data commercially, please contact business@fr24.com. See more information at [Flightradar24's terms and conditions](https://www.flightradar24.com/terms-and-conditions).
