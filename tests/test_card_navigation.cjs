// Dependency-free card regression tests: node --test tests/test_card_navigation.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function fixture(interactive = false) {
  const calls = [];
  const observers = [];
  const elements = new Map(['map', 'map-actions', 'close-details'].map(id => [id, { hidden: true }]));
  const bounds = { getCenter: () => [10, 20], pad() { return this; } };
  const map = {
    options: {},
    dragging: { enable: () => calls.push('drag:on'), disable: () => calls.push('drag:off') },
    touchZoom: { enable: () => calls.push('pinch:on'), disable: () => calls.push('pinch:off') },
    setMaxBounds: value => calls.push(['bounds', value]),
    setView: (center, zoom) => calls.push(['view', center, zoom]),
    fitBounds: value => calls.push(['fit', value]),
    invalidateSize: (options) => calls.push(['size', options]),
    closePopup: () => { card._openPopupFlightId = null; card._lockMapToArea(map); calls.push('close'); },
    removeLayer: value => calls.push(['remove', value]),
  };
  const markers = new Map();
  const layer = () => ({ addTo() { return this; }, removeLayer(marker) { marker.removed = true; } });
  const L = {
    map: (_el, options) => { calls.push(['init', options]); return map; },
    control: { attribution: () => layer() },
    tileLayer: (url, options) => { calls.push(['tiles', url, options]); return layer(); },
    layerGroup: layer,
    latLngBounds: (...corners) => ({ corners, getCenter: () => [10, 20], pad() { return this; } }),
    rectangle: areaBounds => ({ bounds: areaBounds, addTo() { return this; } }),
    divIcon: options => options,
    marker: position => {
      const events = {};
      const popup = { setContent(content) { this.content = content; }, isOpen: () => true, getElement: () => null };
      const marker = { position, events, addTo() { return this; }, bindPopup(content) { popup.content = content; return this; }, on(name, fn) { events[name] = fn; return this; },
        getPopup: () => popup, setLatLng(value) { this.position = value; }, setIcon() {} };
      markers.set(position.join(','), marker);
      return marker;
    },
    DomEvent: { stopPropagation() {} },
  };
  const registry = new Map();
  const context = vm.createContext({ HTMLElement: class {}, window: { L },
    customElements: { define: (name, cls) => registry.set(name, cls) },
    ResizeObserver: class {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe(element) { this.element = element; }
      disconnect() { this.disconnected = true; }
    },
    requestAnimationFrame: callback => callback(), console,
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../custom_components/flightradar24/frontend/flightradar24-card.js'), 'utf8'), context);
  const card = new (registry.get('flightradar24-card'))();
  card._config = { entity: 'sensor.test', interactive_map: interactive, show_tracks: false };
  card.shadowRoot = { getElementById: id => elements.get(id), querySelector: () => ({ style: {} }) };
  card.isConnected = true;
  card._map = map;
  card._areaBounds = bounds;
  card._areaMaxBounds = bounds;
  card._syncAreaCenterMarker = () => {};
  card._drawTracks = () => {};
  card._planeIcon = () => ({});
  card._popupHtml = flight => flight.id;
  card._markers = { addLayer() {}, removeLayer(marker) { marker.removed = true; } };
  return { card, calls, elements, bounds, map, markers, observers };
}

test('initialization keeps legacy gestures disabled and opt-in enables drag/pinch', async () => {
  for (const interactive of [false, true]) {
    const f = fixture(interactive); f.card._map = null;
    await f.card._initMap(f.elements.get('map'));
    const options = f.calls.find(call => Array.isArray(call) && call[0] === 'init')[1];
    assert.equal(options.dragging, interactive);
    assert.equal(options.touchZoom, interactive);
    assert.equal(options.scrollWheelZoom, true);
  }
});

test('changing option on a live card toggles handlers and bounds without rebuilding', () => {
  const f = fixture(true); f.card._configureMapInteraction();
  assert.ok(f.calls.includes('drag:on')); assert.ok(f.calls.includes('pinch:on'));
  assert.deepEqual(f.calls.find(call => call[0] === 'bounds'), ['bounds', null]);
  f.card._config.interactive_map = false; f.card._configureMapInteraction();
  assert.ok(f.calls.includes('drag:off')); assert.ok(f.calls.includes('pinch:off'));
  assert.ok(f.calls.some(call => call[0] === 'fit'));
});

test('popup dismissal remains available and preserves interactive camera', () => {
  const f = fixture(true); f.card._openPopupFlightId = 'flight'; f.card._syncMapControls();
  assert.equal(f.elements.get('map-actions').hidden, false);
  assert.equal(f.elements.get('close-details').hidden, false);
  f.map.closePopup();
  assert.equal(f.elements.get('close-details').hidden, true);
  assert.equal(f.calls.some(call => call[0] === 'fit' || call[0] === 'view'), false);
});

test('legacy popup close still restores monitored area', () => {
  const f = fixture(); f.card._lockMapToArea(f.map);
  assert.ok(f.calls.some(call => call[0] === 'fit'));
  assert.equal(f.elements.get('map-actions').hidden, true);
});

test('explicit reset closes details and restores auto or configured zoom', () => {
  const f = fixture(true); f.card._openPopupFlightId = 'flight'; f.card._resetMapView();
  assert.ok(f.calls.includes('close')); assert.ok(f.calls.some(call => call[0] === 'fit'));
  f.calls.length = 0; f.card._config.zoom = 12; f.card._resetMapView();
  assert.equal(JSON.stringify(f.calls.find(call => call[0] === 'view')), JSON.stringify(['view', [10, 20], 12]));
});

test('flight updates and exits preserve interactive view and remove stale markers', async () => {
  const f = fixture(true);
  const parsed = { north: 10.1, south: 9.9, west: 19.9, east: 20.1, lat: 10, lon: 20 };
  const flight = { id: 'synthetic', latitude: 10, longitude: 20, heading: 0 };
  await f.card._syncMap(parsed, [flight]);
  assert.equal(f.calls.some(call => call[0] === 'bounds'), false);
  f.calls.length = 0;
  await f.card._syncMap(parsed, [{ ...flight, latitude: 10.01 }]);
  assert.equal(f.card._markerById.size, 1);
  assert.equal(f.calls.some(call => call[0] === 'fit' || call[0] === 'view'), false);
  f.card._openPopupFlightId = 'synthetic';
  await f.card._syncMap(parsed, []);
  assert.equal(f.card._markerById.size, 0);
  assert.equal(f.elements.get('close-details').hidden, true);
  assert.equal(f.calls.some(call => call[0] === 'fit' || call[0] === 'view'), false);
});

test('interactive plane selection does not scroll map controls out of the viewport', async () => {
  for (const interactive of [false, true]) {
    const f = fixture(interactive); const selections = [];
    f.card._keepPopupInView = () => {};
    f.card._syncFlightListSelection = value => selections.push(value.scrollToSelected);
    await f.card._syncMap({ north: 10.1, south: 9.9, west: 19.9, east: 20.1, lat: 10, lon: 20 }, [{ id: 'test', latitude: 10, longitude: 20 }]);
    f.card._markerById.get('test').events.popupopen({ popup: {} });
    assert.equal(selections.at(-1), !interactive);
    assert.equal(f.elements.get('close-details').hidden, false);
  }
});

test('interactive popup open does not auto-pan; legacy mode still adjusts', () => {
  const interactive = fixture(true);
  const interactivePans = [];
  interactive.map.panBy = (offset) => interactivePans.push(offset);
  interactive.card._keepPopupInView(
    interactive.map,
    { getLatLng: () => ({ lat: 10, lng: 20 }) },
    {
      isOpen: () => true,
      update() {},
      getElement: () => ({ offsetWidth: 120, offsetHeight: 80 }),
      _adjustPan: () => interactivePans.push('adjust'),
      options: {},
    }
  );
  assert.equal(interactivePans.length, 0);

  const legacy = fixture(false);
  const legacyPans = [];
  legacy.map.panBy = (offset) => legacyPans.push(offset);
  legacy.map.getSize = () => ({ x: 200, y: 200 });
  legacy.map.latLngToContainerPoint = () => ({ x: 100, y: 100 });
  legacy.card._keepPopupInView(
    legacy.map,
    { getLatLng: () => ({ lat: 10, lng: 20 }) },
    {
      isOpen: () => true,
      update() {},
      getElement: () => null,
      _adjustPan: () => legacyPans.push('adjust'),
      options: {},
    }
  );
  assert.equal(legacyPans.length, 1);
  assert.equal(legacyPans[0], 'adjust');
});

test('stub and configuration defaults retain both basemap and interaction options', () => {
  const f = fixture();
  const stub = f.card.constructor.getStubConfig({}, [], []);
  assert.equal(stub.map_style, 'osm');
  assert.equal(stub.interactive_map, false);
  f.card._renderShell = () => {};
  f.card._update = () => {};
  f.card.setConfig({ entity: 'sensor.test' });
  assert.equal(f.card._config.map_style, 'osm');
  assert.equal(f.card._config.interactive_map, false);
});

test('live basemap changes preserve the interactive camera and gesture handlers', () => {
  const f = fixture(true);
  f.card._renderShell = () => {};
  f.card._update = () => {};
  for (const [style, host] of [['osm', 'openstreetmap.org'], ['satellite', 'arcgisonline.com'], ['topo', 'opentopomap.org']]) {
    f.card.setConfig({ entity: 'sensor.test', interactive_map: true, map_style: style });
    const tiles = f.calls.filter(call => call[0] === 'tiles').at(-1);
    assert.ok(tiles[1].includes(host));
    assert.equal(f.card._config.interactive_map, true);
    assert.equal(f.calls.some(call => ['fit', 'view', 'bounds', 'drag:off', 'pinch:off'].includes(call[0])), false);
  }
  assert.equal(f.calls.filter(call => call[0] === 'tiles').at(-1)[2].maxZoom, 17);
  assert.equal(f.calls.filter(call => call[0] === 'remove').length, 2);
});

test('combined editor changes apply gestures and basemap independently', () => {
  const f = fixture();
  f.card._renderShell = () => {};
  f.card._update = () => {};
  f.card.setConfig({ entity: 'sensor.test', interactive_map: true, map_style: 'satellite' });
  assert.ok(f.calls.includes('drag:on'));
  assert.ok(f.calls.includes('pinch:on'));
  assert.ok(f.calls.find(call => call[0] === 'tiles')[1].includes('arcgisonline.com'));
  f.card.setConfig({ entity: 'sensor.test', interactive_map: false, map_style: 'topo' });
  assert.ok(f.calls.includes('drag:off'));
  assert.ok(f.calls.includes('pinch:off'));
  assert.equal(f.card._config.map_style, 'topo');
});


test('area overlay defaults on and can start hidden without losing bounds', async () => {
  const parsed = { north: 10.1, south: 9.9, west: 19.9, east: 20.1, lat: 10, lon: 20 };
  for (const show_area of [undefined, false]) {
    const f = fixture(); f.card._config.show_area = show_area;
    await f.card._syncMap(parsed, []);
    assert.equal(!!f.card._areaRect, show_area !== false);
    assert.ok(f.card._areaBounds); assert.ok(f.card._areaMaxBounds);
  }
});
test('area overlay toggles at unchanged bounds without moving the camera', async () => {
  const f = fixture(true);
  const parsed = { north: 10.1, south: 9.9, west: 19.9, east: 20.1, lat: 10, lon: 20 };
  await f.card._syncMap(parsed, []); const old = f.card._areaRect; f.calls.length = 0;
  f.card._config.show_area = false; await f.card._syncMap(parsed, []);
  assert.equal(f.card._areaRect, null);
  assert.ok(f.calls.some(call => call[0] === 'remove' && call[1] === old));
  f.card._config.show_area = true; await f.card._syncMap(parsed, []);
  assert.ok(f.card._areaRect); assert.notEqual(f.card._areaRect, old);
  assert.equal(f.calls.some(call => ['fit', 'view', 'bounds'].includes(call[0])), false);
});
test('setConfig applies area overlay edits immediately', () => {
  const f = fixture(); f.card._renderShell = () => {}; let updates = 0; f.card._update = () => updates++;
  f.card.setConfig({ entity: 'sensor.test' }); updates = 0;
  assert.equal(f.card._config.show_area, true);
  f.card.setConfig({ entity: 'sensor.test', show_area: false });
  assert.equal(updates, 1);
  assert.equal(f.card.constructor.getStubConfig({}, [], []).show_area, true);
});


test('visible area rectangle follows changed bounds and reuses unchanged bounds', async () => {
  const f = fixture(true);
  const first = { north: 10.1, south: 9.9, west: 19.9, east: 20.1, lat: 10, lon: 20 };
  const next = { ...first, north: 11, east: 21 };
  await f.card._syncMap(first, []);
  const original = f.card._areaRect;
  await f.card._syncMap(first, []);
  assert.equal(f.card._areaRect, original);
  await f.card._syncMap(next, []);
  assert.notEqual(f.card._areaRect, original);
  assert.ok(f.calls.some(call => call[0] === 'remove' && call[1] === original));
  assert.equal(JSON.stringify(f.card._areaRect.bounds.corners), JSON.stringify([[9.9, 19.9], [11, 21]]));
});

test('bounds changed while hidden are used when the area is shown again', async () => {
  const f = fixture(true);
  const first = { north: 10.1, south: 9.9, west: 19.9, east: 20.1, lat: 10, lon: 20 };
  await f.card._syncMap(first, []);
  f.card._config.show_area = false;
  const next = { ...first, north: 11, east: 21 };
  await f.card._syncMap(next, []);
  assert.equal(f.card._areaRect, null);
  assert.equal(JSON.stringify(f.card._areaBounds.corners), JSON.stringify([[9.9, 19.9], [11, 21]]));
  f.calls.length = 0;
  f.card._config.show_area = true;
  await f.card._syncMap(next, []);
  assert.equal(JSON.stringify(f.card._areaRect.bounds.corners), JSON.stringify([[9.9, 19.9], [11, 21]]));
  assert.equal(f.calls.some(call => ['fit', 'view', 'bounds'].includes(call[0])), false);
});

test('area overlay visibility leaves the real center-marker sync independent', async () => {
  const f = fixture(true);
  delete f.card._syncAreaCenterMarker;
  f.card._config.show_area_center = true;
  const parsed = { north: 10.1, south: 9.9, west: 19.9, east: 20.1, lat: 10, lon: 20 };
  await f.card._syncMap(parsed, []);
  const center = f.card._areaCenterMarker;
  assert.ok(center);
  f.card._config.show_area = false;
  await f.card._syncMap(parsed, []);
  assert.equal(f.card._areaCenterMarker, center);
  assert.equal(f.card._areaRect, null);
  assert.equal(f.calls.some(call => call[0] === 'remove' && call[1] === center), false);
});

test('unit defaults preserve existing displays and unsupported values fall back', () => {
  const { card } = fixture();
  card._renderShell = () => {};
  card._update = () => {};
  for (const config of [{}, { altitude_unit: 'unknown', distance_unit: null, speed_unit: 42 }]) {
    card.setConfig({ entity: 'sensor.test', ...config });
    assert.equal(card._formatAltitude(10000), '3048 m (10000 ft)');
    assert.equal(card._formatDistance(1.234), '1234 m');
    assert.equal(card._formatSpeed(100), '185 km/h (100 kts)');
  }
  const stub = card.constructor.getStubConfig({}, [], []);
  assert.equal(stub.altitude_unit, 'both');
  assert.equal(stub.distance_unit, 'm');
  assert.equal(stub.speed_unit, 'both');
});

test('common unit aliases resolve to canonical display options', () => {
  const { card } = fixture();
  card._renderShell = () => {};
  card._update = () => {};
  card.setConfig({
    entity: 'sensor.test',
    altitude_unit: 'feet',
    distance_unit: 'kilometers',
    speed_unit: 'kmh',
  });
  assert.equal(card._config.altitude_unit, 'ft');
  assert.equal(card._config.distance_unit, 'km');
  assert.equal(card._config.speed_unit, 'km/h');
  card.setConfig({ entity: 'sensor.test', speed_unit: 'knots' });
  assert.equal(card._config.speed_unit, 'kts');
  assert.equal(card._formatSpeed(100), '100 kts');
});

test('altitude, distance and speed can each use a single chosen unit', () => {
  const { card } = fixture();
  card._renderShell = () => {};
  card._update = () => {};
  for (const [key, method, source, unit, expected] of [
    ['altitude_unit', '_formatAltitude', 10000, 'm', '3048 m'],
    ['altitude_unit', '_formatAltitude', 10000, 'ft', '10000 ft'],
    ['distance_unit', '_formatDistance', 1.234, 'km', '1.23 km'],
    ['distance_unit', '_formatDistance', 1.609344, 'mi', '1.00 mi'],
    ['distance_unit', '_formatDistance', 1.852, 'nmi', '1.00 nmi'],
    ['speed_unit', '_formatSpeed', 100, 'km/h', '185 km/h'],
    ['speed_unit', '_formatSpeed', 100, 'mph', '115 mph'],
    ['speed_unit', '_formatSpeed', 100, 'kts', '100 kts'],
  ]) {
    card.setConfig({ entity: 'sensor.test', [key]: unit });
    assert.equal(card[method](source), expected);
  }
});

test('unit formatting retains zero and negative altitude, and omits missing or non-finite values', () => {
  const { card } = fixture();
  card._config = { altitude_unit: 'ft', distance_unit: 'mi', speed_unit: 'mph' };
  assert.equal(card._formatAltitude(0), '0 ft');
  assert.equal(card._formatAltitude(-100), '-100 ft');
  assert.equal(card._formatDistance('0'), '0.00 mi');
  assert.equal(card._formatSpeed('0'), '0 mph');
  for (const method of ['_formatAltitude', '_formatDistance', '_formatSpeed']) {
    for (const value of [undefined, null, '', 'unavailable', NaN, Infinity]) {
      assert.equal(card[method](value), null);
    }
  }
});

test('mixed units appear in rows and popups without mutating flight attributes', () => {
  const { card } = fixture();
  card._config = { altitude_unit: 'ft', distance_unit: 'km', speed_unit: 'kts' };
  const flight = Object.freeze({ id: 'test', altitude: 10000, ground_speed: 100, distance: 1.25, closest_distance: 0.5 });
  const snapshot = card._flightRowSnapshot(flight);
  assert.equal(snapshot.altitude, '10000 ft');
  assert.equal(snapshot.speed, '100 kts');
  assert.equal(snapshot.distance, '1.25 km');
  assert.equal(snapshot.closest, '0.50 km');
  const html = card.constructor.prototype._popupHtml.call(card, flight);
  for (const value of ['10000 ft', '100 kts', 'Dist 1.25 km', 'Min 0.50 km']) {
    assert.ok(html.includes(value), value);
  }
});

test('changing units refreshes existing popup content even while flight position is unchanged', async () => {
  const f = fixture(true);
  f.card._renderShell = () => {};
  f.card._popupHtml = f.card.constructor.prototype._popupHtml;
  f.card.setConfig({ entity: 'sensor.test', interactive_map: true, show_tracks: false });
  f.card._selectedFlightId = 'test';
  const parsed = { north: 10.1, south: 9.9, west: 19.9, east: 20.1, lat: 10, lon: 20 };
  const flights = [{ id: 'test', latitude: 10, longitude: 20, altitude: 10000, ground_speed: 100, distance: 1.25 }];
  await f.card._syncMap(parsed, flights);
  const marker = f.card._markerById.get('test');
  const popup = marker.getPopup();
  assert.ok(popup.content.includes('3048 m (10000 ft)'));
  f.card._openPopupFlightId = 'test';
  const updates = [];
  f.card._update = () => { updates.push(f.card._syncMap(parsed, flights)); };
  f.calls.length = 0;
  f.card.setConfig({ entity: 'sensor.test', interactive_map: true, show_tracks: false, altitude_unit: 'ft', distance_unit: 'km', speed_unit: 'kts' });
  assert.equal(updates.length, 1);
  await updates[0];
  assert.equal(f.card._markerById.get('test'), marker);
  assert.equal(f.card._openPopupFlightId, 'test');
  assert.equal(f.card._selectedFlightId, 'test');
  assert.ok(popup.content.includes('10000 ft'));
  assert.ok(popup.content.includes('Dist 1.25 km'));
  assert.ok(popup.content.includes('100 kts'));
  assert.ok(!popup.content.includes('3048 m'));
  assert.equal(f.calls.some(call => ['fit', 'view', 'close'].includes(call[0])), false);
});

test('changing units patches existing flight list meta without recreating the row', () => {
  const { card } = fixture();
  card._renderShell = () => {};
  card._update = () => {};
  const flight = {
    id: 'test',
    altitude: 10000,
    ground_speed: 100,
    distance: 1.25,
    closest_distance: 0.5,
  };
  card.setConfig({ entity: 'sensor.test' });
  const before = card._flightRowSnapshot(flight);
  const spans = [
    { textContent: `Dist ${before.distance}` },
    { textContent: `Closest ${before.closest}` },
    { textContent: before.speed },
    { textContent: before.altitude },
  ];
  const meta = { children: spans, remove() {} };
  const row = {
    classList: { toggle() {} },
    querySelector(sel) {
      if (sel === ':scope > .flight-main') return { querySelector: () => null };
      if (sel === ':scope > .flight-route') return null;
      if (sel === ':scope > .flight-meta') return meta;
      return null;
    },
  };
  card.setConfig({
    entity: 'sensor.test',
    altitude_unit: 'ft',
    distance_unit: 'km',
    speed_unit: 'kts',
  });
  const after = card._flightRowSnapshot(flight);
  card._patchFlightRow(row, after, before);
  assert.equal(spans[0].textContent, 'Dist 1.25 km');
  assert.equal(spans[1].textContent, 'Closest 0.50 km');
  assert.equal(spans[2].textContent, '100 kts');
  assert.equal(spans[3].textContent, '10000 ft');
});

test('list and map icons use helicopter art when aircraft_category is Helicopter', async () => {
  const f = fixture(true);
  f.card._planeIcon = f.card.constructor.prototype._planeIcon;
  const plane = { id: 'p1', heading: 45, aircraft_category: 'Airplane' };
  const heli = { id: 'h1', heading: 45, aircraft_category: 'Helicopter' };
  assert.equal(f.card._flightIcon(plane), 'mdi:airplane');
  assert.equal(f.card._flightIcon(heli), 'mdi:helicopter');
  assert.equal(f.card._flightIcon({ on_ground: 1, aircraft_category: 'Helicopter' }), 'mdi:helicopter');
  const L = { divIcon: (options) => options };
  const planeIcon = f.card._planeIcon(L, plane);
  const heliIcon = f.card._planeIcon(L, heli);
  assert.ok(planeIcon.html.includes('M21 16v-2l-8-5'));
  assert.ok(heliIcon.html.includes('M3,3H17V5H3V3'));
  assert.ok(planeIcon.html.includes('rotate(45deg)'));
  assert.ok(heliIcon.html.includes('rotate(-45deg)'));
  assert.equal(f.card._markerIconKey(heli), '1:45');
  f.card._popupHtml = f.card.constructor.prototype._popupHtml;
  const parsed = { north: 10.1, south: 9.9, west: 19.9, east: 20.1, lat: 10, lon: 20 };
  await f.card._syncMap(parsed, [{
    id: 'h1', latitude: 10, longitude: 20, heading: 10, aircraft_category: 'Airplane',
  }]);
  const marker = f.card._markerById.get('h1');
  assert.equal(marker._frIconKey, '0:10');
  f.calls.length = 0;
  await f.card._syncMap(parsed, [{
    id: 'h1', latitude: 10, longitude: 20, heading: 10, aircraft_category: 'Helicopter',
  }]);
  assert.equal(marker._frIconKey, '1:10');
  assert.equal(f.card._markerById.get('h1'), marker);
});

test('container resize invalidates the existing map without changing its viewport', async () => {
  const f = fixture(true); f.card._map = null;
  await f.card._ensureMap();
  assert.equal(f.observers.length, 1);
  assert.equal(f.observers[0].element, f.elements.get('map'));
  f.calls.length = 0;
  f.observers[0].callback();
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0][0], 'size');
  assert.equal(f.calls[0][1].debounceMoveend, true);
  await f.card._ensureMap();
  assert.equal(f.observers.length, 1);
});

test('disconnect removes resize observation and reinitialization observes again', async () => {
  const f = fixture(true); f.card._map = null;
  await f.card._ensureMap();
  const first = f.observers[0];
  f.card.disconnectedCallback();
  assert.equal(first.disconnected, true);
  assert.equal(f.card._resizeObserver, null);
  f.calls.length = 0;
  first.callback();
  assert.deepEqual(f.calls, []);
  await f.card._ensureMap();
  assert.equal(f.observers.length, 2);
  assert.equal(f.observers[1].element, f.elements.get('map'));
});
