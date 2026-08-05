/**
 * Flightradar24 Lovelace card.
 * OpenStreetMap viewport from sensor `bounds`, with aircraft
 * markers from the `flights` attribute (latitude / longitude).
 */
const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

let leafletLoader = null;

function loadLeaflet() {
  if (window.L) {
    return Promise.resolve(window.L);
  }
  if (leafletLoader) {
    return leafletLoader;
  }
  leafletLoader = new Promise((resolve, reject) => {
    if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = LEAFLET_CSS;
      document.head.appendChild(link);
    }
    const existing = document.querySelector(`script[src="${LEAFLET_JS}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve(window.L));
      existing.addEventListener("error", reject);
      if (window.L) {
        resolve(window.L);
      }
      return;
    }
    const script = document.createElement("script");
    script.src = LEAFLET_JS;
    script.onload = () => resolve(window.L);
    script.onerror = reject;
    document.head.appendChild(script);
  });
  return leafletLoader;
}

class Flightradar24Card extends HTMLElement {
  static getStubConfig(hass, entities, entitiesFallback) {
    const candidates = [
      ...(entities || []),
      ...(entitiesFallback || []),
    ];
    const entity =
      candidates.find((entityId) => {
        const state = hass?.states?.[entityId];
        return (
          state &&
          Array.isArray(state.attributes?.flights) &&
          typeof state.attributes?.bounds === "string"
        );
      }) ||
      candidates.find((entityId) => entityId.includes("flightradar24")) ||
      "";
    return {
      entity,
      show_flights: true,
      show_tracks: true,
    };
  }

  static getConfigElement() {
    return document.createElement("flightradar24-card-editor");
  }

  constructor() {
    super();
    this._map = null;
    this._mapInitPromise = null;
    this._markers = null;
    this._tracks = null;
    this._areaRect = null;
    this._markerById = new Map();
    this._selectedFlightId = null;
    this._openPopupFlightId = null;
    this._rebuildingMarkers = false;
    this._areaBounds = null;
    this._areaMaxBounds = null;
    this._maxBoundsSuspended = false;
    this._lastBoundsKey = null;
    this._lastFlightsKey = null;
    this._lastEntity = null;
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Please define an entity");
    }
    const prev = this._config;
    this._config = {
      show_flights: true,
      show_tracks: true,
      ...config,
    };
    if (prev && prev.entity !== this._config.entity) {
      this._lastBoundsKey = null;
      this._lastFlightsKey = null;
      this._lastEntity = null;
      this._openPopupFlightId = null;
      this._selectedFlightId = null;
      this._markerById = new Map();
    } else if (prev && prev.show_tracks !== this._config.show_tracks) {
      // Force marker/track redraw when the option changes.
      this._lastFlightsKey = null;
    }
    this._renderShell();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  getCardSize() {
    const flights = this._config?.show_flights !== false ? 2 : 0;
    return 4 + flights;
  }

  getGridOptions() {
    return {
      columns: 12,
      min_columns: 6,
      rows: this.getCardSize(),
    };
  }

  connectedCallback() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this._renderShell();
    this._update();
  }

  disconnectedCallback() {
    this._destroyMap();
  }

  _destroyMap() {
    if (this._map) {
      try {
        this._map.remove();
      } catch (_error) {
        // ignore — container may already be gone on refresh
      }
      this._map = null;
    }
    this._mapInitPromise = null;
    const mapEl = this.shadowRoot?.getElementById("map");
    if (mapEl) {
      // Leaflet leaves _leaflet_id on the node; clear so re-init works.
      if (mapEl._leaflet_id) {
        delete mapEl._leaflet_id;
      }
      mapEl.innerHTML = "";
    }
    this._markers = null;
    this._tracks = null;
    this._areaRect = null;
    this._markerById = new Map();
    this._selectedFlightId = null;
    this._openPopupFlightId = null;
    this._rebuildingMarkers = false;
    this._areaBounds = null;
    this._areaMaxBounds = null;
    this._maxBoundsSuspended = false;
    this._lastBoundsKey = null;
    this._lastFlightsKey = null;
  }

  _parseBounds(bounds) {
    if (!bounds || typeof bounds !== "string") {
      return null;
    }
    const parts = bounds.split(",").map((value) => Number(value.trim()));
    if (parts.length !== 4 || parts.some((value) => Number.isNaN(value))) {
      return null;
    }
    const [north, south, west, east] = parts;
    return {
      north,
      south,
      west,
      east,
      lat: (north + south) / 2,
      lon: (west + east) / 2,
    };
  }

  _escape(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  _flightLabel(flight) {
    return (
      flight.flight_number ||
      flight.callsign ||
      flight.aircraft_registration ||
      "—"
    );
  }

  /**
   * Icon by flight phase: on ground, climbing, descending, or level.
   * on_ground: 0 in air, 1 on ground. vertical_speed in ft/min.
   */
  _flightIcon(flight) {
    if (Number(flight.on_ground) === 1 || flight.on_ground === true) {
      return "mdi:airplane-check";
    }
    const vs = Number(flight.vertical_speed);
    if (!Number.isNaN(vs)) {
      if (vs > 0) {
        return "mdi:airplane-takeoff";
      }
      if (vs < 0) {
        return "mdi:airplane-landing";
      }
    }
    return "mdi:airplane";
  }

  _formatNumber(value, digits = 0) {
    if (value == null || value === "") {
      return null;
    }
    const number = Number(value);
    if (Number.isNaN(number)) {
      return String(value);
    }
    return number.toFixed(digits);
  }

  /** Ground speed: km/h with knots in parentheses. Source unit is knots. */
  _formatSpeed(knots) {
    if (knots == null || knots === "") {
      return null;
    }
    const kts = Number(knots);
    if (Number.isNaN(kts)) {
      return null;
    }
    const kmh = Math.round(kts * 1.852);
    return `${kmh} km/h (${Math.round(kts)} kts)`;
  }

  /** Altitude: meters with feet in parentheses. Source unit is feet. */
  _formatAltitude(feet) {
    if (feet == null || feet === "") {
      return null;
    }
    const ft = Number(feet);
    if (Number.isNaN(ft)) {
      return null;
    }
    const meters = Math.round(ft * 0.3048);
    return `${meters} m (${Math.round(ft)} ft)`;
  }

  /** Distance: meters. Source unit is kilometers. */
  _formatDistance(kilometers) {
    if (kilometers == null || kilometers === "") {
      return null;
    }
    const km = Number(kilometers);
    if (Number.isNaN(km)) {
      return null;
    }
    return `${Math.round(km * 1000)} m`;
  }

  _flagHtml(countryCode, title) {
    if (!countryCode || String(countryCode).length !== 2) {
      return "";
    }
    const code = String(countryCode).toUpperCase();
    const lower = code.toLowerCase();
    const label = title || code;
    // Served from the integration static path — avoids CSP / theme issues
    // with third-party flag CDNs (blank white squares).
    return (
      `<img class="flag" src="/flightradar24/flags/${this._escape(lower)}.svg" ` +
      `width="16" height="12" alt="${this._escape(code)}" ` +
      `title="${this._escape(label)}" loading="lazy" ` +
      `onerror="this.style.display='none'" />`
    );
  }

  _flightRow(flight) {
    const number = this._flightLabel(flight);
    const originCity = flight.airport_origin_city || "";
    const destCity = flight.airport_destination_city || "";
    const originFlag = this._flagHtml(
      flight.airport_origin_country_code,
      flight.airport_origin_country_name || flight.airport_origin_country_code
    );
    const destFlag = this._flagHtml(
      flight.airport_destination_country_code,
      flight.airport_destination_country_name ||
        flight.airport_destination_country_code
    );
    const routeParts = [];
    if (originCity || originFlag) {
      routeParts.push(
        `${originFlag}<span>${this._escape(originCity || "—")}</span>`
      );
    }
    if (destCity || destFlag) {
      routeParts.push(
        `${destFlag}<span>${this._escape(destCity || "—")}</span>`
      );
    }
    const route = routeParts.length
      ? routeParts.join('<span class="route-sep">→</span>')
      : "";

    const distance = this._formatDistance(flight.distance);
    const closest = this._formatDistance(flight.closest_distance);
    const speed = this._formatSpeed(flight.ground_speed);
    const altitude = this._formatAltitude(flight.altitude);

    const stats = [
      distance != null ? `Dist ${distance}` : "",
      closest != null ? `Closest ${closest}` : "",
      speed || "",
      altitude || "",
    ]
      .filter(Boolean)
      .map((item) => `<span>${this._escape(item)}</span>`)
      .join("");

    return `
      <div class="flight">
        <div class="flight-main">
          <ha-icon icon="${this._flightIcon(flight)}"></ha-icon>
          <strong>${this._escape(number)}</strong>
          <span class="muted">${this._escape(flight.airline_short || flight.airline || "")}</span>
        </div>
        ${
          route
            ? `<div class="flight-route">${route}</div>`
            : ""
        }
        ${stats ? `<div class="flight-meta">${stats}</div>` : ""}
      </div>
    `;
  }

  _styles() {
    return `
      :host { display: block; }
      ha-card { overflow: hidden; }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        padding: 12px 16px 8px;
        gap: 8px;
      }
      .header h2 {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 500;
        color: var(--primary-text-color);
      }
      .count {
        color: var(--secondary-text-color);
        font-size: 0.9rem;
      }
      .map-wrap {
        position: relative;
        width: 100%;
        aspect-ratio: 16 / 10;
        background: var(--divider-color);
        z-index: 0;
      }
      #map {
        width: 100%;
        height: 100%;
      }
      /* HA dark themes inherit light text; force readable OSM credit. */
      .leaflet-control-attribution {
        background: rgba(255, 255, 255, 0.9);
        color: #333;
        font-size: 11px;
        line-height: 1.3;
        max-width: calc(100% - 10px);
        margin: 0;
        padding: 2px 6px;
        box-sizing: border-box;
      }
      .leaflet-control-attribution a {
        color: #0078a8;
      }
      .warning, .empty {
        padding: 16px;
        color: var(--secondary-text-color);
      }
      .flights {
        padding: 8px 16px 16px;
        display: flex;
        flex-direction: column;
        gap: 10px;
        max-height: 280px;
        overflow: auto;
      }
      .flight {
        border-top: 1px solid var(--divider-color);
        padding-top: 8px;
      }
      .flight-main {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--primary-text-color);
      }
      .flight-main ha-icon {
        --mdc-icon-size: 18px;
        color: var(--state-icon-color, var(--primary-color));
      }
      .flight-route,
      .flight-meta {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 6px 10px;
        margin-top: 4px;
        margin-left: 26px;
        color: var(--secondary-text-color);
        font-size: 0.85rem;
      }
      .flight-route .flag {
        width: 16px;
        height: 12px;
        vertical-align: middle;
        border-radius: 2px;
        object-fit: cover;
        flex-shrink: 0;
        background: transparent;
        filter: none !important;
        box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.15);
      }
      .route-sep {
        opacity: 0.7;
      }
      .muted { color: var(--secondary-text-color); font-weight: 400; }
      .ac-icon {
        background: transparent;
        border: none;
      }
      .ac-marker {
        width: 28px;
        height: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--primary-color, #03a9f4);
        filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.45));
        transform-origin: center center;
      }
      .ac-marker svg {
        width: 26px;
        height: 26px;
        fill: currentColor;
      }
      .leaflet-popup-content {
        margin: 8px 10px;
        font-size: 0.85rem;
        line-height: 1.35;
        min-width: 160px;
        max-height: 200px;
        overflow-y: auto;
      }
      .popup-photo {
        display: block;
        width: 100%;
        max-width: 200px;
        max-height: 110px;
        height: auto;
        border-radius: 6px;
        margin-bottom: 8px;
        object-fit: cover;
      }
    `;
  }

  _renderShell() {
    if (!this.shadowRoot || !this._config) {
      return;
    }
    // Healthy: DOM + Leaflet instance both present.
    if (this.shadowRoot.getElementById("map") && this._map) {
      return;
    }
    // Rebuild after refresh / partial teardown.
    this._destroyMap();
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <link rel="stylesheet" href="${LEAFLET_CSS}">
      <ha-card>
        <div class="header">
          <h2 id="title"></h2>
          <div class="count" id="count"></div>
        </div>
        <div class="map-wrap">
          <div id="map"></div>
        </div>
        <div class="warning" id="warning" style="display:none;"></div>
        <div class="flights" id="flights"></div>
      </ha-card>
    `;
  }

  async _ensureMap() {
    const mapEl = this.shadowRoot?.getElementById("map");
    if (!mapEl) {
      return null;
    }
    if (this._map) {
      return this._map;
    }
    // Serialize concurrent inits (hass + connectedCallback on refresh).
    if (this._mapInitPromise) {
      return this._mapInitPromise;
    }
    this._mapInitPromise = this._initMap(mapEl);
    try {
      return await this._mapInitPromise;
    } finally {
      this._mapInitPromise = null;
    }
  }

  async _initMap(mapEl) {
    const L = await loadLeaflet();
    if (this._map) {
      return this._map;
    }
    // DOM may have been rebuilt while we awaited Leaflet.
    const currentEl = this.shadowRoot?.getElementById("map");
    if (!this.isConnected || !currentEl) {
      return null;
    }
    mapEl = currentEl;
    // Element may still carry Leaflet state after a partial teardown.
    if (mapEl._leaflet_id) {
      delete mapEl._leaflet_id;
      mapEl.innerHTML = "";
    }
    this._map = L.map(mapEl, {
      zoomControl: true,
      attributionControl: false,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
      touchZoom: false,
    });
    L.control
      .attribution({
        prefix: false,
        position: "bottomright",
      })
      .addTo(this._map);
    // OSM tile usage: https://wiki.openstreetmap.org/wiki/Referer
    // HA often sets Referrer-Policy: no-referrer/same-origin, which OSM rejects.
    // Leaflet < May 2026 needs an explicit tile referrerPolicy.
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      referrerPolicy: "strict-origin-when-cross-origin",
    }).addTo(this._map);
    this._markers = L.layerGroup().addTo(this._map);
    this._tracks = L.layerGroup().addTo(this._map);
    this._markerById = new Map();
    // Leaflet needs a tick after being inserted into shadow DOM.
    requestAnimationFrame(() => this._map?.invalidateSize());
    return this._map;
  }

  _planeIcon(L, heading) {
    const rotation =
      heading == null || Number.isNaN(Number(heading)) ? 0 : Number(heading);
    return L.divIcon({
      className: "ac-icon",
      iconSize: [28, 28],
      iconAnchor: [14, 14],
      html: `
        <div class="ac-marker" style="transform: rotate(${rotation}deg)">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
          </svg>
        </div>
      `,
    });
  }

  _flightId(flight) {
    return flight?.id || this._flightLabel(flight);
  }

  _normalizeTrack(coordinates) {
    if (!Array.isArray(coordinates)) {
      return [];
    }
    return coordinates
      .filter((point) => Array.isArray(point) && point.length >= 2)
      .map((point) => [Number(point[0]), Number(point[1])])
      .filter(
        (point) => !Number.isNaN(point[0]) && !Number.isNaN(point[1])
      );
  }

  _clearTracks() {
    if (this._tracks) {
      this._tracks.clearLayers();
    }
  }

  _drawTracks(L, flights) {
    this._clearTracks();
    if (!this._tracks) {
      return;
    }

    const showAll = this._config.show_tracks !== false;
    const selectedId = this._selectedFlightId;
    let selectedPolyline = null;

    for (const flight of flights) {
      const track = this._normalizeTrack(flight?.coordinates);
      if (track.length < 2) {
        continue;
      }
      const flightId = this._flightId(flight);
      const selected = selectedId != null && flightId === selectedId;
      if (!showAll && !selected) {
        continue;
      }
      const polyline = L.polyline(track, {
        color: selected ? "#e53935" : "#ff9800",
        weight: selected ? 5 : 3,
        opacity: selected ? 1 : 0.85,
        lineJoin: "round",
        lineCap: "round",
      }).addTo(this._tracks);
      if (selected) {
        selectedPolyline = polyline;
      }
    }

    // Keep the highlighted route above the others.
    if (selectedPolyline) {
      selectedPolyline.bringToFront();
    }
  }

  _popupHtml(flight) {
    const number = this._flightLabel(flight);
    const route = [flight.airport_origin_city, flight.airport_destination_city]
      .filter(Boolean)
      .join(" → ");
    const trackPoints = this._normalizeTrack(flight.coordinates).length;
    const photo =
      flight.aircraft_photo_medium ||
      flight.aircraft_photo_large ||
      flight.aircraft_photo_small;
    const photoHtml = photo
      ? `<img class="popup-photo" src="${this._escape(photo)}" alt="${this._escape(number)}" loading="lazy" />`
      : "";
    const altitude = this._formatAltitude(flight.altitude);
    const speed = this._formatSpeed(flight.ground_speed);
    const distance = this._formatDistance(flight.distance);
    const closest = this._formatDistance(flight.closest_distance);
    const lines = [
      photoHtml,
      `<strong>${this._escape(number)}</strong>`,
      flight.airline_short || flight.airline
        ? this._escape(flight.airline_short || flight.airline)
        : "",
      route ? this._escape(route) : "",
      altitude ? this._escape(altitude) : "",
      speed ? this._escape(speed) : "",
      distance ? `Dist ${this._escape(distance)}` : "",
      closest ? `Closest ${this._escape(closest)}` : "",
      flight.aircraft_model ? this._escape(flight.aircraft_model) : "",
      trackPoints
        ? `Track: ${trackPoints} point${trackPoints === 1 ? "" : "s"}`
        : "Track: no history yet",
    ].filter(Boolean);
    return lines.join("<br>");
  }

  _unlockMapForPopup(map) {
    if (!map || this._maxBoundsSuspended) {
      return;
    }
    this._maxBoundsSuspended = true;
    map.setMaxBounds(null);
  }

  _lockMapToArea(map, { animate = false } = {}) {
    if (!map) {
      return;
    }
    this._maxBoundsSuspended = false;
    if (this._areaBounds) {
      map.fitBounds(this._areaBounds, { padding: [0, 0], animate });
    }
    if (this._areaMaxBounds) {
      map.setMaxBounds(this._areaMaxBounds);
      map.options.maxBoundsViscosity = 1.0;
    }
  }

  _keepPopupInView(map, marker, popup) {
    if (!map || !popup || !marker) {
      return;
    }
    const adjust = () => {
      if (!popup.isOpen()) {
        return;
      }
      // Must unlock before pan, otherwise maxBounds eats the adjustment.
      this._unlockMapForPopup(map);
      popup.update();

      // Prefer Leaflet's own auto-pan math (correct pixel signs).
      if (typeof popup._adjustPan === "function") {
        const prev = popup.options.autoPan;
        popup.options.autoPan = true;
        popup.options.autoPanPadding = [12, 12];
        popup._adjustPan();
        popup.options.autoPan = prev;
        return;
      }

      // Fallback: same sign convention as Leaflet Popup._adjustPan.
      const el = popup.getElement();
      if (!el) {
        return;
      }
      const size = map.getSize();
      const tip = map.latLngToContainerPoint(marker.getLatLng());
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      const tipH = 12;
      const left = tip.x - w / 2;
      const right = tip.x + w / 2;
      const top = tip.y - h - tipH;
      const bottom = tip.y;
      const pad = 12;
      let dx = 0;
      let dy = 0;
      if (right > size.x - pad) {
        dx = right - (size.x - pad);
      }
      if (left + dx < pad) {
        dx = left - pad;
      }
      if (bottom > size.y - pad) {
        dy = bottom - (size.y - pad);
      }
      if (top + dy < pad) {
        dy = top - pad;
      }
      if (dx !== 0 || dy !== 0) {
        map.panBy([dx, dy], { animate: false });
      }
    };

    // One layout pass after open — avoid repeated pans on sensor ticks.
    requestAnimationFrame(() => requestAnimationFrame(adjust));
    const img = popup.getElement()?.querySelector("img");
    if (img && !img.complete) {
      img.addEventListener("load", adjust, { once: true });
    }
  }

  async _syncMap(parsed, flights) {
    const L = await loadLeaflet();
    const map = await this._ensureMap();
    if (!map || !this._markers) {
      return;
    }

    const mapWrap = this.shadowRoot?.querySelector(".map-wrap");
    const areaBounds = L.latLngBounds(
      [parsed.south, parsed.west],
      [parsed.north, parsed.east]
    );

    const boundsKey = `${parsed.south},${parsed.west},${parsed.north},${parsed.east}`;
    if (boundsKey !== this._lastBoundsKey) {
      this._lastBoundsKey = boundsKey;

      // Match map viewport aspect ratio to the geographic bounds so fitBounds
      // can pin the zone flush to all four edges (no letterboxing).
      if (mapWrap) {
        const latSpan = Math.max(Math.abs(parsed.north - parsed.south), 1e-6);
        const lonSpan = Math.max(Math.abs(parsed.east - parsed.west), 1e-6);
        const widthFactor = lonSpan * Math.cos((parsed.lat * Math.PI) / 180);
        mapWrap.style.aspectRatio = `${widthFactor} / ${latSpan}`;
      }

      if (this._areaRect) {
        map.removeLayer(this._areaRect);
      }
      this._areaRect = L.rectangle(areaBounds, {
        color: "#03a9f4",
        weight: 2,
        fillOpacity: 0.06,
      }).addTo(map);

      this._areaBounds = areaBounds;
      this._areaMaxBounds = areaBounds.pad(0.02);
      if (!this._openPopupFlightId) {
        map.setMaxBounds(this._areaMaxBounds);
        map.options.maxBoundsViscosity = 1.0;
      }

      // Size must be correct before fitting, otherwise zoom is wrong.
      // Never refit while a popup is open — that causes a visible jump.
      map.invalidateSize();
      if (!this._openPopupFlightId) {
        map.fitBounds(areaBounds, { padding: [0, 0], animate: false });
        requestAnimationFrame(() => {
          map.invalidateSize();
          if (!this._openPopupFlightId) {
            map.fitBounds(areaBounds, { padding: [0, 0], animate: false });
          }
        });
      }
    }

    const positioned = flights.filter(
      (flight) =>
        flight &&
        flight.latitude != null &&
        flight.longitude != null &&
        !Number.isNaN(Number(flight.latitude)) &&
        !Number.isNaN(Number(flight.longitude))
    );
    this._positionedFlights = positioned;

    const flightsKey = [
      this._config.show_tracks !== false ? "tracks:1" : "tracks:0",
      `selected:${this._selectedFlightId || ""}`,
      ...positioned.map((flight) => {
        const trackLen = Array.isArray(flight.coordinates)
          ? flight.coordinates.length
          : 0;
        return `${this._flightId(flight)}:${flight.latitude}:${flight.longitude}:${flight.heading ?? ""}:${trackLen}`;
      }),
    ].join("|");
    if (flightsKey === this._lastFlightsKey) {
      return;
    }
    this._lastFlightsKey = flightsKey;

    if (this._selectedFlightId) {
      const stillThere = positioned.some(
        (flight) => this._flightId(flight) === this._selectedFlightId
      );
      if (!stillThere) {
        this._selectedFlightId = null;
      }
    }

    if (this._openPopupFlightId) {
      const stillOpen = positioned.some(
        (flight) => this._flightId(flight) === this._openPopupFlightId
      );
      if (!stillOpen) {
        this._openPopupFlightId = null;
        this._lockMapToArea(map, { animate: true });
      }
    }

    if (!this._markerById) {
      this._markerById = new Map();
    }

    const nextIds = new Set(positioned.map((flight) => this._flightId(flight)));
    for (const [flightId, marker] of [...this._markerById.entries()]) {
      if (!nextIds.has(flightId)) {
        this._rebuildingMarkers = true;
        this._markers.removeLayer(marker);
        this._rebuildingMarkers = false;
        this._markerById.delete(flightId);
      }
    }

    for (const flight of positioned) {
      const flightId = this._flightId(flight);
      const latLng = [Number(flight.latitude), Number(flight.longitude)];
      const popupHtml = this._popupHtml(flight);
      let marker = this._markerById.get(flightId);

      if (!marker) {
        marker = L.marker(latLng, {
          icon: this._planeIcon(L, flight.heading),
          title: this._flightLabel(flight),
        });
        marker.bindPopup(popupHtml, {
          autoPan: false,
          maxWidth: 260,
          maxHeight: 220,
          closeButton: true,
          closeOnClick: true,
        });
        marker.on("popupopen", (event) => {
          this._openPopupFlightId = flightId;
          // Unlock immediately so Leaflet auto-pan is not clamped.
          this._unlockMapForPopup(map);
          this._keepPopupInView(map, marker, event.popup);
        });
        marker.on("popupclose", () => {
          if (this._rebuildingMarkers) {
            return;
          }
          if (this._openPopupFlightId === flightId) {
            this._openPopupFlightId = null;
          }
          this._lockMapToArea(map, { animate: true });
        });
        marker.on("click", (event) => {
          L.DomEvent.stopPropagation(event);
          this._selectedFlightId = flightId;
          this._lastFlightsKey = null;
          this._drawTracks(L, this._positionedFlights || positioned);
        });
        marker._frHeading = String(flight.heading ?? "");
        marker._frPopupHtml = popupHtml;
        this._markers.addLayer(marker);
        this._markerById.set(flightId, marker);
      } else {
        marker.setLatLng(latLng);
        const headingKey = String(flight.heading ?? "");
        if (marker._frHeading !== headingKey) {
          marker._frHeading = headingKey;
          marker.setIcon(this._planeIcon(L, flight.heading));
        }
        // Update content without tearing down an open popup.
        if (marker._frPopupHtml !== popupHtml) {
          marker._frPopupHtml = popupHtml;
          const popup = marker.getPopup();
          if (popup) {
            popup.setContent(popupHtml);
          }
        }
        // Do not re-pan on every sensor tick — that fights the open popup view.
      }
    }

    this._drawTracks(L, positioned);
  }

  async _update() {
    this._renderShell();
    if (!this.shadowRoot || !this._config || !this._hass) {
      return;
    }

    const titleEl = this.shadowRoot.getElementById("title");
    const countEl = this.shadowRoot.getElementById("count");
    const warningEl = this.shadowRoot.getElementById("warning");
    const flightsEl = this.shadowRoot.getElementById("flights");
    const mapWrap = this.shadowRoot.querySelector(".map-wrap");

    const state = this._hass.states[this._config.entity];
    if (this._lastEntity !== this._config.entity) {
      this._lastEntity = this._config.entity;
      this._lastBoundsKey = null;
      this._lastFlightsKey = null;
      this._openPopupFlightId = null;
      this._selectedFlightId = null;
      this._markerById = new Map();
      if (this._markers) {
        this._rebuildingMarkers = true;
        this._markers.clearLayers();
        this._rebuildingMarkers = false;
      }
    }
    if (!state) {
      if (mapWrap) mapWrap.style.display = "none";
      if (flightsEl) flightsEl.style.display = "none";
      if (warningEl) {
        warningEl.style.display = "block";
        warningEl.textContent = `Entity not found: ${this._config.entity}`;
      }
      if (titleEl) titleEl.textContent = "Flightradar24";
      if (countEl) countEl.textContent = "";
      return;
    }

    const name =
      this._config.title ||
      state.attributes.friendly_name ||
      this._config.entity;
    if (titleEl) titleEl.textContent = name;
    if (countEl) countEl.textContent = `${state.state} in area`;

    const bounds = state.attributes.bounds;
    const parsed = this._parseBounds(bounds);
    const flights = Array.isArray(state.attributes.flights)
      ? state.attributes.flights
      : [];

    if (!parsed) {
      if (mapWrap) mapWrap.style.display = "none";
      if (warningEl) {
        warningEl.style.display = "block";
        warningEl.textContent =
          "No valid bounds attribute on this entity yet.";
      }
    } else {
      if (mapWrap) mapWrap.style.display = "block";
      if (warningEl) warningEl.style.display = "none";
      try {
        await this._syncMap(parsed, flights);
      } catch (error) {
        if (warningEl) {
          warningEl.style.display = "block";
          warningEl.textContent = `Map failed to load: ${error}`;
        }
      }
    }

    if (flightsEl) {
      if (this._config.show_flights === false) {
        flightsEl.style.display = "none";
        flightsEl.innerHTML = "";
      } else {
        flightsEl.style.display = "flex";
        flightsEl.innerHTML = flights.length
          ? flights.map((flight) => this._flightRow(flight)).join("")
          : `<div class="empty">No flights in area</div>`;
      }
    }
  }
}

class Flightradar24CardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    // Keep picker in sync without rebuilding the whole form on every hass tick.
    const picker = this.shadowRoot?.querySelector("ha-entity-picker");
    if (picker) {
      picker.hass = hass;
    } else {
      this._render();
    }
  }

  _fireConfigChanged(newConfig) {
    this._config = newConfig;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: newConfig },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    if (!this._config) {
      return;
    }
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }

    this.shadowRoot.innerHTML = `
      <style>
        .row { display: block; padding: 8px 0; }
        label { display: block; font-size: 0.85rem; color: var(--secondary-text-color); margin-bottom: 4px; }
        input {
          width: 100%;
          box-sizing: border-box;
          padding: 8px;
          border-radius: 4px;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        .check { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
        .check input { width: auto; }
        ha-entity-picker { display: block; width: 100%; }
      </style>
      <div class="row">
        <label>Entity</label>
        <div id="entity-picker"></div>
      </div>
      <div class="row">
        <label>Title (optional)</label>
        <input type="text" id="title" value="${this._escape(this._config.title || "")}" />
      </div>
      <div class="row check">
        <input type="checkbox" id="show_flights" ${this._config.show_flights !== false ? "checked" : ""} />
        <span>Show flights list</span>
      </div>
      <div class="row check">
        <input type="checkbox" id="show_tracks" ${this._config.show_tracks !== false ? "checked" : ""} />
        <span>Show flight tracks</span>
      </div>
    `;

    const mount = this.shadowRoot.getElementById("entity-picker");
    const picker = document.createElement("ha-entity-picker");
    picker.hass = this._hass;
    picker.value = this._config.entity || "";
    picker.label = "Sensor";
    picker.allowCustomEntity = true;
    // Prefer sensors; still allow typing any entity id.
    picker.includeDomains = ["sensor"];
    picker.addEventListener("value-changed", (event) => {
      const value = event.detail?.value || "";
      this._fireConfigChanged({
        ...this._config,
        entity: value,
      });
    });
    mount.appendChild(picker);

    this.shadowRoot.getElementById("title").addEventListener("input", (event) => {
      const newConfig = { ...this._config };
      if (event.target.value) {
        newConfig.title = event.target.value;
      } else {
        delete newConfig.title;
      }
      this._fireConfigChanged(newConfig);
    });

    this.shadowRoot.getElementById("show_flights").addEventListener("change", (event) => {
      this._fireConfigChanged({
        ...this._config,
        show_flights: event.target.checked,
      });
    });

    this.shadowRoot.getElementById("show_tracks").addEventListener("change", (event) => {
      this._fireConfigChanged({
        ...this._config,
        show_tracks: event.target.checked,
      });
    });
  }

  _escape(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;");
  }
}

customElements.define("flightradar24-card", Flightradar24Card);
customElements.define("flightradar24-card-editor", Flightradar24CardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "flightradar24-card",
  name: "Flightradar24 Card",
  description:
    "OpenStreetMap of the monitored area with aircraft markers from sensor flights",
  preview: true,
  documentationURL:
    "https://github.com/AlexandrErohin/home-assistant-flightradar24",
});
