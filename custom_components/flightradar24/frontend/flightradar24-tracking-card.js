/**
 * Flightradar24 Tracking Lovelace card.
 * Follows a live flight from sensor.flightradar24_additional_tracked:
 * selected aircraft stays map-centred (north up), list below marks live vs scheduled.
 */
const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

const MAP_STYLES = {
  osm: {
    label: "OpenStreetMap",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution:
      '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
  satellite: {
    label: "Satellite (Esri)",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution:
      "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    maxZoom: 19,
  },
  topo: {
    label: "Topographic",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution:
      'Map data: © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: © <a href="https://opentopomap.org">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)',
    maxZoom: 17,
    subdomains: "abc",
  },
};
const DEFAULT_MAP_STYLE = "osm";
const DEFAULT_ZOOM = 6;
const DEFAULT_VIEW = [20, 0];

/** Follow HA theme (auto), or force light/dark basemap treatment. */
const THEME_MODES = {
  auto: "Auto (follow Home Assistant)",
  light: "Light",
  dark: "Dark",
};
const DEFAULT_THEME_MODE = "auto";
/** Raster styles that look wrong on dark dashboards; satellite is left as-is. */
const DARK_FILTER_STYLES = new Set(["osm", "topo"]);

/** Coast slower than reported GS so the next fix is usually ahead (no reverse jump). */
const COAST_SPEED_FACTOR = 0.75;
/** Catch-up runs faster than reported GS to close the lag after a fix. */
const CATCHUP_SPEED_FACTOR = 1.35;
const CATCHUP_MIN_DURATION_S = 0.45;
const CATCHUP_MAX_DURATION_S = 2.5;
const CATCHUP_MIN_GAP_M = 20;
/** Ignore fixes that would pull the camera backwards along track. */
const REVERSE_ALONG_TRACK_M = -30;

const DISPLAY_UNITS = {
  altitude_unit: {
    label: "Altitude units",
    default: "both",
    options: { both: "Meters and feet", m: "Meters", ft: "Feet" },
  },
  speed_unit: {
    label: "Speed units",
    default: "both",
    options: { both: "km/h and knots", "km/h": "km/h", mph: "mph", kts: "Knots" },
  },
};
const DEFAULT_DISPLAY_UNITS = Object.fromEntries(
  Object.entries(DISPLAY_UNITS).map(([key, units]) => [key, units.default])
);

const DISPLAY_UNIT_ALIASES = {
  altitude_unit: { meters: "m", metre: "m", metres: "m", feet: "ft", foot: "ft" },
  speed_unit: {
    kmh: "km/h",
    kmph: "km/h",
    kph: "km/h",
    knots: "kts",
    knot: "kts",
    kt: "kts",
  },
};

function resolveDisplayUnit(key, value) {
  const raw = typeof value === "string" ? value.trim().toLowerCase() : "";
  const unit = DISPLAY_UNIT_ALIASES[key]?.[raw] || raw;
  return Object.keys(DISPLAY_UNITS[key].options).includes(unit)
    ? unit
    : DISPLAY_UNITS[key].default;
}

function resolveMapStyle(value) {
  const key = typeof value === "string" ? value.trim().toLowerCase() : "";
  return MAP_STYLES[key] ? key : DEFAULT_MAP_STYLE;
}

function resolveThemeMode(value) {
  const key = typeof value === "string" ? value.trim().toLowerCase() : "";
  return Object.prototype.hasOwnProperty.call(THEME_MODES, key)
    ? key
    : DEFAULT_THEME_MODE;
}

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

class Flightradar24TrackingCard extends HTMLElement {
  static getStubConfig(hass, entities, entitiesFallback) {
    const candidates = [...(entities || []), ...(entitiesFallback || [])];
    const entity =
      candidates.find((entityId) =>
        entityId.includes("flightradar24_additional_tracked")
      ) ||
      candidates.find((entityId) => {
        const state = hass?.states?.[entityId];
        return (
          state &&
          Array.isArray(state.attributes?.flights) &&
          state.attributes.flights.some(
            (flight) => flight?.tracked_type != null || flight?.tracked_by != null
          )
        );
      }) ||
      candidates.find((entityId) => entityId.includes("flightradar24")) ||
      "";
    return {
      entity,
      show_header: true,
      show_flights: true,
      show_route: true,
      smooth_motion: true,
      map_style: DEFAULT_MAP_STYLE,
      theme_mode: DEFAULT_THEME_MODE,
      zoom: DEFAULT_ZOOM,
      ...DEFAULT_DISPLAY_UNITS,
    };
  }

  static getConfigElement() {
    return document.createElement("flightradar24-tracking-card-editor");
  }

  constructor() {
    super();
    this._map = null;
    this._mapInitPromise = null;
    this._resizeObserver = null;
    this._tileLayer = null;
    this._planeMarker = null;
    this._routeLayer = null;
    this._selectedFlightId = null;
    this._userPickedFlight = false;
    this._lastFollowKey = null;
    this._flightRowById = new Map();
    this._flightSnapshotById = new Map();
    this._lastEntity = null;
    this._flightsById = new Map();
    this._motion = null;
    this._motionRaf = null;
    this._motionBound = null;
    /** Bumped on user flight selection so in-flight async syncs cannot overwrite it. */
    this._followEpoch = 0;
    this._lastRouteKey = null;
    this._pendingZoomReset = false;
    this._lastDarkTiles = null;
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Please define an entity");
    }
    const prev = this._config;
    const next = {
      show_header: true,
      show_flights: true,
      show_route: true,
      smooth_motion: true,
      map_style: DEFAULT_MAP_STYLE,
      theme_mode: DEFAULT_THEME_MODE,
      zoom: DEFAULT_ZOOM,
      ...DEFAULT_DISPLAY_UNITS,
      ...config,
    };
    next.map_style = resolveMapStyle(next.map_style);
    next.theme_mode = resolveThemeMode(next.theme_mode);
    for (const key of Object.keys(DISPLAY_UNITS)) {
      next[key] = resolveDisplayUnit(key, next[key]);
    }
    if (next.zoom != null && next.zoom !== "") {
      const zoom = Number(next.zoom);
      if (Number.isNaN(zoom)) {
        next.zoom = DEFAULT_ZOOM;
      } else {
        next.zoom = Math.min(19, Math.max(1, Math.round(zoom)));
      }
    } else {
      next.zoom = DEFAULT_ZOOM;
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
    const unitsChanged =
      prev &&
      Object.keys(DISPLAY_UNITS).some((key) => prev[key] !== next[key]);
    if (prev && prev.entity !== this._config.entity) {
      this._resetSelectionState();
    } else if (
      prev &&
      (prev.show_route !== this._config.show_route ||
        prev.smooth_motion !== this._config.smooth_motion ||
        prev.zoom !== this._config.zoom ||
        prev.icon_size !== this._config.icon_size ||
        prev.map_style !== this._config.map_style ||
        prev.theme_mode !== this._config.theme_mode ||
        unitsChanged)
    ) {
      this._lastFollowKey = null;
      this._lastRouteKey = null;
      if (prev.zoom !== this._config.zoom) {
        this._pendingZoomReset = true;
      }
    }
    this._renderShell();
    if (
      prev &&
      (prev.show_header !== this._config.show_header ||
        prev.show_flights !== this._config.show_flights ||
        prev.show_route !== this._config.show_route ||
        prev.smooth_motion !== this._config.smooth_motion ||
        prev.zoom !== this._config.zoom ||
        prev.icon_size !== this._config.icon_size ||
        prev.map_style !== this._config.map_style ||
        prev.theme_mode !== this._config.theme_mode ||
        unitsChanged)
    ) {
      if (
        prev.map_style !== this._config.map_style ||
        prev.theme_mode !== this._config.theme_mode
      ) {
        this._syncTileLayer();
      }
      this._update();
    }
  }

  set hass(hass) {
    this._hass = hass;
    const darkTiles = this._wantsDarkTiles();
    if (this._map && this._lastDarkTiles !== darkTiles) {
      this._syncTileLayer();
    }
    this._update();
  }

  _isDarkTheme() {
    const mode = resolveThemeMode(this._config?.theme_mode);
    if (mode === "dark") {
      return true;
    }
    if (mode === "light") {
      return false;
    }
    return Boolean(this._hass?.themes?.darkMode);
  }

  _wantsDarkTiles() {
    const styleKey = resolveMapStyle(this._config?.map_style);
    return this._isDarkTheme() && DARK_FILTER_STYLES.has(styleKey);
  }

  _applyMapThemeChrome() {
    const mapEl = this.shadowRoot?.getElementById("map");
    if (mapEl?.classList) {
      mapEl.classList.toggle("map-dark", this._isDarkTheme());
    }
  }

  getCardSize() {
    const header = this._config?.show_header !== false ? 1 : 0;
    const flights = this._config?.show_flights !== false ? 2 : 0;
    return 3 + header + flights;
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

  _resetSelectionState() {
    this._selectedFlightId = null;
    this._userPickedFlight = false;
    this._lastFollowKey = null;
    this._lastRouteKey = null;
    this._followEpoch += 1;
    this._clearFlightRows();
    this._flightsById = new Map();
    this._clearMapOverlays();
  }

  _destroyMap() {
    this._resizeObserver?.disconnect();
    this._resizeObserver = null;
    this._clearMapOverlays();
    if (this._map) {
      try {
        this._map.remove();
      } catch (_error) {
        // ignore — container may already be gone on refresh
      }
      this._map = null;
    }
    this._mapInitPromise = null;
    this._tileLayer = null;
    const mapEl = this.shadowRoot?.getElementById("map");
    if (mapEl) {
      if (mapEl._leaflet_id) {
        delete mapEl._leaflet_id;
      }
      mapEl.innerHTML = "";
    }
    this._lastFollowKey = null;
    this._clearFlightRows();
  }

  _clearMapOverlays() {
    this._stopMotion();
    if (this._planeMarker && this._map) {
      try {
        this._map.removeLayer(this._planeMarker);
      } catch (_error) {
        // ignore
      }
    }
    this._planeMarker = null;
    if (this._routeLayer && this._map) {
      try {
        this._map.removeLayer(this._routeLayer);
      } catch (_error) {
        // ignore
      }
    }
    this._routeLayer = null;
    this._lastRouteKey = null;
  }

  _knotsToMetersPerSecond(knots) {
    return knots * (1852 / 3600);
  }

  _metersPerDeg(lat) {
    const metersPerDegLat = 111320;
    const cosLat = Math.cos((lat * Math.PI) / 180);
    return {
      lat: metersPerDegLat,
      lon: metersPerDegLat * Math.max(Math.abs(cosLat), 1e-6),
    };
  }

  /**
   * Dead-reckon lat/lon for dt seconds using ground speed (knots) and heading
   * (degrees, 0 = north, clockwise).
   */
  _extrapolatePosition(lat, lon, headingDeg, speedKnots, dtSeconds) {
    if (
      !Number.isFinite(lat) ||
      !Number.isFinite(lon) ||
      !Number.isFinite(headingDeg) ||
      !Number.isFinite(speedKnots) ||
      !Number.isFinite(dtSeconds) ||
      speedKnots <= 0 ||
      dtSeconds <= 0
    ) {
      return { lat, lon };
    }
    const meters = this._knotsToMetersPerSecond(speedKnots) * dtSeconds;
    const headingRad = (headingDeg * Math.PI) / 180;
    const northM = meters * Math.cos(headingRad);
    const eastM = meters * Math.sin(headingRad);
    const scale = this._metersPerDeg(lat);
    return {
      lat: lat + northM / scale.lat,
      lon: lon + eastM / scale.lon,
    };
  }

  _offsetMeters(lat, lon, toLat, toLon) {
    const scale = this._metersPerDeg(lat);
    return {
      north: (toLat - lat) * scale.lat,
      east: (toLon - lon) * scale.lon,
    };
  }

  _metersBetween(lat, lon, toLat, toLon) {
    const { north, east } = this._offsetMeters(lat, lon, toLat, toLon);
    return Math.hypot(north, east);
  }

  /** Positive => target is ahead along heading; negative => behind. */
  _alongTrackMeters(lat, lon, toLat, toLon, headingDeg) {
    const { north, east } = this._offsetMeters(lat, lon, toLat, toLon);
    const headingRad = (headingDeg * Math.PI) / 180;
    return north * Math.cos(headingRad) + east * Math.sin(headingRad);
  }

  _easeInOutCubic(t) {
    const x = Math.min(1, Math.max(0, t));
    return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  }

  _stopMotion() {
    if (this._motionRaf != null) {
      cancelAnimationFrame(this._motionRaf);
      this._motionRaf = null;
    }
    this._motion = null;
  }

  _nowMs() {
    if (typeof performance !== "undefined" && typeof performance.now === "function") {
      return performance.now();
    }
    return Date.now();
  }

  _motionKinematicsFromFlight(flight) {
    const heading = Number(flight.heading);
    const speedKnots = Number(flight.ground_speed);
    return {
      flightId: this._flightId(flight),
      heading: Number.isFinite(heading) ? heading : 0,
      speedKnots: Number.isFinite(speedKnots) ? speedKnots : 0,
      onGround: Number(flight.on_ground) === 1 || flight.on_ground === true,
      helicopter: this._isHelicopter(flight),
      label: this._flightLabel(flight),
    };
  }

  /**
   * Seed or refresh motion from a sensor fix.
   * Coast under-speeds between fixes; a new fix starts a catch-up to the reported point.
   */
  _applyFlightMotion(flight, { flightChanged = false } = {}) {
    const targetLat = Number(flight.latitude);
    const targetLon = Number(flight.longitude);
    const kinematics = this._motionKinematicsFromFlight(flight);
    const now = this._nowMs();

    if (
      !this._motion ||
      flightChanged ||
      this._motion.flightId !== kinematics.flightId
    ) {
      this._motion = {
        ...kinematics,
        lat: targetLat,
        lon: targetLon,
        phase: "coast",
        catchFromLat: targetLat,
        catchFromLon: targetLon,
        catchToLat: targetLat,
        catchToLon: targetLon,
        catchStartTs: now,
        catchDurationS: 0,
        lastTs: now,
      };
      return;
    }

    const motion = this._motion;
    Object.assign(motion, kinematics);
    motion.lastTs = now;

    if (motion.onGround || this._config?.smooth_motion === false) {
      motion.lat = targetLat;
      motion.lon = targetLon;
      motion.phase = "coast";
      return;
    }

    const gapM = this._metersBetween(motion.lat, motion.lon, targetLat, targetLon);
    const alongM = this._alongTrackMeters(
      motion.lat,
      motion.lon,
      targetLat,
      targetLon,
      motion.heading
    );

    // Coast is intentionally slow; a fix behind the camera must not yank the map back.
    if (alongM < REVERSE_ALONG_TRACK_M) {
      motion.phase = "coast";
      return;
    }

    if (gapM < CATCHUP_MIN_GAP_M) {
      motion.lat = targetLat;
      motion.lon = targetLon;
      motion.phase = "coast";
      return;
    }

    const catchSpeedMps = Math.max(
      this._knotsToMetersPerSecond(motion.speedKnots) * CATCHUP_SPEED_FACTOR,
      30
    );
    const durationS = Math.min(
      CATCHUP_MAX_DURATION_S,
      Math.max(CATCHUP_MIN_DURATION_S, gapM / catchSpeedMps)
    );

    motion.phase = "catchup";
    motion.catchFromLat = motion.lat;
    motion.catchFromLon = motion.lon;
    motion.catchToLat = targetLat;
    motion.catchToLon = targetLon;
    motion.catchStartTs = now;
    motion.catchDurationS = durationS;
  }

  _ensureMotionLoop() {
    if (this._config?.smooth_motion === false || this._motionRaf != null) {
      return;
    }
    if (!this._motionBound) {
      this._motionBound = (timestamp) => this._motionTick(timestamp);
    }
    this._motionRaf = requestAnimationFrame(this._motionBound);
  }

  _motionTick(timestamp) {
    this._motionRaf = null;
    const motion = this._motion;
    if (!motion || !this._map || !this._planeMarker || !this.isConnected) {
      return;
    }

    if (this._config?.smooth_motion !== false && !motion.onGround) {
      const now = Number.isFinite(timestamp) ? timestamp : this._nowMs();
      // Cap so a background tab does not jump kilometers on resume.
      const dt = Math.min(1, Math.max(0, (now - motion.lastTs) / 1000));
      motion.lastTs = now;
      if (dt > 0) {
        if (motion.phase === "catchup") {
          const elapsedS = Math.max(0, (now - motion.catchStartTs) / 1000);
          const duration = Math.max(motion.catchDurationS || CATCHUP_MIN_DURATION_S, 1e-3);
          const t = this._easeInOutCubic(elapsedS / duration);
          motion.lat =
            motion.catchFromLat + (motion.catchToLat - motion.catchFromLat) * t;
          motion.lon =
            motion.catchFromLon + (motion.catchToLon - motion.catchFromLon) * t;
          if (elapsedS >= duration) {
            motion.lat = motion.catchToLat;
            motion.lon = motion.catchToLon;
            motion.phase = "coast";
          }
        } else {
          const next = this._extrapolatePosition(
            motion.lat,
            motion.lon,
            motion.heading,
            motion.speedKnots * COAST_SPEED_FACTOR,
            dt
          );
          motion.lat = next.lat;
          motion.lon = next.lon;
        }
      }
    } else {
      motion.lastTs = Number.isFinite(timestamp) ? timestamp : this._nowMs();
    }

    this._applyMotionView(motion, { animate: false });
    if (this._config?.smooth_motion !== false) {
      this._motionRaf = requestAnimationFrame(this._motionBound);
    }
  }

  _followZoom({ resetZoom = false } = {}) {
    if (!resetZoom && this._map && typeof this._map.getZoom === "function") {
      const current = this._map.getZoom();
      if (Number.isFinite(current)) {
        return current;
      }
    }
    return this._configuredZoom();
  }

  _applyMotionView(motion, { animate = false, resetZoom = false } = {}) {
    if (!this._map || !this._planeMarker || !motion) {
      return;
    }
    const latLng = [motion.lat, motion.lon];
    this._planeMarker.setLatLng(latLng);
    const shouldResetZoom = resetZoom || this._pendingZoomReset;
    if (this._pendingZoomReset) {
      this._pendingZoomReset = false;
    }
    // Keep the user's zoom; only pan so the aircraft stays centred.
    this._map.setView(latLng, this._followZoom({ resetZoom: shouldResetZoom }), {
      animate,
    });
  }

  _clearFlightRows() {
    this._flightRowById = new Map();
    this._flightSnapshotById = new Map();
  }

  _escape(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  _flightId(flight) {
    return flight?.id || this._flightLabel(flight);
  }

  _flightLabel(flight) {
    return (
      flight.flight_number ||
      flight.callsign ||
      flight.aircraft_registration ||
      "—"
    );
  }

  _trackedType(flight) {
    const raw = String(flight?.tracked_type || "").toLowerCase();
    if (raw === "live") {
      return "live";
    }
    if (raw === "schedule" || raw === "scheduled") {
      return "scheduled";
    }
    if (raw === "aircraft") {
      return "aircraft";
    }
    // Live position without an explicit type still counts as followable.
    if (this._hasPosition(flight)) {
      return "live";
    }
    return "scheduled";
  }

  _isLive(flight) {
    return this._trackedType(flight) === "live" && this._hasPosition(flight);
  }

  _hasPosition(flight) {
    return (
      flight &&
      flight.latitude != null &&
      flight.longitude != null &&
      !Number.isNaN(Number(flight.latitude)) &&
      !Number.isNaN(Number(flight.longitude))
    );
  }

  _statusLabel(type) {
    switch (type) {
      case "live":
        return "Live";
      case "aircraft":
        return "Aircraft";
      default:
        return "Scheduled";
    }
  }

  _isHelicopter(flight) {
    return String(flight?.aircraft_category || "").toLowerCase() === "helicopter";
  }

  _flightIcon(flight) {
    if (this._isHelicopter(flight)) {
      return "mdi:helicopter";
    }
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

  _formatSpeed(knots) {
    if (knots == null || knots === "") {
      return null;
    }
    const kts = Number(knots);
    if (!Number.isFinite(kts)) {
      return null;
    }
    const kmh = Math.round(kts * 1.852);
    switch (this._config?.speed_unit) {
      case "km/h":
        return `${kmh} km/h`;
      case "mph":
        return `${Math.round((kts * 1.852) / 1.609344)} mph`;
      case "kts":
        return `${Math.round(kts)} kts`;
      default:
        return `${kmh} km/h (${Math.round(kts)} kts)`;
    }
  }

  _formatAltitude(feet) {
    if (feet == null || feet === "") {
      return null;
    }
    const ft = Number(feet);
    if (!Number.isFinite(ft)) {
      return null;
    }
    const meters = Math.round(ft * 0.3048);
    switch (this._config?.altitude_unit) {
      case "m":
        return `${meters} m`;
      case "ft":
        return `${Math.round(ft)} ft`;
      default:
        return `${meters} m (${Math.round(ft)} ft)`;
    }
  }

  /**
   * Format a unix timestamp as HH:MM.
   * When utcOffsetSeconds is provided (FR24 airport timezone offset), the time
   * is shown in that airport's local zone rather than the browser's.
   */
  _formatTimestamp(value, utcOffsetSeconds = null) {
    if (value == null || value === "") {
      return null;
    }
    const seconds = Number(value);
    if (Number.isNaN(seconds) || seconds <= 0) {
      return null;
    }
    const offset = Number(utcOffsetSeconds);
    let hours;
    let minutes;
    if (Number.isFinite(offset)) {
      const shifted = new Date((seconds + offset) * 1000);
      if (Number.isNaN(shifted.getTime())) {
        return null;
      }
      hours = shifted.getUTCHours();
      minutes = shifted.getUTCMinutes();
    } else {
      const date = new Date(seconds * 1000);
      if (Number.isNaN(date.getTime())) {
        return null;
      }
      hours = date.getHours();
      minutes = date.getMinutes();
    }
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
  }

  _flightLegFields(leg) {
    return leg === "departure"
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
  }

  _flightLegTimestamp(flight, leg) {
    for (const field of this._flightLegFields(leg)) {
      const value = Number(flight?.[field]);
      if (Number.isFinite(value) && value > 0) {
        return value;
      }
    }
    return null;
  }

  _flightLegTimezone(flight, leg) {
    if (leg === "departure") {
      return {
        offset: flight?.airport_origin_timezone_offset,
        abbr: flight?.airport_origin_timezone_abbr,
      };
    }
    return {
      offset: flight?.airport_destination_timezone_offset,
      abbr: flight?.airport_destination_timezone_abbr,
    };
  }

  /** City endpoint time in the airport's local timezone, with abbr when known. */
  _flightLegTime(flight, leg) {
    const timestamp = this._flightLegTimestamp(flight, leg);
    if (timestamp == null) {
      return null;
    }
    const { offset, abbr } = this._flightLegTimezone(flight, leg);
    const time = this._formatTimestamp(timestamp, offset);
    if (!time) {
      return null;
    }
    const zone = typeof abbr === "string" ? abbr.trim() : "";
    return zone ? `${time} ${zone}` : time;
  }

  /** Duration as HH:MM, matching Flightradar24 progress labels. */
  _formatDurationClock(seconds) {
    if (!Number.isFinite(seconds)) {
      return null;
    }
    const totalMinutes = Math.max(0, Math.round(Math.abs(seconds) / 60));
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
  }

  _formatDistanceKm(kilometers) {
    if (!Number.isFinite(kilometers) || kilometers < 0) {
      return null;
    }
    // Approximate great-circle estimate — mark with ~ like FR24.
    return `~${Math.round(kilometers).toLocaleString("en-US")} km`;
  }

  _haversineKm(lat1, lon1, lat2, lon2) {
    const toRad = (deg) => (deg * Math.PI) / 180;
    const earthKm = 6371;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return 2 * earthKm * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  /**
   * FR24-style progress: yellow flown segment + labels
   * "~3,237 km, 04:10 ago" / "~8,998 km, in 10:34".
   * Distances are great-circle (origin→aircraft, aircraft→destination);
   * times use absolute unix timestamps (timezone-independent).
   */
  _flightProgressInfo(flight) {
    if (!flight) {
      return null;
    }
    const origin = this._airportPoint(flight, "origin");
    const destination = this._airportPoint(flight, "destination");
    const current = this._hasPosition(flight)
      ? [Number(flight.latitude), Number(flight.longitude)]
      : null;
    const now = Date.now() / 1000;
    const departure = this._flightLegTimestamp(flight, "departure");
    const arrival = this._flightLegTimestamp(flight, "arrival");
    const realArrival = Number(flight.time_real_arrival);
    const onGround =
      Number(flight.on_ground) === 1 || flight.on_ground === true;
    const arrived =
      (Number.isFinite(realArrival) && realArrival > 0) ||
      (onGround && arrival != null && arrival <= now && departure != null && departure < now);
    const departed =
      departure != null &&
      (departure <= now || this._isLive(flight)) &&
      !(onGround && departure > now && !this._isLive(flight));

    let flownKm = null;
    let remainKm = null;
    if (arrived && origin && destination) {
      flownKm = this._haversineKm(origin[0], origin[1], destination[0], destination[1]);
      remainKm = 0;
    } else if (current && origin && destination) {
      flownKm = this._haversineKm(origin[0], origin[1], current[0], current[1]);
      remainKm = this._haversineKm(current[0], current[1], destination[0], destination[1]);
    } else if (current && origin) {
      flownKm = this._haversineKm(origin[0], origin[1], current[0], current[1]);
    } else if (current && destination) {
      remainKm = this._haversineKm(current[0], current[1], destination[0], destination[1]);
    } else if (origin && destination) {
      flownKm = 0;
      remainKm = this._haversineKm(origin[0], origin[1], destination[0], destination[1]);
    } else {
      return null;
    }

    const flown = flownKm != null ? Math.max(0, flownKm) : 0;
    const remain = remainKm != null ? Math.max(0, remainKm) : 0;
    const total = flown + remain;
    let percent = 0;
    if (arrived) {
      percent = 100;
    } else if (total > 0) {
      percent = Math.min(100, Math.max(0, (flown / total) * 100));
    }

    let leftLabel = "";
    if (flownKm != null) {
      const dist = this._formatDistanceKm(flown);
      if (departed && departure != null && now >= departure) {
        const ago = this._formatDurationClock(now - departure);
        leftLabel = ago ? `${dist}, ${ago} ago` : dist;
      } else {
        leftLabel = dist;
      }
    }

    let rightLabel = "";
    if (arrived) {
      rightLabel = remainKm != null ? `${this._formatDistanceKm(0)}, Arrived` : "Arrived";
    } else if (remainKm != null) {
      const dist = this._formatDistanceKm(remain);
      let until = null;
      if (!departed && departure != null && departure > now) {
        until = departure - now;
      } else if (arrival != null && arrival > now) {
        until = arrival - now;
      } else if (arrival != null && arrival <= now) {
        rightLabel = `${dist}, Arriving`;
      }
      if (until != null) {
        const clock = this._formatDurationClock(until);
        rightLabel = clock ? `${dist}, in ${clock}` : dist;
      } else if (!rightLabel) {
        rightLabel = dist;
      }
    }

    if (!leftLabel && !rightLabel) {
      return null;
    }
    return {
      percent: Math.round(percent * 10) / 10,
      leftLabel,
      rightLabel,
    };
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

  _flightRowSnapshot(flight) {
    const type = this._trackedType(flight);
    const live = this._isLive(flight);
    const originCode = flight.airport_origin_country_code || "";
    const destCode = flight.airport_destination_country_code || "";
    return {
      id: this._flightId(flight),
      label: this._flightLabel(flight),
      fr24Url: this._flightFr24Url(flight) || "",
      icon: this._flightIcon(flight),
      aircraft: flight.aircraft_model || flight.aircraft_code || "",
      airline: flight.airline_short || flight.airline || "",
      originCity: flight.airport_origin_city || flight.airport_origin_code_iata || "",
      originCode: String(originCode).length === 2 ? String(originCode).toUpperCase() : "",
      originName:
        flight.airport_origin_country_name || flight.airport_origin_country_code || "",
      destCity:
        flight.airport_destination_city || flight.airport_destination_code_iata || "",
      destCode: String(destCode).length === 2 ? String(destCode).toUpperCase() : "",
      destName:
        flight.airport_destination_country_name ||
        flight.airport_destination_country_code ||
        "",
      depTime: this._flightLegTime(flight, "departure") || "",
      arrTime: this._flightLegTime(flight, "arrival") || "",
      progress: this._flightProgressInfo(flight),
      speed: live ? this._formatSpeed(flight.ground_speed) : null,
      altitude: live ? this._formatAltitude(flight.altitude) : null,
      trackedType: type,
      statusLabel: this._statusLabel(type),
      clickable: live,
      selected: this._selectedFlightId === this._flightId(flight),
    };
  }

  _ensureFlagImg(container, countryCode, title) {
    if (!countryCode || String(countryCode).length !== 2) {
      const existing = container.querySelector(":scope > img.flag");
      if (existing) {
        existing.remove();
      }
      return;
    }
    const code = String(countryCode).toUpperCase();
    const lower = code.toLowerCase();
    const label = title || code;
    const src = `/flightradar24/flags/${lower}.svg`;
    let img = container.querySelector(":scope > img.flag");
    if (!img) {
      img = document.createElement("img");
      img.className = "flag";
      img.width = 16;
      img.height = 12;
      img.decoding = "sync";
      img.onerror = () => {
        img.style.display = "none";
      };
      container.insertBefore(img, container.firstChild);
    }
    if (img.getAttribute("src") !== src) {
      img.style.display = "";
      img.src = src;
    }
    if (img.alt !== code) {
      img.alt = code;
    }
    if (img.title !== label) {
      img.title = label;
    }
  }

  _setOptionalText(parent, className, value) {
    let el = parent.querySelector(`:scope > .${className}`);
    if (!value) {
      if (el) {
        el.remove();
      }
      return;
    }
    if (!el) {
      el = document.createElement("span");
      el.className = className;
      parent.appendChild(el);
    }
    if (el.textContent !== value) {
      el.textContent = value;
    }
  }

  _setFlightLabel(mainEl, label, fr24Url) {
    let link = mainEl.querySelector(":scope > a.flight-link");
    let strong = mainEl.querySelector(":scope > strong");
    if (fr24Url) {
      if (strong) {
        strong.remove();
      }
      if (!link) {
        link = document.createElement("a");
        link.className = "flight-link";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.title = "Open on Flightradar24";
        link.addEventListener("click", (event) => event.stopPropagation());
        const badge = mainEl.querySelector(":scope > .status-badge");
        if (badge) {
          mainEl.insertBefore(link, badge);
        } else {
          mainEl.appendChild(link);
        }
      }
      if (link.href !== fr24Url) {
        link.href = fr24Url;
      }
      if (link.textContent !== label) {
        link.textContent = label;
      }
      return;
    }
    if (link) {
      link.remove();
    }
    if (!strong) {
      strong = document.createElement("strong");
      const badge = mainEl.querySelector(":scope > .status-badge");
      if (badge) {
        mainEl.insertBefore(strong, badge);
      } else {
        mainEl.appendChild(strong);
      }
    }
    if (strong.textContent !== label) {
      strong.textContent = label;
    }
  }

  _setStatusBadge(mainEl, snap) {
    let badge = mainEl.querySelector(":scope > .status-badge");
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "status-badge";
      mainEl.appendChild(badge);
    }
    const typeClass = `status-${snap.trackedType}`;
    badge.className = `status-badge ${typeClass}`;
    if (badge.textContent !== snap.statusLabel) {
      badge.textContent = snap.statusLabel;
    }
  }

  _routeEndpointText(city, time) {
    const parts = [];
    if (city) {
      parts.push(city);
    }
    if (time) {
      parts.push(time);
    }
    return parts.join(" ");
  }

  _setRouteEndpoint(routeEl, side, snap) {
    const isOrigin = side === "origin";
    const city = isOrigin ? snap.originCity : snap.destCity;
    const time = isOrigin ? snap.depTime : snap.arrTime;
    const code = isOrigin ? snap.originCode : snap.destCode;
    const name = isOrigin ? snap.originName : snap.destName;
    const text = this._routeEndpointText(city, time);
    const selector = `:scope > [data-endpoint="${side}"]`;
    let endpoint = routeEl.querySelector(selector);

    if (!text) {
      if (endpoint) {
        endpoint.remove();
      }
      return;
    }

    if (!endpoint) {
      endpoint = document.createElement("span");
      endpoint.dataset.endpoint = side;
      endpoint.className = "route-endpoint";
      const sep = routeEl.querySelector(":scope > .route-sep");
      if (isOrigin) {
        routeEl.insertBefore(endpoint, routeEl.firstChild);
      } else if (sep && sep.nextSibling) {
        routeEl.insertBefore(endpoint, sep.nextSibling);
      } else {
        routeEl.appendChild(endpoint);
      }
    }

    this._ensureFlagImg(endpoint, code, name);

    let textEl = endpoint.querySelector(":scope > span.endpoint-text");
    if (!textEl) {
      textEl = document.createElement("span");
      textEl.className = "endpoint-text";
      endpoint.appendChild(textEl);
    }
    if (textEl.textContent !== text) {
      textEl.textContent = text;
    }
  }

  _syncRouteSep(routeEl) {
    const origin = routeEl.querySelector(':scope > [data-endpoint="origin"]');
    const dest = routeEl.querySelector(':scope > [data-endpoint="dest"]');
    let sep = routeEl.querySelector(":scope > .route-sep");
    if (origin && dest) {
      if (!sep) {
        sep = document.createElement("span");
        sep.className = "route-sep";
        sep.textContent = "→";
      }
      if (origin.nextSibling !== sep) {
        routeEl.insertBefore(sep, origin.nextSibling);
      }
    } else if (sep) {
      sep.remove();
    }
  }

  _setProgress(row, snap) {
    const info = snap.progress;
    let progress = row.querySelector(":scope > .flight-progress");
    if (!info) {
      if (progress) {
        progress.remove();
      }
      return;
    }
    if (!progress) {
      progress = document.createElement("div");
      progress.className = "flight-progress";
      progress.innerHTML = `
        <div class="flight-progress-track">
          <div class="flight-progress-flown"></div>
          <div class="flight-progress-plane" aria-hidden="true"></div>
        </div>
        <div class="flight-progress-labels">
          <span class="flight-progress-left"></span>
          <span class="flight-progress-right"></span>
        </div>
      `;
      const meta = row.querySelector(":scope > .flight-meta");
      if (meta) {
        row.insertBefore(progress, meta);
      } else {
        row.appendChild(progress);
      }
    }
    const flown = progress.querySelector(".flight-progress-flown");
    const plane = progress.querySelector(".flight-progress-plane");
    const left = progress.querySelector(".flight-progress-left");
    const right = progress.querySelector(".flight-progress-right");
    const pct = `${info.percent}%`;
    if (flown && flown.style.width !== pct) {
      flown.style.width = pct;
    }
    if (plane && plane.style.left !== pct) {
      plane.style.left = pct;
    }
    if (left && left.textContent !== info.leftLabel) {
      left.textContent = info.leftLabel;
    }
    if (right && right.textContent !== info.rightLabel) {
      right.textContent = info.rightLabel;
    }
  }

  _setMeta(row, snap) {
    const stats = [snap.speed || "", snap.altitude || ""].filter(Boolean);
    let meta = row.querySelector(":scope > .flight-meta");
    if (!stats.length) {
      if (meta) {
        meta.remove();
      }
      return;
    }
    if (!meta) {
      meta = document.createElement("div");
      meta.className = "flight-meta";
      row.appendChild(meta);
    }
    const existing = [...meta.children];
    stats.forEach((text, index) => {
      let span = existing[index];
      if (!span) {
        span = document.createElement("span");
        meta.appendChild(span);
      }
      if (span.textContent !== text) {
        span.textContent = text;
      }
    });
    for (let i = stats.length; i < existing.length; i++) {
      existing[i].remove();
    }
  }

  _createFlightRow(snap) {
    const row = document.createElement("div");
    row.className = this._flightRowClass(snap);
    row.dataset.flightId = snap.id;

    const main = document.createElement("div");
    main.className = "flight-main";

    const icon = document.createElement("ha-icon");
    icon.setAttribute("icon", snap.icon);
    main.appendChild(icon);
    row.appendChild(main);

    const route = document.createElement("div");
    route.className = "flight-route";
    row.appendChild(route);

    this._patchFlightRow(row, snap, null);
    return row;
  }

  _flightRowClass(snap) {
    const parts = ["flight"];
    if (snap.selected) {
      parts.push("selected");
    }
    if (snap.clickable) {
      parts.push("live");
    } else {
      parts.push("scheduled");
    }
    return parts.join(" ");
  }

  _patchFlightRow(row, snap, prev) {
    row.className = this._flightRowClass(snap);

    const main = row.querySelector(":scope > .flight-main");
    if (!main) {
      return;
    }

    const icon = main.querySelector("ha-icon");
    if (icon && (!prev || prev.icon !== snap.icon)) {
      icon.setAttribute("icon", snap.icon);
    }

    if (!prev || prev.label !== snap.label || prev.fr24Url !== snap.fr24Url) {
      this._setFlightLabel(main, snap.label, snap.fr24Url);
    }

    if (
      !prev ||
      prev.statusLabel !== snap.statusLabel ||
      prev.trackedType !== snap.trackedType
    ) {
      this._setStatusBadge(main, snap);
    }

    if (!prev || prev.aircraft !== snap.aircraft) {
      this._setOptionalText(main, "flight-type", snap.aircraft);
    }
    if (!prev || prev.airline !== snap.airline) {
      this._setOptionalText(main, "muted", snap.airline);
    }

    const hasRoute = !!(
      snap.originCity ||
      snap.depTime ||
      snap.destCity ||
      snap.arrTime
    );
    let route = row.querySelector(":scope > .flight-route");
    if (!hasRoute) {
      if (route) {
        route.remove();
      }
    } else {
      if (!route) {
        route = document.createElement("div");
        route.className = "flight-route";
        const progressEl = row.querySelector(":scope > .flight-progress");
        const meta = row.querySelector(":scope > .flight-meta");
        const before = progressEl || meta;
        if (before) {
          row.insertBefore(route, before);
        } else {
          row.appendChild(route);
        }
      }
      if (
        !prev ||
        prev.originCity !== snap.originCity ||
        prev.depTime !== snap.depTime ||
        prev.originCode !== snap.originCode ||
        prev.originName !== snap.originName
      ) {
        this._setRouteEndpoint(route, "origin", snap);
      }
      if (
        !prev ||
        prev.destCity !== snap.destCity ||
        prev.arrTime !== snap.arrTime ||
        prev.destCode !== snap.destCode ||
        prev.destName !== snap.destName
      ) {
        this._setRouteEndpoint(route, "dest", snap);
      }
      this._syncRouteSep(route);
    }

    const prevProgress = prev?.progress;
    const nextProgress = snap.progress;
    if (
      !prev ||
      prevProgress?.percent !== nextProgress?.percent ||
      prevProgress?.leftLabel !== nextProgress?.leftLabel ||
      prevProgress?.rightLabel !== nextProgress?.rightLabel ||
      !!prevProgress !== !!nextProgress
    ) {
      this._setProgress(row, snap);
    }

    if (
      !prev ||
      prev.speed !== snap.speed ||
      prev.altitude !== snap.altitude
    ) {
      this._setMeta(row, snap);
    }
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
      const row = event.target.closest(".flight.live[data-flight-id]");
      if (!row) {
        return;
      }
      const flightId = row.dataset.flightId;
      if (!flightId) {
        return;
      }
      this._selectFlight(flightId, { userPicked: true });
    });
  }

  _syncFlightListSelection({ scrollToSelected = false } = {}) {
    for (const [id, row] of this._flightRowById) {
      const snap = this._flightSnapshotById.get(id);
      if (snap) {
        snap.selected = id === this._selectedFlightId;
        row.className = this._flightRowClass(snap);
      } else {
        row.classList.toggle("selected", id === this._selectedFlightId);
      }
    }
    if (!scrollToSelected || !this._selectedFlightId) {
      return;
    }
    const selectedRow = this._flightRowById.get(this._selectedFlightId);
    if (selectedRow) {
      selectedRow.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }

  _selectFlight(flightId, { userPicked = false, scrollList = true } = {}) {
    const flight = this._flightsById.get(flightId);
    if (!flight || !this._isLive(flight)) {
      return;
    }
    this._selectedFlightId = flightId;
    if (userPicked) {
      this._userPickedFlight = true;
    }
    this._syncFlightListSelection({ scrollToSelected: scrollList });
    this._lastFollowKey = null;
    this._lastRouteKey = null;
    this._followEpoch += 1;
    void this._syncFollowedFlight(flight, this._followEpoch);
  }

  _firstLiveFlight(flights) {
    return flights.find((flight) => this._isLive(flight)) || null;
  }

  _resolveSelectedFlight(flights) {
    if (this._selectedFlightId) {
      const current = flights.find(
        (flight) => this._flightId(flight) === this._selectedFlightId
      );
      if (current && this._isLive(current)) {
        return current;
      }
    }
    if (this._userPickedFlight && this._selectedFlightId) {
      // User picked a flight that is no longer live — clear plane until they pick again.
      this._selectedFlightId = null;
      return null;
    }
    const firstLive = this._firstLiveFlight(flights);
    this._selectedFlightId = firstLive ? this._flightId(firstLive) : null;
    return firstLive;
  }

  _renderFlightsList(flights, { scrollToSelected = false } = {}) {
    const flightsEl = this.shadowRoot?.getElementById("flights");
    if (!flightsEl || this._config?.show_flights === false) {
      return;
    }
    this._bindFlightsList(flightsEl);
    flightsEl.style.display = "flex";

    if (this._flightRowById.size) {
      const sample = this._flightRowById.values().next().value;
      if (sample && sample.parentElement !== flightsEl) {
        this._clearFlightRows();
      }
    }

    const list = Array.isArray(flights) ? flights : [];

    if (!list.length) {
      for (const row of this._flightRowById.values()) {
        row.remove();
      }
      this._clearFlightRows();
      if (!flightsEl.querySelector(":scope > .empty")) {
        flightsEl.replaceChildren();
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "No tracked flights";
        flightsEl.appendChild(empty);
      }
      return;
    }

    const emptyEl = flightsEl.querySelector(":scope > .empty");
    if (emptyEl) {
      emptyEl.remove();
    }

    const nextIds = new Set();
    const orderedRows = [];

    for (const flight of list) {
      const snap = this._flightRowSnapshot(flight);
      const id = snap.id;
      nextIds.add(id);

      let row = this._flightRowById.get(id);
      const prev = this._flightSnapshotById.get(id);
      if (!row) {
        row = this._createFlightRow(snap);
        this._flightRowById.set(id, row);
      } else {
        this._patchFlightRow(row, snap, prev);
      }
      this._flightSnapshotById.set(id, snap);
      orderedRows.push(row);
    }

    for (const [id, row] of [...this._flightRowById.entries()]) {
      if (!nextIds.has(id)) {
        row.remove();
        this._flightRowById.delete(id);
        this._flightSnapshotById.delete(id);
      }
    }

    let previous = null;
    for (const row of orderedRows) {
      if (previous === null) {
        if (flightsEl.firstChild !== row) {
          flightsEl.insertBefore(row, flightsEl.firstChild);
        }
      } else if (previous.nextSibling !== row) {
        flightsEl.insertBefore(row, previous.nextSibling);
      }
      previous = row;
    }

    if (scrollToSelected && this._selectedFlightId) {
      const selectedRow = this._flightRowById.get(this._selectedFlightId);
      if (selectedRow) {
        selectedRow.scrollIntoView({ block: "nearest", behavior: "smooth" });
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
      #map.map-dark {
        background: #1f1f1f;
      }
      /* Dark OSM/topo tiles without a key-gated dark provider (#366). */
      .map-tiles-dark {
        filter: brightness(0.6) invert(1) contrast(3) hue-rotate(200deg)
          saturate(0.3) brightness(0.7);
      }
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
      }
      .flight.live {
        cursor: pointer;
      }
      .flight.scheduled {
        cursor: default;
        opacity: 0.78;
      }
      .flight.selected {
        background: color-mix(in srgb, var(--primary-color, #03a9f4) 14%, transparent);
        border-radius: 8px;
        box-shadow: inset 0 0 0 2px var(--primary-color, #03a9f4);
        opacity: 1;
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
      .status-badge {
        display: inline-flex;
        align-items: center;
        padding: 1px 7px;
        border-radius: 999px;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        line-height: 1.4;
      }
      .status-live {
        color: #0b6b2d;
        background: color-mix(in srgb, #4caf50 22%, transparent);
      }
      .status-scheduled {
        color: #6a4c00;
        background: color-mix(in srgb, #ffc107 24%, transparent);
      }
      .status-aircraft {
        color: #37474f;
        background: color-mix(in srgb, #90a4ae 28%, transparent);
      }
      .flight-route,
      .flight-progress,
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
      .flight-progress {
        flex-direction: column;
        align-items: stretch;
        gap: 4px;
        max-width: calc(100% - 26px);
      }
      .flight-progress-track {
        position: relative;
        height: 4px;
        border-radius: 999px;
        background: color-mix(in srgb, var(--secondary-text-color) 28%, transparent);
        overflow: visible;
      }
      .flight-progress-flown {
        height: 100%;
        border-radius: 999px;
        background: #f5c518;
        width: 0%;
      }
      .flight-progress-plane {
        position: absolute;
        top: 50%;
        width: 10px;
        height: 10px;
        margin-left: -5px;
        border-radius: 50%;
        background: var(--primary-text-color, #212121);
        border: 2px solid #f5c518;
        box-sizing: border-box;
        transform: translateY(-50%);
        pointer-events: none;
      }
      .flight-progress-labels {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        font-size: 0.78rem;
        line-height: 1.3;
      }
      .flight-progress-left,
      .flight-progress-right {
        color: var(--secondary-text-color);
      }
      .flight-progress-right {
        text-align: right;
      }
      .flight-route .route-endpoint {
        display: inline-flex;
        align-items: center;
        gap: 6px;
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
      .ac-icon, .airport-icon {
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
      .airport-marker {
        width: 18px;
        height: 18px;
        border-radius: 50%;
        border: 2px solid #fff;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.45);
        box-sizing: border-box;
      }
      .airport-marker.origin {
        background: #43a047;
      }
      .airport-marker.destination {
        background: #e53935;
      }
    `;
  }

  _renderShell() {
    if (!this.shadowRoot || !this._config) {
      return;
    }
    if (this.shadowRoot.getElementById("map") && this._map) {
      return;
    }
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
    const currentEl = this.shadowRoot?.getElementById("map");
    if (!this.isConnected || !currentEl) {
      return null;
    }
    mapEl = currentEl;
    if (mapEl._leaflet_id) {
      delete mapEl._leaflet_id;
      mapEl.innerHTML = "";
    }
    // North always up: no map rotation / bearing. Plane icon rotates instead.
    this._map = L.map(mapEl, {
      zoomControl: true,
      attributionControl: false,
      dragging: true,
      scrollWheelZoom: true,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
      touchZoom: true,
    });
    L.control
      .attribution({
        prefix: false,
        position: "bottomright",
      })
      .addTo(this._map);
    this._syncTileLayer();
    this._map.setView(DEFAULT_VIEW, this._configuredZoom());
    this._resizeObserver?.disconnect();
    this._resizeObserver = new ResizeObserver(() => {
      this._map?.invalidateSize({ debounceMoveend: true });
    });
    this._resizeObserver.observe(mapEl);
    requestAnimationFrame(() => this._map?.invalidateSize());
    return this._map;
  }

  _syncTileLayer() {
    if (!this._map || !window.L) {
      return;
    }
    const L = window.L;
    const styleKey = resolveMapStyle(this._config?.map_style);
    const style = MAP_STYLES[styleKey];
    const darkTiles = this._wantsDarkTiles();
    if (this._tileLayer) {
      try {
        this._map.removeLayer(this._tileLayer);
      } catch (_error) {
        // ignore
      }
      this._tileLayer = null;
    }
    const options = {
      maxZoom: style.maxZoom,
      attribution: style.attribution,
      referrerPolicy: "strict-origin-when-cross-origin",
    };
    if (style.subdomains) {
      options.subdomains = style.subdomains;
    }
    if (darkTiles) {
      // className is applied to tile <img>s only — markers/tracks stay unfiltered.
      options.className = "map-tiles-dark";
    }
    this._tileLayer = L.tileLayer(style.url, options).addTo(this._map);
    this._lastDarkTiles = darkTiles;
    this._applyMapThemeChrome();
  }

  _configuredZoom() {
    const zoom = this._config?.zoom;
    if (zoom == null || zoom === "") {
      return DEFAULT_ZOOM;
    }
    const value = Number(zoom);
    if (Number.isNaN(value)) {
      return DEFAULT_ZOOM;
    }
    return Math.min(19, Math.max(1, Math.round(value)));
  }

  _configuredIconSize() {
    const iconSize = this._config?.icon_size;
    if (iconSize == null || iconSize === "") {
      return 32;
    }
    const value = Number(iconSize);
    if (Number.isNaN(value)) {
      return 32;
    }
    return Math.min(64, Math.max(12, Math.round(value)));
  }

  _planeIcon(L, flight) {
    const heading = flight?.heading;
    const helicopter = this._isHelicopter(flight);
    let rotation =
      heading == null || Number.isNaN(Number(heading)) ? 0 : Number(heading);
    if (helicopter) {
      rotation -= 90;
    }
    const size = this._configuredIconSize();
    const svgSize = Math.max(8, size - 2);
    const anchor = size / 2;
    const path = helicopter
      ? "M3,3H17V5H3V3M23,6V10.5L14.75,12.2C14.91,12.6 15,13.04 15,13.5C15,14.9 14.18,16.1 13,16.66V17L13,19H16V21H4A3,3 0 0,1 1,18V17H3V18A1,1 0 0,0 4,19H5V16.74C3.25,16.13 2,14.46 2,12.5C2,10 4,8 6.5,8H9V6H11V8H21V6H23M11,19V17H7V19H11M7.5,10C6.12,10 5,10.9 5,12C5,13.1 6.12,14 7.5,14C8.88,14 10,13.1 10,12C10,10.9 8.88,10 7.5,10Z"
      : "M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z";
    return L.divIcon({
      className: "ac-icon",
      iconSize: [size, size],
      iconAnchor: [anchor, anchor],
      html: `
        <div class="ac-marker" style="width:${size}px;height:${size}px;transform: rotate(${rotation}deg)">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" style="width:${svgSize}px;height:${svgSize}px">
            <path d="${path}"/>
          </svg>
        </div>
      `,
    });
  }

  _airportIcon(L, kind) {
    return L.divIcon({
      className: "airport-icon",
      iconSize: [18, 18],
      iconAnchor: [9, 9],
      html: `<div class="airport-marker ${kind}"></div>`,
    });
  }

  _airportPoint(flight, side) {
    const latKey =
      side === "origin"
        ? "airport_origin_latitude"
        : "airport_destination_latitude";
    const lonKey =
      side === "origin"
        ? "airport_origin_longitude"
        : "airport_destination_longitude";
    // Number(null) === 0 — treat missing coords as absent, not Null Island.
    if (flight?.[latKey] == null || flight?.[lonKey] == null) {
      return null;
    }
    const lat = Number(flight[latKey]);
    const lon = Number(flight[lonKey]);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      return null;
    }
    return [lat, lon];
  }

  _normalizeTrack(coordinates) {
    if (!Array.isArray(coordinates)) {
      return [];
    }
    return coordinates
      .filter((point) => Array.isArray(point) && point.length >= 2)
      .map((point) => [Number(point[0]), Number(point[1])])
      .filter(
        (point) => Number.isFinite(point[0]) && Number.isFinite(point[1])
      );
  }

  _samePoint(a, b, epsilon = 1e-5) {
    return (
      !!a &&
      !!b &&
      Math.abs(a[0] - b[0]) <= epsilon &&
      Math.abs(a[1] - b[1]) <= epsilon
    );
  }

  _appendUniquePoint(points, point) {
    if (!point) {
      return;
    }
    if (!points.length || !this._samePoint(points[points.length - 1], point)) {
      points.push(point);
    }
  }

  /**
   * Build the followed-flight path:
   * origin (if any) → coordinates trail → current position → destination (if any).
   * No destination ⇒ origin + coordinates; no origin ⇒ coordinates (+ destination).
   */
  _buildRouteLatLngs(flight) {
    if (!flight) {
      return [];
    }
    const origin = this._airportPoint(flight, "origin");
    const destination = this._airportPoint(flight, "destination");
    const track = this._normalizeTrack(flight.coordinates);
    const current = this._hasPosition(flight)
      ? [Number(flight.latitude), Number(flight.longitude)]
      : null;

    const points = [];
    if (origin) {
      this._appendUniquePoint(points, origin);
    }
    for (const point of track) {
      this._appendUniquePoint(points, point);
    }
    if (current) {
      this._appendUniquePoint(points, current);
    }
    if (destination) {
      this._appendUniquePoint(points, destination);
    }
    return points.length >= 2 ? points : [];
  }

  _routeKey(flight) {
    if (!flight || this._config?.show_route === false) {
      return "off";
    }
    const points = this._buildRouteLatLngs(flight);
    if (points.length < 2) {
      return "none";
    }
    const first = points[0].join(",");
    const last = points[points.length - 1].join(",");
    return `${this._flightId(flight)}|${points.length}|${first}|${last}`;
  }

  _drawRoute(L, flight, { force = false } = {}) {
    const routeKey = this._routeKey(flight);
    if (!force && routeKey === this._lastRouteKey && this._routeLayer) {
      return;
    }
    if (this._routeLayer) {
      try {
        this._map.removeLayer(this._routeLayer);
      } catch (_error) {
        // ignore
      }
      this._routeLayer = null;
    }
    this._lastRouteKey = routeKey;
    if (!this._map || this._config?.show_route === false || !flight) {
      return;
    }
    const points = this._buildRouteLatLngs(flight);
    if (points.length < 2) {
      return;
    }

    const origin = this._airportPoint(flight, "origin");
    const destination = this._airportPoint(flight, "destination");
    const current = this._hasPosition(flight)
      ? [Number(flight.latitude), Number(flight.longitude)]
      : null;

    // Flown path up to the aircraft; remaining leg to destination dashed.
    let splitIndex = points.length;
    if (current) {
      for (let i = points.length - 1; i >= 0; i--) {
        if (this._samePoint(points[i], current)) {
          splitIndex = i;
          break;
        }
      }
    } else if (destination && this._samePoint(points[points.length - 1], destination)) {
      splitIndex = points.length - 1;
    }

    const flown = points.slice(0, splitIndex + 1);
    const remaining = points.slice(splitIndex);

    this._routeLayer = L.layerGroup().addTo(this._map);
    if (flown.length >= 2) {
      L.polyline(flown, {
        color: "#0277bd",
        weight: 3,
        opacity: 0.9,
        lineJoin: "round",
        lineCap: "round",
      }).addTo(this._routeLayer);
    }
    if (remaining.length >= 2) {
      L.polyline(remaining, {
        color: "#0277bd",
        weight: 3,
        opacity: 0.75,
        dashArray: "8 6",
        lineJoin: "round",
        lineCap: "round",
      }).addTo(this._routeLayer);
    }
    if (origin) {
      L.marker(origin, {
        icon: this._airportIcon(L, "origin"),
        interactive: false,
        keyboard: false,
      }).addTo(this._routeLayer);
    }
    if (destination) {
      L.marker(destination, {
        icon: this._airportIcon(L, "destination"),
        interactive: false,
        keyboard: false,
      }).addTo(this._routeLayer);
    }
  }

  _markerIconKey(flight) {
    const heli = this._isHelicopter(flight) ? "1" : "0";
    return `${heli}:${String(flight?.heading ?? "")}:${this._configuredIconSize()}`;
  }

  async _syncFollowedFlight(flight, epoch = this._followEpoch) {
    const L = await loadLeaflet();
    if (epoch !== this._followEpoch) {
      return;
    }
    const map = await this._ensureMap();
    if (!map || epoch !== this._followEpoch) {
      return;
    }

    // Prefer the currently selected live flight — a newer click may have
    // changed the target while we awaited Leaflet/map init.
    if (this._selectedFlightId) {
      const selected = this._flightsById.get(this._selectedFlightId);
      if (selected && this._isLive(selected)) {
        flight = selected;
      }
    }

    if (!flight || !this._isLive(flight)) {
      this._clearMapOverlays();
      this._lastFollowKey = "none";
      map.setView(DEFAULT_VIEW, this._configuredZoom(), { animate: false });
      return;
    }

    const flightId = this._flightId(flight);
    const latLng = [Number(flight.latitude), Number(flight.longitude)];
    const followKey = [
      flightId,
      latLng[0],
      latLng[1],
      flight.heading ?? "",
      flight.ground_speed ?? "",
      flight.on_ground ?? "",
      this._routeKey(flight),
      `icon:${this._configuredIconSize()}`,
      this._config.smooth_motion === false ? "smooth:0" : "smooth:1",
    ].join("|");
    if (followKey === this._lastFollowKey && this._planeMarker && this._motion) {
      // Still refresh the route if airports arrived for an otherwise identical fix.
      this._drawRoute(L, flight);
      return;
    }
    const flightChanged =
      !this._motion || this._motion.flightId !== flightId;
    this._lastFollowKey = followKey;

    map.invalidateSize();
    this._applyFlightMotion(flight, { flightChanged });
    if (epoch !== this._followEpoch) {
      return;
    }

    if (!this._planeMarker) {
      this._planeMarker = L.marker([this._motion.lat, this._motion.lon], {
        icon: this._planeIcon(L, flight),
        title: this._flightLabel(flight),
        zIndexOffset: 1000,
        keyboard: false,
      }).addTo(map);
      this._planeMarker._frIconKey = this._markerIconKey(flight);
    } else {
      // Always refresh icon/title on flight switch; heading-only updates use the key.
      const iconKey = this._markerIconKey(flight);
      if (flightChanged || this._planeMarker._frIconKey !== iconKey) {
        this._planeMarker._frIconKey = iconKey;
        this._planeMarker.setIcon(this._planeIcon(L, flight));
      }
      this._planeMarker.options.title = this._flightLabel(flight);
      this._planeMarker.setLatLng([this._motion.lat, this._motion.lon]);
    }

    this._drawRoute(L, flight, { force: flightChanged });
    // Shadow-DOM / first layout: redraw once the map has a real size so the
    // origin→destination polyline is not lost on the initial paint.
    requestAnimationFrame(() => {
      if (epoch !== this._followEpoch || !this._map) {
        return;
      }
      this._map.invalidateSize({ debounceMoveend: true });
      this._drawRoute(L, flight, { force: true });
    });

    this._applyMotionView(this._motion, {
      animate: false,
      resetZoom: flightChanged && this._config?.smooth_motion === false,
    });

    if (this._config?.smooth_motion === false) {
      if (this._motionRaf != null) {
        cancelAnimationFrame(this._motionRaf);
        this._motionRaf = null;
      }
      return;
    }
    this._ensureMotionLoop();
  }

  async _update() {
    this._renderShell();
    if (!this.shadowRoot || !this._config || !this._hass) {
      return;
    }

    const headerEl = this.shadowRoot.querySelector(".header");
    const titleEl = this.shadowRoot.getElementById("title");
    const countEl = this.shadowRoot.getElementById("count");
    const warningEl = this.shadowRoot.getElementById("warning");
    const flightsEl = this.shadowRoot.getElementById("flights");
    const mapWrap = this.shadowRoot.querySelector(".map-wrap");

    if (headerEl) {
      headerEl.style.display =
        this._config.show_header === false ? "none" : "flex";
    }

    const state = this._hass.states[this._config.entity];
    if (this._lastEntity !== this._config.entity) {
      this._lastEntity = this._config.entity;
      this._resetSelectionState();
    }

    if (!state) {
      if (mapWrap) mapWrap.style.display = "none";
      if (flightsEl) flightsEl.style.display = "none";
      if (warningEl) {
        warningEl.style.display = "block";
        warningEl.textContent = `Entity not found: ${this._config.entity}`;
      }
      if (titleEl) titleEl.textContent = "Flightradar24 Tracking";
      if (countEl) countEl.textContent = "";
      return;
    }

    const name =
      this._config.title ||
      state.attributes.friendly_name ||
      this._config.entity;
    if (titleEl) titleEl.textContent = name;

    const flights = Array.isArray(state.attributes.flights)
      ? state.attributes.flights
      : [];
    this._flightsById = new Map(
      flights.map((flight) => [this._flightId(flight), flight])
    );

    const liveCount = flights.filter((flight) => this._isLive(flight)).length;
    const scheduledCount = flights.length - liveCount;
    if (countEl) {
      const parts = [`${flights.length} tracked`];
      if (flights.length) {
        parts.push(`${liveCount} live`);
        if (scheduledCount) {
          parts.push(`${scheduledCount} scheduled`);
        }
      }
      countEl.textContent = parts.join(" · ");
    }

    const selected = this._resolveSelectedFlight(flights);
    if (warningEl) warningEl.style.display = "none";

    // Map only while a live (active) flight is followed; hide when the list is
    // scheduled-only or empty, and show again as soon as one becomes live.
    if (!selected) {
      if (mapWrap) mapWrap.style.display = "none";
      this._followEpoch += 1;
      this._clearMapOverlays();
      this._lastFollowKey = "none";
    } else {
      if (mapWrap) mapWrap.style.display = "block";
      const epoch = this._followEpoch;
      try {
        await this._syncFollowedFlight(selected, epoch);
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
        flightsEl.replaceChildren();
        this._clearFlightRows();
      } else {
        this._renderFlightsList(flights);
      }
    }
  }
}

class Flightradar24TrackingCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
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
        select {
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
        <input type="checkbox" id="show_header" ${this._config.show_header !== false ? "checked" : ""} />
        <span>Show header</span>
      </div>
      <div class="row check">
        <input type="checkbox" id="show_flights" ${this._config.show_flights !== false ? "checked" : ""} />
        <span>Show flights list</span>
      </div>
      <div class="row check">
        <input type="checkbox" id="show_route" ${this._config.show_route !== false ? "checked" : ""} />
        <span>Show flight route (airports + track)</span>
      </div>
      <div class="row check">
        <input type="checkbox" id="smooth_motion" ${this._config.smooth_motion !== false ? "checked" : ""} />
        <span>Smooth map motion between sensor updates</span>
      </div>
      <div class="row">
        <label>Map style</label>
        <select id="map_style">
          ${Object.entries(MAP_STYLES)
            .map(([key, style]) => {
              const selected =
                resolveMapStyle(this._config.map_style) === key ? "selected" : "";
              return `<option value="${key}" ${selected}>${style.label}</option>`;
            })
            .join("")}
        </select>
      </div>
      <div class="row">
        <label>Map theme</label>
        <select id="theme_mode">
          ${Object.entries(THEME_MODES)
            .map(([key, label]) => {
              const selected =
                resolveThemeMode(this._config.theme_mode) === key ? "selected" : "";
              return `<option value="${key}" ${selected}>${label}</option>`;
            })
            .join("")}
        </select>
      </div>
      <div class="row">
        <label>Zoom (1–19)</label>
        <input
          type="number"
          id="zoom"
          min="1"
          max="19"
          step="1"
          value="${this._escape(String(this._config.zoom ?? DEFAULT_ZOOM))}"
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
          placeholder="32"
          value="${this._config.icon_size != null ? this._escape(String(this._config.icon_size)) : ""}"
        />
      </div>
      ${Object.entries(DISPLAY_UNITS)
        .map(
          ([key, units]) => `
          <div class="row">
            <label for="${key}">${units.label}</label>
            <select id="${key}">
              ${Object.entries(units.options)
                .map(([unit, label]) => {
                  const selected =
                    resolveDisplayUnit(key, this._config[key]) === unit
                      ? "selected"
                      : "";
                  return `<option value="${unit}" ${selected}>${label}</option>`;
                })
                .join("")}
            </select>
          </div>
        `
        )
        .join("")}
    `;

    const mount = this.shadowRoot.getElementById("entity-picker");
    const picker = document.createElement("ha-entity-picker");
    picker.hass = this._hass;
    picker.value = this._config.entity || "";
    picker.label = "Additional tracked sensor";
    picker.allowCustomEntity = true;
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

    this.shadowRoot.getElementById("show_header").addEventListener("change", (event) => {
      this._fireConfigChanged({
        ...this._config,
        show_header: event.target.checked,
      });
    });

    this.shadowRoot.getElementById("show_flights").addEventListener("change", (event) => {
      this._fireConfigChanged({
        ...this._config,
        show_flights: event.target.checked,
      });
    });

    this.shadowRoot.getElementById("show_route").addEventListener("change", (event) => {
      this._fireConfigChanged({
        ...this._config,
        show_route: event.target.checked,
      });
    });

    this.shadowRoot.getElementById("smooth_motion").addEventListener("change", (event) => {
      this._fireConfigChanged({
        ...this._config,
        smooth_motion: event.target.checked,
      });
    });

    this.shadowRoot.getElementById("map_style").addEventListener("change", (event) => {
      this._fireConfigChanged({
        ...this._config,
        map_style: resolveMapStyle(event.target.value),
      });
    });

    this.shadowRoot.getElementById("theme_mode").addEventListener("change", (event) => {
      this._fireConfigChanged({
        ...this._config,
        theme_mode: resolveThemeMode(event.target.value),
      });
    });

    for (const key of Object.keys(DISPLAY_UNITS)) {
      this.shadowRoot.getElementById(key).addEventListener("change", (event) => {
        this._fireConfigChanged({
          ...this._config,
          [key]: resolveDisplayUnit(key, event.target.value),
        });
      });
    }

    this.shadowRoot.getElementById("zoom").addEventListener("change", (event) => {
      const zoom = Number(event.target.value);
      this._fireConfigChanged({
        ...this._config,
        zoom: Number.isNaN(zoom)
          ? DEFAULT_ZOOM
          : Math.min(19, Math.max(1, Math.round(zoom))),
      });
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

customElements.define("flightradar24-tracking-card", Flightradar24TrackingCard);
customElements.define(
  "flightradar24-tracking-card-editor",
  Flightradar24TrackingCardEditor
);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "flightradar24-tracking-card",
  name: "Flightradar24 Tracking Card",
  description:
    "Follow additional tracked flights: map centres on a live aircraft with optional airport+track route and a live/scheduled list",
  preview: true,
  documentationURL:
    "https://github.com/AlexandrErohin/home-assistant-flightradar24",
});
