# Flightradar24 integration for Home Assistant
Flightradar24 integration allows one to track overhead flights in a given region. It will also fire Home Assistant events when flights enter and exit the defined region.

<b>IMPORTANT: No need FlightRadar24 subscription!</b>

It allows you:
1) Know how many flights in your area right now, or just have entered or exited it. And get list of flights with [full information](#flight) by every relevant flight for the sensor
2) Create automations (example - [Get a notification when a flight enters or exits your area](#notification))
3) Add flights table to your [Home Assistant dashboard](https://www.home-assistant.io/dashboards/) by [Lovelace Card](#lovelace))

<img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/lovelace.png" width="48%"> <img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/sensors.png" width="48%">

## Components
### Events
 - flightradar24_entry: Fired when a flight enters the region.
 - flightradar24_exit: Fired when a flight exits the region.

### Sensors
 - Current in area
 - Entered area
 - Exited area

Sensors shows how many flights in the given area, just have entered or exited it. All sensors have attribute `flights` with list of [flight object](#flight) contained a full information by every relevant flight for the sensor

## Installation

### HACS (recommended)

Have [HACS](https://hacs.xyz/) installed, this will allow you to update easily.

1. Go to the <b>Hacs</b>-><b>Integrations</b>.
2. Add this repository (https://github.com/AlexandrErohin/home-assistant-flightradar24) as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories/)
3. Click on `+ Explore & Download Repositories`, search for `Flightradar24`. 
4. Search for `Flightradar24`. 
5. Navigate to `Flightradar24` integration 
6. Press `DOWNLOAD` and in the next window also press `DOWNLOAD`. 
7. After download, restart Home Assistant.

### Manual

1. Locate the `custom_components` directory in your Home Assistant configuration directory. It may need to be created.
2. Copy the `custom_components/flightradar24` directory into the `custom_components` directory.
3. Restart Home Assistant.

## Configuration
Flightradar24 is configured via the GUI. See [the HA docs](https://www.home-assistant.io/getting-started/integration/) for more details.

The default data is preset already

<img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/config_flow.png" width="48%">

1. Go to the <b>Settings</b>-><b>Devices & services</b>.
2. Click on `+ ADD INTEGRATION`, search for `Flightradar24`.
3. You may change the default values for Radius, Latitude and Longitude
4. Click `SUBMIT`

### Edit Configuration
You may edit configuration data like radius or coordinates.

If you have FlightRadar24 subscription, you may authenticate also

To do that

1. Go to the <b>Settings</b>-><b>Devices & services</b>.
2. Search for `Flightradar24`, and click on it.
3. Click on `CONFIGURE`
4. Edit the options you need and click `SUBMIT`

## Uses
### <a id="notification">Notification</a>
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
        message: "Flight entry of {{ trigger.event.data.callsign }} to {{ trigger.event.data.airport_destination_city }}"
```

All available fields in `trigger.event.data` you can check [here](#flight)

### <a id="lovelace">Lovelace Card</a>
You can add flight table to your [Home Assistant dashboard](https://www.home-assistant.io/dashboards/)

<img src="https://raw.githubusercontent.com/AlexandrErohin/home-assistant-flightradar24/master/docs/media/lovelace.png" width="48%">

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
        'flights') %} {% for flight in data %}
          <ha-icon icon="mdi:airplane"></ha-icon>{{ flight.flight_number }} - {{ flight.airline_short }} - {{ flight.aircraft_model }}
          {{ flight.airport_origin_city }}{%if flight.airport_origin_city %}<img src="https://flagsapi.com/{{ flight.airport_origin_country_code }}/shiny/16.png" title='{{ flight.airport_origin_country_name }}'/>{% endif %} -> {{ flight.airport_destination_city }}{%
          if flight.airport_destination_country_code %}<img src="https://flagsapi.com/{{ flight.airport_destination_country_code }}/shiny/16.png" title='{{ flight.airport_destination_country_name }}'/>{% endif %}
          {%if flight.time_scheduled_departure %}Departure - {{ flight.time_scheduled_departure | timestamp_custom('%H:%M') }}; {% endif %}{%if flight.time_scheduled_arrival%}Arrival - {{ flight.time_scheduled_arrival | timestamp_custom('%H:%M') }}{% endif %}
          Altitude - {{ flight.altitude }} ft{%if flight.altitude > 0 %} ({{(flight.altitude * 0.3048)| round(0)}} m){% endif%}; Gr. speed - {{ flight.ground_speed }} kts{%if flight.ground_speed > 0 %} ({{(flight.ground_speed * 1.852)| round(0)}} km/h){% endif%}
          {% endfor %}
```

All available fields for flight you can check [here](#flight)

## Database decrease
To decrease data stored by [Recorder](https://www.home-assistant.io/integrations/recorder/) in database add following lines to your `configuration.yaml` file:
```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.flightradar24*
```

## <a id="flight">Flight fields</a>
| Field | Description |
| --- |---|
| flight_number | Flight Number |
| latitude | Current latitude of the aircraft |
| longitude | Current longitude of the aircraft |
| altitude | Altitude (measurement: foot) |
| ground_speed | Ground speed (measurement: knots) |
| squawk | Squawk code are what air traffic control (ATC) use to identify aircraft when they are flying **(for subscription only)** |
| vertical_speed | Vertical speed **(for subscription only)** |
| heading | The compass direction in which the craft's bow or nose is pointed (measurement: degrees) |
| callsign | Callsign of the flight |
| aircraft_registration | Aircraft registration number |
| aircraft_photo_small | Aircraft small size photo url |
| aircraft_photo_medium | Aircraft medium size photo url |
| aircraft_photo_large | Aircraft large size photo url |
| aircraft_model | Aircraft model |
| aircraft_code | Aircraft code |
| airline | Airline full name |
| airline_short | Airline short name |
| airline_iata | Airline IATA code |
| airline_icao | Airline ICAO code |
| airport_origin_name | Origin airport name |
| airport_origin_code_iata | Origin airport IATA code |
| airport_origin_code_icao | Origin airport ICAO code |
| airport_origin_country_name | Origin airport country name |
| airport_origin_country_code | Origin airport country code |
| airport_origin_city | Origin airport city name |
| airport_destination_name | Destination airport name |
| airport_destination_code_iata | Destination airport IATA code |
| airport_destination_code_icao | Destination airport ICAO code |
| airport_destination_country_name | Destination airport country name |
| airport_destination_country_code | Destination airport country code |
| airport_destination_city | Destination airport city name |
| time_scheduled_departure | Scheduled departure time |
| time_scheduled_arrival | Scheduled arrival time |
| time_real_departure | Real departure time |
| time_real_arrival | Real arrival time |
| time_estimated_departure | Estimated departure time |
| time_estimated_arrival | Estimated arrival time |

## Thanks To
 - [FlightRadarAPI](https://github.com/JeanExtreme002/FlightRadarAPI) by [@JeanExtreme002](https://github.com/JeanExtreme002)
 - [The OpenSky integration](https://github.com/home-assistant/core/tree/dev/homeassistant/components/opensky)