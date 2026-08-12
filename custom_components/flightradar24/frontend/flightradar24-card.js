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
      show_area_center: true,
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
    this._areaCenterMarker = null;
    this._areaCenterMarkerPos = null;
    this._markerById = new Map();
    this._selectedFlightId = null;
    this._openPopupFlightId = null;
    this._rebuildingMarkers = false;
    this._areaBounds = null;
    this._areaMaxBounds = null;
    this._maxBoundsSuspended = false;
    this._lastBoundsKey = null;
    this._lastViewportKey = null;
    this._lastFlightsKey = null;
    this._lastEntity = null;
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Please define an entity");
    }
    const prev = this._config;
    const next = {
      show_flights: true,
      show_tracks: true,
      show_area_center: true,
      ...config,
    };
    if (next.zoom != null && next.zoom !== "") {
      const zoom = Number(next.zoom);
      if (Number.isNaN(zoom)) {
        delete next.zoom;
      } else {
        next.zoom = Math.min(19, Math.max(1, Math.round(zoom)));
      }
    } else {
      delete next.zoom;
    }
    if (next.icon_size != null && next.icon_size !== "") {
      const iconSize = Number(next.icon_size);
      if (Number.isNaN(iconSize)) {
        delete next.icon_size;
      } else {
        next.icon_size = Math.min(64, Math.max(12, Math.round(iconSize)));
      }
    } else {
      delete next.icon_size;
    }
    this._config = next;
    if (prev && prev.entity !== this._config.entity) {
      this._lastBoundsKey = null;
      this._lastViewportKey = null;
      this._lastFlightsKey = null;
      this._lastEntity = null;
      this._openPopupFlightId = null;
      this._selectedFlightId = null;
      this._markerById = new Map();
      this._removeAreaCenterMarker();
    } else if (prev && prev.show_tracks !== this._config.show_tracks) {
      // Force marker/track redraw when the option changes.
      this._lastFlightsKey = null;
    } else if (prev && prev.zoom !== this._config.zoom) {
      this._lastViewportKey = null;
    } else if (prev && prev.icon_size !== this._config.icon_size) {
      this._lastFlightsKey = null;
    }
    this._renderShell();
    if (
      prev &&
      (prev.show_area_center !== this._config.show_area_center ||
        prev.show_tracks !== this._config.show_tracks ||
        prev.zoom !== this._config.zoom ||
        prev.icon_size !== this._config.icon_size)
    ) {
      this._update();
    }
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
    this._areaCenterMarker = null;
    this._areaCenterMarkerPos = null;
    this._markerById = new Map();
    this._selectedFlightId = null;
    this._openPopupFlightId = null;
    this._rebuildingMarkers = false;
    this._areaBounds = null;
    this._areaMaxBounds = null;
    this._maxBoundsSuspended = false;
    this._lastBoundsKey = null;
    this._lastViewportKey = null;
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

  _formatTimestamp(value) {
    if (value == null || value === "") {
      return null;
    }
    const seconds = Number(value);
    if (Number.isNaN(seconds) || seconds <= 0) {
      return null;
    }
    const date = new Date(seconds * 1000);
    if (Number.isNaN(date.getTime())) {
      return null;
    }
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${hours}:${minutes}`;
  }

  _flightLegTime(flight, leg) {
    const fields =
      leg === "departure"
        ? [
            "time_real_departure",
            "time_estimated_departure",
            "time_scheduled_departure",
          ]
        : [
            "time_real_arrival",
            "time_estimated_arrival",
            "time_scheduled_arrival",
          ];
    for (const field of fields) {
      const formatted = this._formatTimestamp(flight[field]);
      if (formatted) {
        return formatted;
      }
    }
    return null;
  }

  _flightFr24Url(flight) {
    if (!flight) {
      return null;
    }
    const id =
      flight.id != null && flight.id !== "" ? String(flight.id).trim() : "";
    const slug = String(
      flight.callsign || flight.flight_number || flight.aircraft_registration || ""
    ).trim();
    if (id && slug) {
      return `https://fr24.com/${encodeURIComponent(slug)}/${encodeURIComponent(id)}`;
    }
    if (slug) {
      return `https://www.flightradar24.com/${encodeURIComponent(slug)}`;
    }
    if (id) {
      return `https://www.flightradar24.com/${encodeURIComponent(id)}`;
    }
    return null;
  }

  _flightFr24Link(label, url, className = "flight-link") {
    if (!url) {
      return `<strong>${this._escape(label)}</strong>`;
    }
    return (
      `<a class="${className}" href="${this._escape(url)}" target="_blank" ` +
      `rel="noopener noreferrer" title="Open on Flightradar24" ` +
      `onclick="event.stopPropagation();">${this._escape(label)}</a>`
    );
  }

  _flightFr24IconLink(url) {
    if (!url) {
      return "";
    }
    return (
      `<a class="popup-fr24-link" href="${this._escape(url)}" target="_blank" ` +
      `rel="noopener noreferrer" title="Open on Flightradar24" ` +
      `onclick="event.stopPropagation();" aria-label="Open on Flightradar24">↗</a>`
    );
  }

  _routeEndpoint(city, time, flagHtml) {
    const parts = [];
    if (city) {
      parts.push(this._escape(city));
    }
    if (time) {
      parts.push(this._escape(time));
    }
    if (!parts.length) {
      return "";
    }
    return `${flagHtml}<span>${parts.join(" ")}</span>`;
  }

  _flightRow(flight) {
    const number = this._flightLabel(flight);
    const fr24Url = this._flightFr24Url(flight);
    const aircraft = flight.aircraft_model || flight.aircraft_code || "";
    const airline = flight.airline_short || flight.airline || "";
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
    const depTime = this._flightLegTime(flight, "departure");
    const arrTime = this._flightLegTime(flight, "arrival");
    const origin = this._routeEndpoint(originCity, depTime, originFlag);
    const destination = this._routeEndpoint(destCity, arrTime, destFlag);
    const routeParts = [origin, destination].filter(Boolean);
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

    const mainParts = [
      this._flightFr24Link(number, fr24Url),
      aircraft ? `<span class="flight-type">${this._escape(aircraft)}</span>` : "",
      airline ? `<span class="muted">${this._escape(airline)}</span>` : "",
    ].filter(Boolean);

    return `
      <div class="flight${this._selectedFlightId === this._flightId(flight) ? " selected" : ""}" data-flight-id="${this._escape(this._flightId(flight))}">
        <div class="flight-main">
          <ha-icon icon="${this._flightIcon(flight)}"></ha-icon>
          ${mainParts.join("")}
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

  _bindFlightsList(flightsEl) {
    if (!flightsEl || flightsEl._frClickBound) {
      return;
    }
    flightsEl._frClickBound = true;
    flightsEl.addEventListener("click", (event) => {
      if (event.target.closest("a")) {
        return;
      }
      const row = event.target.closest(".flight[data-flight-id]");
      if (!row) {
        return;
      }
      const flightId = row.dataset.flightId;
      if (!flightId) {
        return;
      }
      this._selectFlight(flightId, { openPopup: true });
    });
  }

  async _selectFlight(flightId, { scrollList = false, openPopup = false } = {}) {
    this._selectedFlightId = flightId;
    this._renderFlightsList(this._positionedFlights || [], {
      scrollToSelected: scrollList,
    });

    if (!this._map) {
      return;
    }
    const L = await loadLeaflet();
    this._drawTracks(L, this._positionedFlights || []);

    if (!openPopup) {
      return;
    }
    const marker = this._markerById?.get(flightId);
    if (!marker) {
      return;
    }
    this._unlockMapForPopup(this._map);
    marker.openPopup();
    const popup = marker.getPopup();
    if (popup) {
      this._keepPopupInView(this._map, marker, popup);
    }
  }

  _renderFlightsList(flights, { scrollToSelected = false } = {}) {
    const flightsEl = this.shadowRoot?.getElementById("flights");
    if (!flightsEl || this._config?.show_flights === false) {
      return;
    }
    this._bindFlightsList(flightsEl);
    flightsEl.style.display = "flex";
    flightsEl.innerHTML = flights.length
      ? flights.map((flight) => this._flightRow(flight)).join("")
      : `<div class="empty">No flights in area</div>`;

    if (!scrollToSelected || !this._selectedFlightId) {
      return;
    }
    for (const row of flightsEl.querySelectorAll(".flight")) {
      if (row.dataset.flightId === this._selectedFlightId) {
        row.scrollIntoView({ block: "nearest", behavior: "smooth" });
        break;
      }
    }
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
        padding: 8px 8px 0;
        margin: 0 -8px;
        cursor: pointer;
      }
      .flight.selected {
        background: color-mix(in srgb, var(--primary-color, #03a9f4) 14%, transparent);
        border-radius: 8px;
        box-shadow: inset 0 0 0 2px var(--primary-color, #03a9f4);
      }
      .flight.selected + .flight {
        border-top-color: transparent;
      }
      .flight-main {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
        color: var(--primary-text-color);
      }
      .flight-main ha-icon {
        --mdc-icon-size: 18px;
        color: var(--state-icon-color, var(--primary-color));
        flex-shrink: 0;
      }
      .flight-main .flight-type {
        color: var(--secondary-text-color);
      }
      .flight-link {
        font-weight: 600;
        color: var(--primary-color, #03a9f4);
        text-decoration: none;
      }
      .flight-link:hover {
        text-decoration: underline;
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
      .area-center-icon {
        background: transparent;
        border: none;
      }
      .area-center-marker {
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--accent-color, #ff5722);
        filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.45));
      }
      .area-center-marker svg {
        width: 22px;
        height: 22px;
        fill: currentColor;
      }
      .leaflet-popup-content-wrapper {
        width: 200px;
        min-width: 200px;
        max-width: 200px;
        padding: 0;
        overflow: hidden;
        box-sizing: border-box;
      }
      .leaflet-container .leaflet-popup-content {
        margin: 0 !important;
        padding: 6px 8px !important;
        font-size: 0.8rem;
        line-height: 1.2;
        width: 200px !important;
        max-width: 200px !important;
        min-height: 0;
        box-sizing: border-box;
        overflow: hidden;
        text-align: left;
      }
      .leaflet-popup-content .popup-photo,
      .popup-photo {
        display: block;
        width: 100%;
        max-width: 100%;
        max-height: 110px;
        height: auto;
        border-radius: 6px;
        margin: 0 0 6px;
        object-fit: cover;
        box-sizing: border-box;
      }
      .fr-popup {
        color: var(--primary-text-color, #212121);
        width: 100%;
        max-width: 100%;
        overflow: hidden;
        box-sizing: border-box;
      }
      .popup-body {
        width: 100%;
        max-width: 100%;
        box-sizing: border-box;
      }
      .popup-title {
        display: flex;
        align-items: center;
        gap: 6px;
        font-weight: 600;
        font-size: 0.85rem;
        line-height: 1.2;
      }
      .popup-fr24-link {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 18px;
        height: 18px;
        flex-shrink: 0;
        color: var(--primary-color, #03a9f4);
        text-decoration: none;
        font-size: 0.85rem;
        line-height: 1;
      }
      .popup-fr24-link:hover {
        text-decoration: none;
        opacity: 0.8;
      }
      .popup-line {
        margin-top: 2px;
        line-height: 1.2;
      }
      .popup-meta,
      .popup-route,
      .popup-stats {
        color: var(--secondary-text-color, #666);
        font-size: 0.75rem;
      }
      .popup-stats span + span::before {
        content: "·";
        margin: 0 5px;
        opacity: 0.55;
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
      scrollWheelZoom: true,
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
    const size = this._configuredIconSize();
    const svgSize = Math.max(8, size - 2);
    const anchor = size / 2;
    return L.divIcon({
      className: "ac-icon",
      iconSize: [size, size],
      iconAnchor: [anchor, anchor],
      html: `
        <div class="ac-marker" style="width:${size}px;height:${size}px;transform: rotate(${rotation}deg)">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" style="width:${svgSize}px;height:${svgSize}px">
            <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
          </svg>
        </div>
      `,
    });
  }

  _removeAreaCenterMarker(map = this._map) {
    if (this._areaCenterMarker && map) {
      map.removeLayer(this._areaCenterMarker);
    }
    this._areaCenterMarker = null;
    this._areaCenterMarkerPos = null;
  }

  _areaCenterIcon(L) {
    return L.divIcon({
      className: "area-center-icon",
      iconSize: [24, 24],
      iconAnchor: [12, 12],
      html: `
        <div class="area-center-marker">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/>
          </svg>
        </div>
      `,
    });
  }

  /**
   * Marker at the centre of the observed area - the latitude/longitude this
   * device is configured with. Deliberately not zone.home: with several
   * Flightradar24 devices watching different points, only the bounds centre
   * is correct for the device this card is showing.
   */
  _syncAreaCenterMarker(L, map, parsed) {
    if (this._config.show_area_center === false) {
      this._removeAreaCenterMarker(map);
      return;
    }
    // parsed is non-null and numeric here: _parseBounds rejects both, and
    // _syncMap is not reached otherwise.
    const posKey = `${parsed.lat},${parsed.lon}`;
    if (this._areaCenterMarker) {
      if (posKey !== this._areaCenterMarkerPos) {
        this._areaCenterMarker.setLatLng([parsed.lat, parsed.lon]);
        this._areaCenterMarkerPos = posKey;
      }
      return;
    }
    this._areaCenterMarker = L.marker([parsed.lat, parsed.lon], {
      icon: this._areaCenterIcon(L),
      keyboard: false,
      // Above aircraft: a fixed reference point should stay findable inside
      // a dense cluster of markers.
      zIndexOffset: 1000,
    }).addTo(map);
    this._areaCenterMarkerPos = posKey;
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
    const fr24Url = this._flightFr24Url(flight);
    const aircraft = flight.aircraft_model || flight.aircraft_code || "";
    const airline = flight.airline_short || flight.airline || "";
    const origin =
      flight.airport_origin_city || flight.airport_origin_code_iata || "";
    const dest =
      flight.airport_destination_city ||
      flight.airport_destination_code_iata ||
      "";
    const route = [origin, dest].filter(Boolean).join(" → ");
    const headMeta = [aircraft, airline]
      .filter(Boolean)
      .map((value) => this._escape(value))
      .join(" · ");
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
    const motionStats = [
      altitude ? this._escape(altitude) : "",
      speed ? this._escape(speed) : "",
    ].filter(Boolean);
    const distanceStats = [
      distance ? `Dist ${this._escape(distance)}` : "",
      closest ? `Min ${this._escape(closest)}` : "",
    ].filter(Boolean);
    const statsLine = (items) =>
      items.map((item) => `<span>${item}</span>`).join("");

    return `
      <div class="fr-popup">
        ${photoHtml}
        <div class="popup-body">
          <div class="popup-title">
            <span>${this._escape(number)}</span>
            ${this._flightFr24IconLink(fr24Url)}
          </div>
          ${headMeta ? `<div class="popup-line popup-meta">${headMeta}</div>` : ""}
          ${route ? `<div class="popup-line popup-route">${this._escape(route)}</div>` : ""}
          ${
            motionStats.length
              ? `<div class="popup-line popup-stats">${statsLine(motionStats)}</div>`
              : ""
          }
          ${
            distanceStats.length
              ? `<div class="popup-line popup-stats">${statsLine(distanceStats)}</div>`
              : ""
          }
        </div>
      </div>
    `;
  }

  _unlockMapForPopup(map) {
    if (!map || this._maxBoundsSuspended) {
      return;
    }
    this._maxBoundsSuspended = true;
    map.setMaxBounds(null);
  }

  _configuredZoom() {
    const zoom = this._config?.zoom;
    if (zoom == null || zoom === "") {
      return null;
    }
    const value = Number(zoom);
    if (Number.isNaN(value)) {
      return null;
    }
    return Math.min(19, Math.max(1, Math.round(value)));
  }

  _configuredIconSize() {
    const iconSize = this._config?.icon_size;
    if (iconSize == null || iconSize === "") {
      return 28;
    }
    const value = Number(iconSize);
    if (Number.isNaN(value)) {
      return 28;
    }
    return Math.min(64, Math.max(12, Math.round(value)));
  }

  _applyAreaViewport(map, parsed, areaBounds, { animate = false } = {}) {
    if (!map || this._openPopupFlightId) {
      return;
    }
    map.invalidateSize();
    const zoom = this._configuredZoom();
    if (zoom != null) {
      map.setView([parsed.lat, parsed.lon], zoom, { animate });
      return;
    }
    map.fitBounds(areaBounds, { padding: [0, 0], animate });
  }

  _lockMapToArea(map, { animate = false } = {}) {
    if (!map) {
      return;
    }
    this._maxBoundsSuspended = false;
    if (this._areaBounds) {
      const zoom = this._configuredZoom();
      if (zoom != null) {
        const center = this._areaBounds.getCenter();
        map.setView(center, zoom, { animate });
      } else {
        map.fitBounds(this._areaBounds, { padding: [0, 0], animate });
      }
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

    this._syncAreaCenterMarker(L, map, parsed);

    const boundsKey = `${parsed.south},${parsed.west},${parsed.north},${parsed.east}`;
    const configuredZoom = this._configuredZoom();
    const viewportKey = `${boundsKey}|zoom:${configuredZoom ?? "auto"}`;
    if (viewportKey !== this._lastViewportKey) {
      this._lastViewportKey = viewportKey;

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
      }

      // Size must be correct before fitting, otherwise zoom is wrong.
      // Never refit while a popup is open — that causes a visible jump.
      this._applyAreaViewport(map, parsed, areaBounds, { animate: false });
      requestAnimationFrame(() => {
        if (viewportKey !== this._lastViewportKey) {
          return;
        }
        this._applyAreaViewport(map, parsed, areaBounds, { animate: false });
      });
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
      `icon:${this._configuredIconSize()}`,
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
          maxWidth: 200,
          maxHeight: 220,
          closeButton: true,
          closeOnClick: true,
        });
        marker.on("popupopen", (event) => {
          this._openPopupFlightId = flightId;
          this._selectedFlightId = flightId;
          this._renderFlightsList(this._positionedFlights || []);
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
          this._selectFlight(flightId, { scrollList: true });
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
      this._lastViewportKey = null;
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
        this._renderFlightsList(flights);
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
      <div class="row check">
        <input type="checkbox" id="show_area_center" ${this._config.show_area_center !== false ? "checked" : ""} />
        <span>Show area centre marker</span>
      </div>
      <div class="row">
        <label>Zoom (optional, 1–19)</label>
        <input
          type="number"
          id="zoom"
          min="1"
          max="19"
          step="1"
          placeholder="Auto"
          value="${this._config.zoom != null ? this._escape(String(this._config.zoom)) : ""}"
        />
      </div>
      <div class="row">
        <label>Aircraft icon size (optional, 12–64 px)</label>
        <input
          type="number"
          id="icon_size"
          min="12"
          max="64"
          step="1"
          placeholder="28"
          value="${this._config.icon_size != null ? this._escape(String(this._config.icon_size)) : ""}"
        />
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

    this.shadowRoot.getElementById("show_area_center").addEventListener("change", (event) => {
      this._fireConfigChanged({
        ...this._config,
        show_area_center: event.target.checked,
      });
    });

    this.shadowRoot.getElementById("zoom").addEventListener("change", (event) => {
      const newConfig = { ...this._config };
      const raw = event.target.value.trim();
      if (raw === "") {
        delete newConfig.zoom;
      } else {
        const zoom = Number(raw);
        if (!Number.isNaN(zoom)) {
          newConfig.zoom = Math.min(19, Math.max(1, Math.round(zoom)));
        }
      }
      this._fireConfigChanged(newConfig);
    });

    this.shadowRoot.getElementById("icon_size").addEventListener("change", (event) => {
      const newConfig = { ...this._config };
      const raw = event.target.value.trim();
      if (raw === "") {
        delete newConfig.icon_size;
      } else {
        const iconSize = Number(raw);
        if (!Number.isNaN(iconSize)) {
          newConfig.icon_size = Math.min(64, Math.max(12, Math.round(iconSize)));
        }
      }
      this._fireConfigChanged(newConfig);
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
    "OpenStreetMap of the monitored area with aircraft markers, optional flight tracks, and an optional area centre marker",
  preview: true,
  documentationURL:
    "https://github.com/AlexandrErohin/home-assistant-flightradar24",
});
