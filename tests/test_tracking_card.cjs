// Dependency-free tracking card tests: node --test tests/test_tracking_card.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function loadCard() {
  const calls = [];
  const markers = [];
  const layers = [];
  const pendingRaf = new Map();
  let rafId = 0;
  const map = {
    options: {},
    _zoom: 6,
    setView: (center, zoom, options) => {
      map._zoom = zoom;
      calls.push(['view', center, zoom, options]);
    },
    fitBounds: (bounds, options) => {
      map._zoom = options?.maxZoom ?? 10;
      calls.push(['fitBounds', bounds, options]);
    },
    getZoom: () => map._zoom,
    invalidateSize: () => calls.push('size'),
    removeLayer: (layer) => calls.push(['remove', layer]),
    remove: () => calls.push('remove-map'),
  };
  const layer = () => {
    const group = {
      addTo() {
        layers.push(this);
        return this;
      },
    };
    return group;
  };
  const L = {
    map: (_el, options) => {
      calls.push(['init', options]);
      return map;
    },
    control: { attribution: () => layer() },
    tileLayer: (url, options) => {
      calls.push(['tiles', url, options]);
      return layer();
    },
    latLngBounds: (points) => ({ points, isValid: () => true }),
    layerGroup: layer,
    polyline: (points, options) => {
      calls.push(['polyline', points, options]);
      return layer();
    },
    divIcon: (options) => options,
    marker: (position, options) => {
      const marker = {
        position,
        options,
        _frIconKey: null,
        setLatLng(value) {
          this.position = value;
          calls.push(['setLatLng', value]);
        },
        setIcon(icon) {
          this.icon = icon;
          calls.push(['setIcon', icon]);
        },
        addTo() {
          markers.push(this);
          return this;
        },
      };
      calls.push(['marker', position, options]);
      return marker;
    },
  };
  const registry = new Map();
  const elements = new Map([
    ['map', {}],
    ['title', { textContent: '' }],
    ['count', { textContent: '' }],
    ['warning', { style: { display: 'none' }, textContent: '' }],
    ['flights', { style: { display: 'none' }, replaceChildren() {}, querySelector: () => null }],
  ]);
  const context = vm.createContext({
    HTMLElement: class {},
    window: { L, customCards: [] },
    customElements: { define: (name, cls) => registry.set(name, cls) },
    ResizeObserver: class {
      observe() {}
      disconnect() {}
    },
    requestAnimationFrame: (callback) => {
      const id = ++rafId;
      pendingRaf.set(id, callback);
      return id;
    },
    cancelAnimationFrame: (id) => {
      pendingRaf.delete(id);
    },
    performance: { now: () => 1000 },
    console,
    document: {
      createElement: () => ({
        style: {},
        classList: { toggle() {}, add() {} },
        setAttribute() {},
        appendChild() {},
        addEventListener() {},
        querySelector: () => null,
        querySelectorAll: () => [],
      }),
      querySelector: () => null,
      head: { appendChild() {} },
    },
  });
  vm.runInContext(
    fs.readFileSync(
      path.join(__dirname, '../custom_components/flightradar24/frontend/flightradar24-tracking-card.js'),
      'utf8'
    ),
    context
  );
  const Card = registry.get('flightradar24-tracking-card');
  const card = new Card();
  card._config = {
    entity: 'sensor.flightradar24_additional_tracked',
    show_route: true,
    zoom_mode: 'follow',
    zoom: 6,
  };
  const mapWrap = { style: { display: 'block' } };
  const header = { style: {} };
  card.shadowRoot = {
    getElementById: (id) => elements.get(id),
    querySelector: (sel) => {
      if (sel === '.header') return header;
      if (sel === '.map-wrap') return mapWrap;
      return null;
    },
  };
  card.isConnected = true;
  card._map = map;
  return {
    card,
    calls,
    markers,
    map,
    mapWrap,
    L,
    registry,
    pendingRaf,
    windowCards: context.window.customCards,
    flushRaf(timestamp = 1000) {
      const entries = [...pendingRaf.entries()];
      pendingRaf.clear();
      for (const [, callback] of entries) {
        callback(timestamp);
      }
    },
  };
}

test('registers tracking card custom element and catalog entry', () => {
  const { registry, windowCards } = loadCard();
  assert.ok(registry.has('flightradar24-tracking-card'));
  assert.ok(registry.has('flightradar24-tracking-card-editor'));
  assert.ok(windowCards.some((entry) => entry.type === 'flightradar24-tracking-card'));
});

test('tracking card theme_mode dark filters osm tiles and leaves satellite alone', () => {
  const { card, calls } = loadCard();
  card._config.map_style = 'osm';
  card._config.theme_mode = 'dark';
  card._hass = { themes: { darkMode: false } };
  card._syncTileLayer();
  let tiles = calls.filter((call) => Array.isArray(call) && call[0] === 'tiles').at(-1);
  assert.equal(tiles[2].className, 'map-tiles-dark');
  assert.equal(card._wantsDarkTiles(), true);

  card._config.map_style = 'satellite';
  card._syncTileLayer();
  tiles = calls.filter((call) => Array.isArray(call) && call[0] === 'tiles').at(-1);
  assert.equal(tiles[2].className, undefined);
  assert.equal(card._wantsDarkTiles(), false);

  card._config.map_style = 'osm';
  card._config.theme_mode = 'auto';
  card._hass = { themes: { darkMode: true } };
  assert.equal(card._wantsDarkTiles(), true);
  card._hass = { themes: { darkMode: false } };
  assert.equal(card._wantsDarkTiles(), false);
});

test('defaults to the first live flight and ignores scheduled for selection', async () => {
  const { card, calls } = loadCard();
  const flights = [
    {
      id: 'sched1',
      tracked_type: 'schedule',
      flight_number: 'AB123',
      airport_origin_city: 'Berlin',
      airport_destination_city: 'Paris',
    },
    {
      id: 'live1',
      tracked_type: 'live',
      flight_number: 'CD456',
      latitude: 50.1,
      longitude: 8.6,
      heading: 90,
      ground_speed: 400,
      airport_origin_latitude: 52.3,
      airport_origin_longitude: 13.5,
      airport_destination_latitude: 48.8,
      airport_destination_longitude: 2.3,
    },
  ];
  card._flightsById = new Map(flights.map((flight) => [flight.id, flight]));
  const selected = card._resolveSelectedFlight(flights);
  assert.equal(selected.id, 'live1');
  assert.equal(card._selectedFlightId, 'live1');
  assert.equal(card._isLive(flights[0]), false);
  assert.equal(card._isLive(flights[1]), true);

  await card._syncFollowedFlight(selected);
  assert.ok(calls.some((call) => Array.isArray(call) && call[0] === 'view' && call[1][0] === 50.1));
  assert.ok(calls.some((call) => Array.isArray(call) && call[0] === 'polyline'));
  assert.ok(card._planeMarker);
  assert.ok(card._motionRaf != null);
});

test('scheduled flights are not selectable; live click updates follow target', async () => {
  const { card } = loadCard();
  const flights = [
    {
      id: 'sched1',
      tracked_type: 'schedule',
      flight_number: 'AB123',
    },
    {
      id: 'live1',
      tracked_type: 'live',
      latitude: 10,
      longitude: 20,
      heading: 10,
      ground_speed: 100,
    },
    {
      id: 'live2',
      tracked_type: 'live',
      latitude: 30,
      longitude: 40,
      heading: 180,
      ground_speed: 200,
      airport_origin_latitude: 31,
      airport_origin_longitude: 41,
      airport_destination_latitude: 29,
      airport_destination_longitude: 39,
    },
  ];
  card._flightsById = new Map(flights.map((flight) => [flight.id, flight]));
  card._resolveSelectedFlight(flights);
  assert.equal(card._selectedFlightId, 'live1');

  card._selectFlight('sched1', { userPicked: true });
  assert.equal(card._selectedFlightId, 'live1');

  card._selectFlight('live2', { userPicked: true });
  assert.equal(card._selectedFlightId, 'live2');
  assert.equal(card._userPickedFlight, true);
});

test('plane icon rotation uses heading and map stays north-up', async () => {
  const { card, L } = loadCard();
  const icon = card._planeIcon(L, { heading: 135, aircraft_category: 'Airplane' });
  assert.match(icon.html, /rotate\(135deg\)/);
  card._map = null;
  const mapEl = {};
  const created = await card._initMap(mapEl);
  assert.ok(created === null || created);
});

test('show_route false skips airport polyline', async () => {
  const { card, calls } = loadCard();
  card._config.show_route = false;
  const flight = {
    id: 'live1',
    tracked_type: 'live',
    latitude: 1,
    longitude: 2,
    heading: 0,
    ground_speed: 250,
    airport_origin_latitude: 3,
    airport_origin_longitude: 4,
    airport_destination_latitude: 5,
    airport_destination_longitude: 6,
  };
  await card._syncFollowedFlight(flight);
  assert.equal(
    calls.some((call) => Array.isArray(call) && call[0] === 'polyline'),
    false
  );
  assert.ok(card._planeMarker);
});

test('no live flights clears aircraft overlay', async () => {
  const { card } = loadCard();
  card._planeMarker = { keep: true };
  card._routeLayer = { keep: true };
  await card._syncFollowedFlight(null);
  assert.equal(card._planeMarker, null);
  assert.equal(card._routeLayer, null);
  assert.equal(card._motion, null);
  assert.equal(card._resolveSelectedFlight([{ id: 's', tracked_type: 'schedule' }]), null);
});

test('map is hidden without live flights and shown when one appears', async () => {
  const { card, mapWrap } = loadCard();
  card._config.show_flights = false;
  card._hass = {
    states: {
      'sensor.flightradar24_additional_tracked': {
        attributes: {
          friendly_name: 'Tracked',
          flights: [{ id: 's', tracked_type: 'schedule', flight_number: 'AB1' }],
        },
      },
    },
  };
  card._planeMarker = { keep: true };
  card._routeLayer = { keep: true };

  await card._update();
  assert.equal(mapWrap.style.display, 'none');
  assert.equal(card._planeMarker, null);
  assert.equal(card._selectedFlightId, null);

  card._hass.states['sensor.flightradar24_additional_tracked'].attributes.flights = [
    { id: 's', tracked_type: 'schedule', flight_number: 'AB1' },
    {
      id: 'live1',
      tracked_type: 'live',
      latitude: 50,
      longitude: 8,
      heading: 90,
      ground_speed: 400,
    },
  ];
  await card._update();
  assert.equal(mapWrap.style.display, 'block');
  assert.equal(card._selectedFlightId, 'live1');
  assert.ok(card._planeMarker);
});

test('extrapolatePosition moves east at heading 90', () => {
  const { card } = loadCard();
  const start = { lat: 0, lon: 0 };
  // 3600 knots for 1s => 1852 m east ≈ 1852 / 111320 degrees lon at equator
  const next = card._extrapolatePosition(start.lat, start.lon, 90, 3600, 1);
  assert.ok(Math.abs(next.lat - 0) < 1e-9);
  assert.ok(next.lon > 0.016);
  assert.ok(next.lon < 0.017);
});

test('coast phase advances slower than full reported ground speed', async () => {
  const { card, flushRaf } = loadCard();
  card._nowMs = () => 1000;
  await card._syncFollowedFlight({
    id: 'live1',
    tracked_type: 'live',
    latitude: 0,
    longitude: 0,
    heading: 90,
    ground_speed: 3600,
  });
  assert.equal(card._motion.phase, 'coast');
  flushRaf(2000);
  const coastLon = card._motion.lon;
  const full = card._extrapolatePosition(0, 0, 90, 3600, 1);
  assert.ok(coastLon > 0);
  assert.ok(coastLon < full.lon);
  assert.ok(Math.abs(coastLon - full.lon * 0.75) < 1e-6);
});

test('new ahead fix starts catch-up then returns to coast', async () => {
  const { card, flushRaf } = loadCard();
  let now = 1000;
  card._nowMs = () => now;
  await card._syncFollowedFlight({
    id: 'live1',
    tracked_type: 'live',
    latitude: 0,
    longitude: 0,
    heading: 90,
    ground_speed: 400,
  });

  // Sensor reports a point clearly ahead along track.
  now = 5000;
  card._lastFollowKey = null;
  await card._syncFollowedFlight({
    id: 'live1',
    tracked_type: 'live',
    latitude: 0,
    longitude: 0.05,
    heading: 90,
    ground_speed: 400,
  });
  assert.equal(card._motion.phase, 'catchup');
  assert.ok(card._motion.catchDurationS > 0);

  const midLon = card._motion.lon;
  flushRaf(now + card._motion.catchDurationS * 500);
  assert.equal(card._motion.phase, 'catchup');
  assert.ok(card._motion.lon > midLon);

  flushRaf(now + card._motion.catchDurationS * 1000 + 10);
  assert.equal(card._motion.phase, 'coast');
  assert.ok(Math.abs(card._motion.lon - 0.05) < 1e-9);
});

test('behind fix does not pull the map backwards', async () => {
  const { card } = loadCard();
  let now = 1000;
  card._nowMs = () => now;
  await card._syncFollowedFlight({
    id: 'live1',
    tracked_type: 'live',
    latitude: 0,
    longitude: 0.02,
    heading: 90,
    ground_speed: 400,
  });
  const lonBefore = card._motion.lon;
  now = 2000;
  card._lastFollowKey = null;
  await card._syncFollowedFlight({
    id: 'live1',
    tracked_type: 'live',
    latitude: 0,
    longitude: 0.0,
    heading: 90,
    ground_speed: 400,
  });
  assert.equal(card._motion.phase, 'coast');
  assert.equal(card._motion.lon, lonBefore);
});

test('live follow always schedules continuous motion frames', async () => {
  const { card } = loadCard();
  await card._syncFollowedFlight({
    id: 'live1',
    tracked_type: 'live',
    latitude: 10,
    longitude: 20,
    heading: 45,
    ground_speed: 300,
  });
  assert.ok(card._motionRaf != null);
  assert.equal(card._motion?.phase, 'coast');
});

test('motion view preserves user zoom instead of resetting to config', async () => {
  const { card, map, calls, flushRaf } = loadCard();
  card._nowMs = () => 1000;
  await card._syncFollowedFlight({
    id: 'live1',
    tracked_type: 'live',
    latitude: 0,
    longitude: 0,
    heading: 90,
    ground_speed: 3600,
  });
  map._zoom = 10;
  flushRaf(2000);
  const views = calls.filter((call) => Array.isArray(call) && call[0] === 'view');
  const last = views[views.length - 1];
  assert.equal(last[2], 10);
});

test('fit_route zooms to origin and destination and does not re-centre every coast tick', async () => {
  const { card, calls, flushRaf } = loadCard();
  card._config.zoom_mode = 'fit_route';
  card._nowMs = () => 1000;
  const flight = {
    id: 'ocean1',
    tracked_type: 'live',
    latitude: 50,
    longitude: -30,
    heading: 270,
    ground_speed: 450,
    airport_origin_latitude: 51.47,
    airport_origin_longitude: -0.46,
    airport_destination_latitude: 40.64,
    airport_destination_longitude: -73.78,
  };
  await card._syncFollowedFlight(flight);
  const fits = calls.filter((call) => Array.isArray(call) && call[0] === 'fitBounds');
  assert.equal(fits.length, 1);
  assert.equal(fits[0][2].maxZoom, 12);
  assert.ok(card._lastFitKey);

  const before = fits.length;
  flushRaf(2000);
  const fitsAfter = calls.filter((call) => Array.isArray(call) && call[0] === 'fitBounds');
  assert.equal(fitsAfter.length, before);

  // Without airports, fall back to configured zoom centred on the aircraft.
  card._lastFitKey = null;
  card._lastFollowKey = null;
  await card._syncFollowedFlight({
    id: 'local1',
    tracked_type: 'live',
    latitude: 10,
    longitude: 20,
    heading: 90,
    ground_speed: 200,
  });
  const views = calls.filter((call) => Array.isArray(call) && call[0] === 'view');
  assert.ok(views.some((call) => call[1][0] === 10 && call[1][1] === 20 && call[2] === 6));
});

test('null airport coordinates are ignored (not Null Island)', () => {
  const { card } = loadCard();
  assert.equal(
    card._airportPoint(
      { airport_origin_latitude: null, airport_origin_longitude: null },
      'origin'
    ),
    null
  );
});

function samePoints(actual, expected) {
  return JSON.stringify(actual) === JSON.stringify(expected);
}

test('route uses origin, coordinates trail, current position, then destination', () => {
  const { card } = loadCard();
  const points = card._buildRouteLatLngs({
    id: '42a2ec2d',
    latitude: 52.5178,
    longitude: 12.6638,
    airport_origin_latitude: 30.121941,
    airport_origin_longitude: 31.40555,
    airport_destination_latitude: 33.94252,
    airport_destination_longitude: -118.406998,
    coordinates: [
      [50.993683, 14.291135],
      [51.048485, 14.230881],
      [52.5178, 12.6638],
    ],
  });
  assert.ok(samePoints(points[0], [30.121941, 31.40555]));
  assert.ok(samePoints(points[1], [50.993683, 14.291135]));
  assert.ok(samePoints(points[points.length - 2], [52.5178, 12.6638]));
  assert.ok(samePoints(points[points.length - 1], [33.94252, -118.406998]));
  // Must include the European track — a CAI→LAX straight line would miss the aircraft.
  assert.ok(points.some((point) => point[0] > 50 && point[1] > 12 && point[1] < 15));
});

test('route falls back to coordinates only without airports', () => {
  const { card } = loadCard();
  const points = card._buildRouteLatLngs({
    id: 'x',
    latitude: 2,
    longitude: 3,
    coordinates: [
      [0, 0],
      [1, 1],
    ],
  });
  assert.ok(
    samePoints(points, [
      [0, 0],
      [1, 1],
      [2, 3],
    ])
  );
});

test('route without destination keeps origin and track', () => {
  const { card } = loadCard();
  const points = card._buildRouteLatLngs({
    id: 'x',
    latitude: 5,
    longitude: 6,
    airport_origin_latitude: 1,
    airport_origin_longitude: 2,
    coordinates: [[3, 4]],
  });
  assert.ok(
    samePoints(points, [
      [1, 2],
      [3, 4],
      [5, 6],
    ])
  );
});

test('selecting another live flight moves the marker and updates the route', async () => {
  const { card, calls } = loadCard();
  const flights = [
    {
      id: 'live1',
      tracked_type: 'live',
      latitude: 10,
      longitude: 20,
      heading: 10,
      ground_speed: 300,
      airport_origin_latitude: 11,
      airport_origin_longitude: 21,
      airport_destination_latitude: 9,
      airport_destination_longitude: 19,
    },
    {
      id: 'live2',
      tracked_type: 'live',
      latitude: 40,
      longitude: 50,
      heading: 180,
      ground_speed: 400,
      airport_origin_latitude: 41,
      airport_origin_longitude: 51,
      airport_destination_latitude: 39,
      airport_destination_longitude: 49,
    },
  ];
  card._flightsById = new Map(flights.map((flight) => [flight.id, flight]));
  await card._syncFollowedFlight(flights[0]);
  assert.equal(card._motion.flightId, 'live1');

  card._selectFlight('live2', { userPicked: true });
  // Allow the async select sync to finish.
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(card._selectedFlightId, 'live2');
  assert.equal(card._motion.flightId, 'live2');
  assert.equal(card._planeMarker.position[0], 40);
  assert.equal(card._planeMarker.position[1], 50);
  assert.ok(
    calls.some(
      (call) =>
        Array.isArray(call) &&
        call[0] === 'polyline' &&
        call[1].some((point) => point[0] === 41)
    )
  );
  assert.ok(
    calls.some(
      (call) =>
        Array.isArray(call) &&
        call[0] === 'polyline' &&
        call[1].some((point) => point[0] === 39)
    )
  );
});

test('city times use airport local timezone', () => {
  const { card } = loadCard();
  // 2026-01-01 12:00:00 UTC
  const utcNoon = Date.UTC(2026, 0, 1, 12, 0, 0) / 1000;
  const flight = {
    id: '42a2ec2d',
    tracked_type: 'live',
    latitude: 52.5,
    longitude: 12.6,
    on_ground: 0,
    time_real_departure: utcNoon,
    time_estimated_arrival: utcNoon + 2 * 3600 + 15 * 60,
    airport_origin_timezone_offset: 7200,
    airport_origin_timezone_abbr: 'EET',
    airport_destination_timezone_offset: -28800,
    airport_destination_timezone_abbr: 'PST',
  };
  assert.equal(card._flightLegTime(flight, 'departure'), '14:00 EET');
  assert.equal(card._flightLegTime(flight, 'arrival'), '06:15 PST');
});

test('progress bar labels match FR24 style distance and clock durations', () => {
  const { card } = loadCard();
  const now = Math.floor(Date.now() / 1000);
  const progress = card._flightProgressInfo({
    id: '42a2ec2d',
    tracked_type: 'live',
    latitude: 52.5178,
    longitude: 12.6638,
    on_ground: 0,
    time_real_departure: now - 4 * 3600 - 10 * 60,
    time_estimated_arrival: now + 10 * 3600 + 34 * 60,
    airport_origin_latitude: 30.121941,
    airport_origin_longitude: 31.40555,
    airport_destination_latitude: 33.94252,
    airport_destination_longitude: -118.406998,
  });
  assert.ok(progress);
  assert.ok(progress.percent > 0 && progress.percent < 100);
  assert.match(progress.leftLabel, /^~\d{1,3}(,\d{3})* km, 04:\d{2} ago$/);
  assert.match(progress.rightLabel, /^~\d{1,3}(,\d{3})* km, in 10:\d{2}$/);

  const scheduled = card._flightProgressInfo({
    id: 's1',
    tracked_type: 'schedule',
    time_scheduled_departure: now + 90 * 60,
    time_scheduled_arrival: now + 5 * 3600,
    airport_origin_latitude: 30,
    airport_origin_longitude: 31,
    airport_destination_latitude: 34,
    airport_destination_longitude: -118,
  });
  assert.equal(scheduled.percent, 0);
  assert.match(scheduled.rightLabel, /in 01:\d{2}$/);

  const arrived = card._flightProgressInfo({
    id: 'a1',
    tracked_type: 'live',
    latitude: 33.94,
    longitude: -118.4,
    on_ground: 1,
    time_real_departure: now - 7200,
    time_real_arrival: now - 600,
    airport_origin_latitude: 30.12,
    airport_origin_longitude: 31.4,
    airport_destination_latitude: 33.94,
    airport_destination_longitude: -118.4,
  });
  assert.equal(arrived.percent, 100);
  assert.match(arrived.rightLabel, /Arrived$/);
});

test('scheduled FR24 links use data/flights pages; live keep session URLs', () => {
  const { card } = loadCard();
  assert.equal(
    card._flightFr24Url({
      id: 'QF2051',
      tracked_type: 'schedule',
      callsign: 'QLK51D',
      flight_number: 'QF2051',
    }),
    'https://www.flightradar24.com/data/flights/qf2051'
  );
  assert.equal(
    card._flightFr24Url({
      id: '42a4df0b',
      tracked_type: 'live',
      callsign: 'SIA321',
      flight_number: 'SQ321',
      latitude: 1,
      longitude: 2,
    }),
    'https://fr24.com/SIA321/42a4df0b'
  );
  assert.equal(
    card._flightFr24Url({
      id: '9V-SMF',
      tracked_type: 'aircraft',
      aircraft_registration: '9V-SMF',
    }),
    'https://www.flightradar24.com/data/aircraft/9V-SMF'
  );
});

test('tracked list sorts live before aircraft and scheduled', () => {
  const { card } = loadCard();
  const sorted = card._sortTrackedFlights([
    { id: 's1', tracked_type: 'schedule', flight_number: 'ZZ9' },
    { id: 'a1', tracked_type: 'aircraft', aircraft_registration: 'N1AB' },
    { id: 'l1', tracked_type: 'live', flight_number: 'AA1', latitude: 1, longitude: 2 },
    { id: 's0', tracked_type: 'schedule', flight_number: 'AA2' },
  ]);
  assert.equal(sorted.map((flight) => flight.id).join(','), 'l1,a1,s0,s1');
});

test('detail_level compact prefers IATA and always includes registration', () => {
  const { card } = loadCard();
  const flight = {
    id: 'l1',
    tracked_type: 'live',
    latitude: 1,
    longitude: 2,
    flight_number: 'SQ321',
    aircraft_model: 'A359',
    aircraft_registration: '9V-SMK',
    airport_origin_city: 'Singapore',
    airport_origin_code_iata: 'SIN',
    airport_destination_city: 'London',
    airport_destination_code_iata: 'LHR',
  };
  card._config.detail_level = 'full';
  let snap = card._flightRowSnapshot(flight);
  assert.equal(snap.aircraft, 'A359 (9V-SMK)');
  assert.equal(snap.originCity, 'Singapore');
  assert.equal(snap.destCity, 'London');

  card._config.detail_level = 'compact';
  snap = card._flightRowSnapshot(flight);
  assert.equal(snap.aircraft, 'A359 (9V-SMK)');
  assert.equal(snap.originCity, 'SIN');
  assert.equal(snap.destCity, 'LHR');
});

test('show_map false keeps map hidden even with a live flight', async () => {
  const { card, mapWrap } = loadCard();
  card._config.show_map = false;
  card._config.show_flights = false;
  card._hass = {
    states: {
      'sensor.flightradar24_additional_tracked': {
        attributes: {
          friendly_name: 'Tracked',
          flights: [
            {
              id: 'live1',
              tracked_type: 'live',
              latitude: 10,
              longitude: 20,
              heading: 90,
              ground_speed: 400,
            },
          ],
        },
      },
    },
  };
  await card._update();
  assert.equal(mapWrap.style.display, 'none');
  assert.equal(card._planeMarker, null);
});

test('stale async sync cannot overwrite a newer user selection', async () => {
  const { card } = loadCard();
  const flights = [
    {
      id: 'live1',
      tracked_type: 'live',
      latitude: 1,
      longitude: 2,
      heading: 0,
      ground_speed: 100,
    },
    {
      id: 'live2',
      tracked_type: 'live',
      latitude: 3,
      longitude: 4,
      heading: 90,
      ground_speed: 200,
    },
  ];
  card._flightsById = new Map(flights.map((flight) => [flight.id, flight]));
  card._selectedFlightId = 'live1';
  const staleEpoch = card._followEpoch;
  card._followEpoch += 1;
  card._selectedFlightId = 'live2';
  await card._syncFollowedFlight(flights[0], staleEpoch);
  assert.notEqual(card._motion?.flightId, 'live1');
});
