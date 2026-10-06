// Dependency-free card regression tests: node --test tests/test_card_navigation.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function fixture(interactive = false) {
  const calls = [];
  const elements = new Map(['map', 'map-actions', 'close-details'].map(id => [id, { hidden: true }]));
  const bounds = { getCenter: () => [10, 20], pad() { return this; } };
  const map = {
    options: {},
    dragging: { enable: () => calls.push('drag:on'), disable: () => calls.push('drag:off') },
    touchZoom: { enable: () => calls.push('pinch:on'), disable: () => calls.push('pinch:off') },
    setMaxBounds: value => calls.push(['bounds', value]),
    setView: (center, zoom) => calls.push(['view', center, zoom]),
    fitBounds: value => calls.push(['fit', value]),
    invalidateSize: () => calls.push('size'),
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
    latLngBounds: () => bounds, rectangle: () => ({ addTo() { return this; } }),
    marker: position => {
      const events = {};
      const popup = { setContent() {}, isOpen: () => true, getElement: () => null };
      const marker = { position, events, bindPopup() { return this; }, on(name, fn) { events[name] = fn; return this; },
        getPopup: () => popup, setLatLng(value) { this.position = value; }, setIcon() {} };
      markers.set(position.join(','), marker);
      return marker;
    },
    DomEvent: { stopPropagation() {} },
  };
  const registry = new Map();
  const context = vm.createContext({ HTMLElement: class {}, window: { L },
    customElements: { define: (name, cls) => registry.set(name, cls) },
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
  return { card, calls, elements, bounds, map, markers };
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
