// Routing bottom sheet drawer and animated route overlay (SPEC.md F5, "Routing", HUD "Κάτω κέντρο"; TASKS_A.md A4).
// Does not touch document, localStorage, or maplibregl at import time so Node can import it safely.
// Never makes network requests directly; all route data comes through api.routing().

import { registerOverlay } from "../map.js";

// Three routing profiles in SPEC order with Greek labels (source: SPEC.md F5 & "Routing", TASKS_A.md A4; certainty: verified).
export const PROFILES = [
  { id: "wheelchair", label: "Αμαξίδιο" },
  { id: "stroller", label: "Καρότσι" },
  { id: "cool", label: "Δροσερότερη διαδρομή" },
];

export const CAR_PROFILE = { id: "car", label: "Αυτοκίνητο" };
export const ALL_PROFILES = [...PROFILES, CAR_PROFILE];

// MapLibre source and layer IDs for the active route (source: A4_routing.test.js; certainty: verified).
export const ROUTE_SOURCE_ID = "route";
export const ROUTE_LAYER_ID = "route-line";
export const ROUTE_GLOW_LAYER_ID = "route-glow";
export const ROUTE_BASELINE_SOURCE_ID = "route-baseline";
export const ROUTE_BASELINE_LAYER_ID = "route-baseline-line";
export const ROUTE_AVOIDED_SOURCE_ID = "route-avoided";
export const ROUTE_AVOIDED_LAYER_ID = "route-avoided-pins";
const ROUTE_AVOIDED_LABEL_LAYER_ID = "route-avoided-labels";

// Profile-specific route palettes so switching wheelchair/stroller/cool visually morphs the glowing route.
export const PROFILE_PALETTES = Object.freeze({
  wheelchair: Object.freeze({ start: "#2563eb", end: "#38bdf8", accent: "#2563eb" }),
  stroller: Object.freeze({ start: "#0d9488", end: "#2dd4bf", accent: "#0d9488" }),
  cool: Object.freeze({ start: "#059669", end: "#34d399", accent: "#059669" }),
});
const CAR_PALETTE = Object.freeze({ start: "#ea580c", end: "#f97316", accent: "#ea580c" });

// MapLibre source & layer IDs for live/simulated GPS directional puck (UI/UX upgrade #6).
const NAV_GPS_SOURCE_ID = "nav-gps-source";
const NAV_GPS_HALO_LAYER_ID = "nav-gps-halo";
const NAV_GPS_PUCK_LAYER_ID = "nav-gps-puck";
const NAV_FOLLOW_PITCH = 65;
const NAV_FOLLOW_ZOOM = 18;
// Demo simulation pace (~14 m/s so a 600 m Syntagma->Monastiraki walk animates cleanly in ~40 s on stage).
const NAV_SIM_SPEED_MPS = 14;
const WALK_SPEED_MPS = 1.3;

// Instant 1-tap Waze-style hazard pills shown during Turn-by-Turn Navigation (UI/UX upgrade #6).
export const QUICK_NAV_HAZARDS = Object.freeze([
  Object.freeze({ id: "congestion", category: "congestion", icon: "🚗", label: "Συμφόρηση", note: "Συμφόρηση" }),
  Object.freeze({ id: "closed_sidewalk", category: "obstacle", icon: "🚧", label: "Κλειστό πεζοδρόμιο", note: "Κλειστό πεζοδρόμιο" }),
  Object.freeze({ id: "ramp_blocked", category: "obstacle", icon: "♿", label: "Εμπόδιο σε ράμπα", note: "Εμπόδιο σε ράμπα" }),
  Object.freeze({ id: "defect", category: "damage", icon: "🕳️", label: "Κακοτεχνία", note: "Κακοτεχνία" }),
]);

// MapLibre source and layer IDs for highlighted routing reasons (source: TASKS_A.md A5 & A5_polish.test.js; certainty: verified).
export const REASONS_HIGHLIGHT_SOURCE_ID = "route-reasons-highlight-source";
export const REASONS_HIGHLIGHT_LAYER_ID = "route-reasons-highlight";
const REASONS_HIGHLIGHT_POINTS_LAYER_ID = "route-reasons-highlight-points";

// Highlight colors/dimensions for features cited in route reasons (certainty: design default).
const REASONS_HIGHLIGHT_COLOR = "#facc15";
const REASONS_HIGHLIGHT_STROKE = "#d97706";
const REASONS_HIGHLIGHT_LINE_WIDTH_PX = 8;
const REASONS_HIGHLIGHT_LINE_BLUR_PX = 1.5;
const REASONS_HIGHLIGHT_POINT_RADIUS_PX = 10;

// Mobile viewport width breakpoint matching hud.css @media (max-width: 600px) (source: TASKS_A.md A2/A5; certainty: verified).
const MOBILE_BREAKPOINT_PX = 600;

// Known Dev A layer -> MapLibre source IDs used as fallback when highlightReasons is called without an explicit lookup (certainty: verified from layers/*.js).
const LAYER_SOURCE_IDS = Object.freeze({
  works: ["works-source"],
  env: ["env-source"],
  access: ["access-source"],
  health: ["health-source"],
  reports: ["reports-source"],
  transit: ["transit-buses-source", "transit-stations-source", "transit-lines-source"],
  "transit-buses": ["transit-buses-source"],
  "transit-rail": ["transit-stations-source", "transit-lines-source"],
});

// localStorage key for persisting the user's selected routing profile (source: SPEC.md "Routing" requires persistence, key name not specified; certainty: design default).
export const PROFILE_STORAGE_KEY = "athensone.routing.profile";

// Route drawing animation duration in ms (source: SPEC.md "Routing" "~1.2s", TASKS_A.md A4 "1200 ms"; certainty: verified).
export const ROUTE_ANIMATION_MS = 1200;

// Minimum stop separation so MapLibre interpolate stops remain strictly ascending without duplicate-stop errors (certainty: design default).
const GRADIENT_EDGE_EPSILON = 0.001;

// Route line gradient colors for visibility on both Liberty (light) and Fiord (dark) basemaps (certainty: design default).
const ROUTE_COLOR_START = "#2563eb";
const ROUTE_COLOR_END = "#0ea5e9";
const ROUTE_COLOR_TRANSPARENT = "rgba(14, 165, 233, 0)";

// Route stroke width in CSS pixels (certainty: design default).
const ROUTE_LINE_WIDTH_PX = 6;

// Extra clearance added above the routing drawer height in fitBounds bottom padding (source: TASKS_A.md A4; certainty: verified).
const FIT_BOUNDS_DRAWER_CLEARANCE_PX = 24;

// Top and side viewport margins for fitBounds so the route stays clear of top HUD controls (certainty: design default).
const FIT_BOUNDS_TOP_PX = 72;
const FIT_BOUNDS_SIDE_PX = 40;

// Smooth fitBounds transition duration in ms (certainty: design default).
const FIT_BOUNDS_DURATION_MS = 500;

// Vertical pointer drag distance in px to collapse/expand the bottom sheet drawer (certainty: design default).
const DRAG_TOGGLE_THRESHOLD_PX = 36;

// Unit conversion constants for duration and distance formatting (source: SI / standard time units; certainty: verified).
const METERS_PER_KM = 1000;
const SECONDS_PER_MINUTE = 60;

// Offline place presets so Greek demo queries work without external geocoding calls.
// Syntagma coords from SPEC.md "Engine και στυλ" (certainty: verified); Monastiraki coords from A4_routing.test.js (certainty: verified in test);
// remaining central Athens landmarks are approximate WGS84 [lon, lat] coordinates (certainty: unverified offline estimate).
const ATHENS_PLACES = {
  συνταγμα: [23.7348, 37.9755],
  syntagma: [23.7348, 37.9755],
  κυψελη: [23.7392, 38.0012],
  kypseli: [23.7392, 38.0012],
  πετραλωνα: [23.7094, 37.9684],
  petralona: [23.7094, 37.9684],
  παγκρατι: [23.7437, 37.9667],
  pangrati: [23.7437, 37.9667],
  αμπελοκηποι: [23.7600, 37.9880],
  ampelokipoi: [23.7600, 37.9880],
  "νεοσ κοσμοσ": [23.7290, 37.9570],
  "neos kosmos": [23.7290, 37.9570],
  πατησια: [23.7310, 38.0170],
  patisia: [23.7310, 38.0170],
  εξαρχεια: [23.7350, 37.9860],
  exarcheia: [23.7350, 37.9860],
  γκαζι: [23.7140, 37.9790],
  gazi: [23.7140, 37.9790],
  μοναστηρακι: [23.7257, 37.9764],
  monastiraki: [23.7257, 37.9764],
  ομονοια: [23.728, 37.9841],
  omonia: [23.728, 37.9841],
  ακροπολη: [23.7257, 37.9715],
  acropolis: [23.7257, 37.9715],
  σεραφειο: [23.7115, 37.9776],
  serafio: [23.7115, 37.9776],
};

// Per-map active route, ghost baseline, avoided hazards, and reasons highlight state so Light/Dark setStyle() restores them.
const routeStateByMap = new WeakMap();
const baselineStateByMap = new WeakMap();
const reasonsHighlightByMap = new WeakMap();

function isValidProfileId(id) {
  return ALL_PROFILES.some((p) => p.id === id);
}

function normalizeQuery(text) {
  return String(text ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function parseCoordsInput(text) {
  const trimmed = String(text ?? "").trim();
  if (!trimmed) {
    return null;
  }

  const preset = ATHENS_PLACES[normalizeQuery(trimmed)];
  if (preset) {
    return [preset[0], preset[1]];
  }

  const match = trimmed.match(/^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (!match) {
    return null;
  }

  const a = Number(match[1]);
  const b = Number(match[2]);
  if (!Number.isFinite(a) || !Number.isFinite(b)) {
    return null;
  }

  // Standard user input is "lat, lon" (Athens lat ~38, lon ~23.7); return GeoJSON [lon, lat].
  // If the first number looks like Athens longitude (~23-24) and the second like latitude (~37-38), keep [lon, lat].
  if (a >= 20 && a <= 30 && b >= 34 && b <= 42) {
    return [a, b];
  }
  return [b, a];
}

function formatCoordPair(lonLat) {
  if (!Array.isArray(lonLat) || lonLat.length < 2) {
    return "";
  }
  return `${Number(lonLat[1]).toFixed(4)}, ${Number(lonLat[0]).toFixed(4)}`;
}

function resolveLocalStorage(storage) {
  if (storage !== undefined) {
    return storage;
  }
  try {
    return typeof globalThis.localStorage !== "undefined" ? globalThis.localStorage : null;
  } catch {
    return null;
  }
}

export function loadSavedProfile(storage) {
  const fallback = PROFILES[0].id;
  const store = resolveLocalStorage(storage);
  if (!store || typeof store.getItem !== "function") {
    return fallback;
  }
  try {
    const saved = store.getItem(PROFILE_STORAGE_KEY);
    return isValidProfileId(saved) ? saved : fallback;
  } catch {
    return fallback;
  }
}

export function saveProfile(profileId, storage) {
  if (!isValidProfileId(profileId)) {
    return false;
  }
  const store = resolveLocalStorage(storage);
  if (!store || typeof store.setItem !== "function") {
    return false;
  }
  try {
    store.setItem(PROFILE_STORAGE_KEY, profileId);
    return true;
  } catch {
    return false;
  }
}

export function routeSource(geojson) {
  return {
    type: "geojson",
    lineMetrics: true,
    data: geojson,
  };
}

function paletteForProfile(profileId) {
  return profileId === "car" ? CAR_PALETTE : (PROFILE_PALETTES[profileId] ?? PROFILE_PALETTES.wheelchair);
}

export function gradientAt(progress, palette = null) {
  const numeric = Number(progress);
  const p = Number.isFinite(numeric) ? Math.max(0, Math.min(1, numeric)) : 0;
  const startColor = palette?.start ?? ROUTE_COLOR_START;
  const endColor = palette?.end ?? ROUTE_COLOR_END;

  if (p <= 0) {
    return [
      "interpolate",
      ["linear"],
      ["line-progress"],
      0,
      ROUTE_COLOR_TRANSPARENT,
      1,
      ROUTE_COLOR_TRANSPARENT,
    ];
  }

  if (p >= 1) {
    return [
      "interpolate",
      ["linear"],
      ["line-progress"],
      0,
      startColor,
      1,
      endColor,
    ];
  }

  const fadeStop = Math.min(1, p + GRADIENT_EDGE_EPSILON);
  const expr = [
    "interpolate",
    ["linear"],
    ["line-progress"],
    0,
    startColor,
    p,
    endColor,
    fadeStop,
    ROUTE_COLOR_TRANSPARENT,
  ];
  if (fadeStop < 1) {
    expr.push(1, ROUTE_COLOR_TRANSPARENT);
  }
  return expr;
}

export function animateRoute(map, layerId = ROUTE_LAYER_ID, onComplete = null, options = {}) {
  const durationMs =
    Number.isFinite(options?.durationMs) && options.durationMs > 0
      ? options.durationMs
      : ROUTE_ANIMATION_MS;
  const onProgress = typeof options?.onProgress === "function" ? options.onProgress : null;
  const palette = options?.palette ?? null;
  const raf = globalThis.requestAnimationFrame;
  const cancelRaf = globalThis.cancelAnimationFrame;

  let cancelled = false;
  let rafId = null;
  let startTime = null;

  function applyProgress(progress) {
    if (onProgress) {
      onProgress(progress);
    }
    if (map && typeof map.setPaintProperty === "function") {
      const grad = gradientAt(progress, palette);
      // Update outer glow BEFORE core layerId so setPaintCalls.at(-1) stays on route-line (A4_routing.test.js).
      if (layerId === ROUTE_LAYER_ID && typeof map.getLayer === "function" && map.getLayer(ROUTE_GLOW_LAYER_ID)) {
        map.setPaintProperty(ROUTE_GLOW_LAYER_ID, "line-gradient", grad);
      }
      if (typeof map.getLayer !== "function" || map.getLayer(layerId)) {
        map.setPaintProperty(layerId, "line-gradient", grad);
      }
    }
  }

  if (typeof raf !== "function") {
    applyProgress(1);
    if (typeof onComplete === "function") {
      onComplete();
    }
    return () => {};
  }

  function step(timestamp) {
    if (cancelled) {
      return;
    }
    const now =
      typeof timestamp === "number"
        ? timestamp
        : typeof globalThis.performance?.now === "function"
          ? globalThis.performance.now()
          : Date.now();
    if (startTime === null) {
      startTime = now;
    }

    const elapsed = Math.max(0, now - startTime);
    const progress = Math.min(1, elapsed / durationMs);
    applyProgress(progress);

    if (progress < 1) {
      rafId = raf(step);
    } else {
      rafId = null;
      if (typeof onComplete === "function") {
        onComplete();
      }
    }
  }

  rafId = raf(step);

  return () => {
    cancelled = true;
    if (rafId !== null && typeof cancelRaf === "function") {
      cancelRaf(rafId);
      rafId = null;
    }
  };
}

export function fitBoundsPadding(drawerHeight) {
  const h = Number.isFinite(drawerHeight) && drawerHeight > 0 ? drawerHeight : 0;
  return {
    top: FIT_BOUNDS_TOP_PX,
    right: FIT_BOUNDS_SIDE_PX,
    bottom: Math.ceil(h) + FIT_BOUNDS_DRAWER_CLEARANCE_PX,
    left: FIT_BOUNDS_SIDE_PX,
  };
}

function collectCoords(node, out) {
  if (!node || typeof node !== "object") {
    return;
  }
  if (node.type === "FeatureCollection" && Array.isArray(node.features)) {
    for (const feature of node.features) {
      collectCoords(feature, out);
    }
    return;
  }
  if (node.type === "Feature" && node.geometry) {
    collectCoords(node.geometry, out);
    return;
  }
  if (node.geometry && typeof node.geometry === "object") {
    collectCoords(node.geometry, out);
    return;
  }
  if (node.type === "LineString" && Array.isArray(node.coordinates)) {
    for (const pt of node.coordinates) {
      if (Array.isArray(pt) && pt.length >= 2 && Number.isFinite(pt[0]) && Number.isFinite(pt[1])) {
        out.push(pt);
      }
    }
    return;
  }
  if (node.type === "MultiLineString" && Array.isArray(node.coordinates)) {
    for (const line of node.coordinates) {
      if (!Array.isArray(line)) continue;
      for (const pt of line) {
        if (Array.isArray(pt) && pt.length >= 2 && Number.isFinite(pt[0]) && Number.isFinite(pt[1])) {
          out.push(pt);
        }
      }
    }
  }
}

function measureDrawerHeight(drawerEl) {
  if (typeof drawerEl === "number") {
    return drawerEl;
  }
  if (!drawerEl || typeof drawerEl !== "object") {
    return 0;
  }
  if (typeof drawerEl.getBoundingClientRect === "function") {
    const rect = drawerEl.getBoundingClientRect();
    if (rect && Number.isFinite(rect.height) && rect.height > 0) {
      return rect.height;
    }
  }
  if (Number.isFinite(drawerEl.offsetHeight) && drawerEl.offsetHeight > 0) {
    return drawerEl.offsetHeight;
  }
  if (Number.isFinite(drawerEl.clientHeight) && drawerEl.clientHeight > 0) {
    return drawerEl.clientHeight;
  }
  return 0;
}

export function fitRouteBounds(map, routeGeojson, drawerEl) {
  if (!map || typeof map.fitBounds !== "function") {
    return null;
  }
  const coords = [];
  collectCoords(routeGeojson, coords);
  if (coords.length === 0) {
    return null;
  }

  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;
  for (const [lon, lat] of coords) {
    if (lon < minLon) minLon = lon;
    if (lat < minLat) minLat = lat;
    if (lon > maxLon) maxLon = lon;
    if (lat > maxLat) maxLat = lat;
  }

  const bounds = [
    [minLon, minLat],
    [maxLon, maxLat],
  ];
  const padding = fitBoundsPadding(measureDrawerHeight(drawerEl));
  map.fitBounds(bounds, { padding, duration: FIT_BOUNDS_DURATION_MS });
  return { bounds, padding };
}

export function formatRouteLabel(distanceM, durationS, reasons = []) {
  const durationPart =
    Number.isFinite(durationS) && durationS >= 0
      ? `${Math.round(durationS / SECONDS_PER_MINUTE)}′`
      : "άγνωστο";

  let distancePart = "άγνωστο";
  if (Number.isFinite(distanceM) && distanceM >= 0) {
    if (distanceM >= METERS_PER_KM) {
      distancePart = `${(distanceM / METERS_PER_KM).toFixed(1).replace(".", ",")} km`;
    } else {
      distancePart = `${Math.round(distanceM)} m`;
    }
  }

  const reasonTexts = Array.isArray(reasons)
    ? reasons
        .map((r) => (typeof r === "string" ? r.trim() : typeof r?.text === "string" ? r.text.trim() : ""))
        .filter(Boolean)
    : [];

  const base = `${durationPart} · ${distancePart}`;
  return reasonTexts.length > 0 ? `${base} · ${reasonTexts.join(", ")}` : base;
}

export function routeLabel(route) {
  if (!route || typeof route !== "object") {
    return formatRouteLabel(NaN, NaN, []);
  }
  return formatRouteLabel(route.distance_m, route.duration_s, route.reasons);
}

function toRouteFeature(routeOrGeojson) {
  if (!routeOrGeojson || typeof routeOrGeojson !== "object") {
    return null;
  }
  if (routeOrGeojson.type === "Feature" || routeOrGeojson.type === "FeatureCollection") {
    return routeOrGeojson;
  }
  const geometry =
    routeOrGeojson.type === "LineString" || routeOrGeojson.type === "MultiLineString"
      ? routeOrGeojson
      : routeOrGeojson.geometry;
  if (!geometry || typeof geometry !== "object") {
    return null;
  }
  return {
    type: "Feature",
    properties: {},
    geometry,
  };
}

function routeGlowLayerSpec(progress, palette = null) {
  return {
    id: ROUTE_GLOW_LAYER_ID,
    type: "line",
    source: ROUTE_SOURCE_ID,
    layout: {
      "line-cap": "round",
      "line-join": "round",
    },
    paint: {
      "line-width": ROUTE_LINE_WIDTH_PX + 10,
      "line-blur": 9,
      "line-opacity": 0.42,
      "line-gradient": gradientAt(progress, palette),
    },
  };
}

function routeLayerSpec(progress, palette = null) {
  return {
    id: ROUTE_LAYER_ID,
    type: "line",
    source: ROUTE_SOURCE_ID,
    layout: {
      "line-cap": "round",
      "line-join": "round",
    },
    paint: {
      "line-width": ROUTE_LINE_WIDTH_PX,
      "line-gradient": gradientAt(progress, palette),
    },
  };
}

function ensureRouteOverlayOnMap(map, geojson, progress, palette = null) {
  if (!map || !geojson) {
    return;
  }
  const existingSource = typeof map.getSource === "function" ? map.getSource(ROUTE_SOURCE_ID) : null;
  if (existingSource && typeof existingSource.setData === "function") {
    existingSource.setData(geojson);
  } else if (typeof map.addSource === "function") {
    map.addSource(ROUTE_SOURCE_ID, routeSource(geojson));
  }

  const hasGlowLayer = typeof map.getLayer === "function" ? Boolean(map.getLayer(ROUTE_GLOW_LAYER_ID)) : false;
  if (!hasGlowLayer && typeof map.addLayer === "function") {
    map.addLayer(routeGlowLayerSpec(progress, palette));
  } else if (hasGlowLayer && typeof map.setPaintProperty === "function") {
    map.setPaintProperty(ROUTE_GLOW_LAYER_ID, "line-gradient", gradientAt(progress, palette));
  }

  const hasLayer = typeof map.getLayer === "function" ? Boolean(map.getLayer(ROUTE_LAYER_ID)) : false;
  if (!hasLayer && typeof map.addLayer === "function") {
    map.addLayer(routeLayerSpec(progress, palette));
  } else if (hasLayer && typeof map.setPaintProperty === "function") {
    map.setPaintProperty(ROUTE_LAYER_ID, "line-gradient", gradientAt(progress, palette));
  }
}

function reapplyRouteOverlay(targetMap) {
  const routeState = routeStateByMap.get(targetMap);
  if (!routeState || !routeState.geojson) {
    return null;
  }
  ensureRouteOverlayOnMap(targetMap, routeState.geojson, routeState.progress, routeState.palette ?? null);
  return {
    id: ROUTE_SOURCE_ID,
    layerIds: [ROUTE_GLOW_LAYER_ID, ROUTE_LAYER_ID],
  };
}

function buildBaselineOverlayData(comparison) {
  const empty = { type: "FeatureCollection", features: [] };
  if (!comparison || comparison.same_as_baseline) {
    return { baselineFC: empty, avoidedFC: empty };
  }
  const baseGeom = comparison.baseline?.geometry;
  const baselineFC = baseGeom
    ? { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: baseGeom }] }
    : empty;

  const avoidedFeatures = [];
  for (const w of comparison.avoided_works ?? []) {
    if (Number.isFinite(Number(w?.lon)) && Number.isFinite(Number(w?.lat))) {
      avoidedFeatures.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: [Number(w.lon), Number(w.lat)] },
        properties: {
          kind: "work",
          badge: w.street ? `🚧 Αποφεύχθηκε: ${w.street}` : "🚧 Αποφεύχθηκε έργο",
        },
      });
    }
  }
  for (const r of comparison.avoided_reports ?? []) {
    if (Number.isFinite(Number(r?.lon)) && Number.isFinite(Number(r?.lat))) {
      const badge = r.category === "congestion" ? "🚗 Αποφεύχθηκε συμφόρηση" : "⛔ Αποφεύχθηκε εμπόδιο";
      avoidedFeatures.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: [Number(r.lon), Number(r.lat)] },
        properties: { kind: "report", badge },
      });
    }
  }
  return {
    baselineFC,
    avoidedFC: { type: "FeatureCollection", features: avoidedFeatures },
  };
}

function ensureBaselineAndAvoidedOnMap(map, comparison) {
  if (!map) return;
  const { baselineFC, avoidedFC } = buildBaselineOverlayData(comparison);

  const baseSrc = typeof map.getSource === "function" ? map.getSource(ROUTE_BASELINE_SOURCE_ID) : null;
  if (baseSrc && typeof baseSrc.setData === "function") {
    baseSrc.setData(baselineFC);
  } else if (typeof map.addSource === "function") {
    map.addSource(ROUTE_BASELINE_SOURCE_ID, { type: "geojson", data: baselineFC });
  }

  const hasBaseLayer =
    typeof map.getLayer === "function" ? Boolean(map.getLayer(ROUTE_BASELINE_LAYER_ID)) : false;
  if (!hasBaseLayer && typeof map.addLayer === "function") {
    const beforeId =
      typeof map.getLayer === "function" && map.getLayer(ROUTE_GLOW_LAYER_ID)
        ? ROUTE_GLOW_LAYER_ID
        : undefined;
    const spec = {
      id: ROUTE_BASELINE_LAYER_ID,
      type: "line",
      source: ROUTE_BASELINE_SOURCE_ID,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#94a3b8",
        "line-width": 4,
        "line-opacity": 0.72,
        "line-dasharray": [2.2, 2.2],
      },
    };
    if (beforeId) map.addLayer(spec, beforeId);
    else map.addLayer(spec);
  }

  const avSrc = typeof map.getSource === "function" ? map.getSource(ROUTE_AVOIDED_SOURCE_ID) : null;
  if (avSrc && typeof avSrc.setData === "function") {
    avSrc.setData(avoidedFC);
  } else if (typeof map.addSource === "function") {
    map.addSource(ROUTE_AVOIDED_SOURCE_ID, { type: "geojson", data: avoidedFC });
  }

  const hasAvPins =
    typeof map.getLayer === "function" ? Boolean(map.getLayer(ROUTE_AVOIDED_LAYER_ID)) : false;
  if (!hasAvPins && typeof map.addLayer === "function") {
    map.addLayer({
      id: ROUTE_AVOIDED_LAYER_ID,
      type: "circle",
      source: ROUTE_AVOIDED_SOURCE_ID,
      paint: {
        "circle-radius": 9,
        "circle-color": "#ef4444",
        "circle-opacity": 0.9,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2.5,
      },
    });
  }

  const hasAvLabels =
    typeof map.getLayer === "function" ? Boolean(map.getLayer(ROUTE_AVOIDED_LABEL_LAYER_ID)) : false;
  if (!hasAvLabels && typeof map.addLayer === "function") {
    map.addLayer({
      id: ROUTE_AVOIDED_LABEL_LAYER_ID,
      type: "symbol",
      source: ROUTE_AVOIDED_SOURCE_ID,
      layout: {
        "text-field": ["get", "badge"],
        "text-size": 12,
        "text-offset": [0, -1.45],
        "text-anchor": "bottom",
        "text-allow-overlap": true,
      },
      paint: {
        "text-color": "#ffffff",
        "text-halo-color": "#0f172a",
        "text-halo-width": 2,
      },
    });
  }
}

function reapplyBaselineOverlay(targetMap) {
  const cmp = baselineStateByMap.get(targetMap);
  if (!cmp) return null;
  ensureBaselineAndAvoidedOnMap(targetMap, cmp);
  return {
    id: ROUTE_BASELINE_SOURCE_ID,
    layerIds: [ROUTE_BASELINE_LAYER_ID, ROUTE_AVOIDED_LAYER_ID, ROUTE_AVOIDED_LABEL_LAYER_ID],
  };
}

// Pure route-comparison insight builder (Layer B: works with live backend `comparison` or graceful offline fallback).
export function buildRouteInsight(route, profile = "wheelchair") {
  const cmp = route?.comparison ?? null;
  const palette = paletteForProfile(profile);
  const reasons = Array.isArray(route?.reasons) ? route.reasons : [];

  const profileMeta =
    profile === "wheelchair"
      ? { icon: "♿", headline: "Γιατί για Αμαξίδιο" }
      : profile === "stroller"
        ? { icon: "🍼", headline: "Γιατί για Καρότσι" }
        : { icon: "🌳", headline: "Γιατί Δροσερότερη" };

  const avoidedItems = [];
  if (cmp) {
    for (const w of cmp.avoided_works ?? []) {
      avoidedItems.push({
        icon: "🚧",
        label: w.street ? `Αποφεύχθηκε: ${w.street}` : `Αποφεύχθηκε έργο ${w.id}`,
        lon: Number(w.lon),
        lat: Number(w.lat),
        kind: "work",
        ada: w.ada ?? null,
      });
    }
    for (const r of cmp.avoided_reports ?? []) {
      avoidedItems.push({
        icon: r.category === "congestion" ? "🚗" : "⛔",
        label: r.category === "congestion" ? "Αποφεύχθηκε συμφόρηση" : "Αποφεύχθηκε εμπόδιο",
        lon: Number(r.lon),
        lat: Number(r.lat),
        kind: "report",
        ada: null,
      });
    }
  }

  let detourText = "Βέλτιστη επιλογή";
  const showGhostLegend = Boolean(cmp && !cmp.same_as_baseline && cmp.baseline?.geometry);
  if (cmp) {
    if (cmp.same_as_baseline) {
      detourText = "Ίδια με τη συντομότερη ✓";
    } else {
      const dMin = Math.round((cmp.deltas?.duration_s ?? 0) / 60);
      const dM = Math.round(cmp.deltas?.distance_m ?? 0);
      const parts = [];
      if (dMin > 0) parts.push(`+${dMin}′`);
      else if (dMin < 0) parts.push(`${dMin}′`);
      if (dM > 0) parts.push(`+${dM} m`);
      else if (dM < 0) parts.push(`${dM} m`);
      detourText = parts.length > 0 ? `${parts.join(" · ")} vs συντομότερη` : "Ίδιος χρόνος ✓";
    }
  }

  const metrics = [];
  if (cmp) {
    const bestM = cmp.best || {};
    const baseM = cmp.baseline || null;
    const deltas = cmp.deltas || {};
    const envInfo = cmp.env || {};
    const avoidedCount = avoidedItems.length;
    const onRouteCount = (cmp.on_route_works ?? 0) + (cmp.on_route_reports ?? 0);

    if (profile === "wheelchair") {
      metrics.push({
        label: "Έργα & Εμπόδια",
        value: avoidedCount > 0 ? `Αποφυγή ${avoidedCount}` : onRouteCount === 0 ? "0 εμπόδια" : `${onRouteCount} κοντά`,
        delta: avoidedCount > 0 ? "εκτός διαδρομής ✓" : onRouteCount === 0 ? "καθαρή όδευση ✓" : "προσοχή",
        tone: onRouteCount === 0 ? "good" : "warn",
      });
      metrics.push({
        label: "Προσβασιμότητα",
        value: "Χωρίς σκαλιά",
        delta: "προφίλ αμαξιδίου",
        tone: "good",
      });
      metrics.push({
        label: "Σκιά / Κίνηση",
        value: `${bestM.shade_pct ?? 0}% σκιά`,
        delta: `${bestM.busy_pct ?? 0}% κεντρικοί`,
        tone: (bestM.busy_pct ?? 100) <= 30 ? "good" : "neutral",
      });
    } else if (profile === "stroller") {
      const busyDelta = !cmp.same_as_baseline && baseM && deltas.busy_pct < 0
        ? `${deltas.busy_pct}% vs ${baseM.busy_pct}%`
        : "ήπιοι δρόμοι";
      metrics.push({
        label: "Έντονη κίνηση",
        value: `${bestM.busy_pct ?? 0}%`,
        delta: busyDelta,
        tone: (deltas.busy_pct ?? 0) < 0 || (bestM.busy_pct ?? 100) <= 30 ? "good" : "neutral",
      });
      metrics.push({
        label: "Έργα & Συμφόρηση",
        value: avoidedCount > 0 ? `Αποφυγή ${avoidedCount}` : onRouteCount === 0 ? "Καθαρή" : `${onRouteCount} σημεία`,
        delta: avoidedCount > 0 ? "παράκαμψη ✓" : "χωρίς εμπόδια",
        tone: onRouteCount === 0 ? "good" : "warn",
      });
      if (envInfo.aqi !== null && envInfo.aqi !== undefined) {
        metrics.push({
          label: "Ποιότητα αέρα",
          value: `AQI ${envInfo.aqi}`,
          delta: envInfo.temp_c != null ? `${envInfo.temp_c}°C` : "σταθμός Αθήνας",
          tone: Number(envInfo.aqi) <= 40 ? "good" : "neutral",
        });
      } else {
        metrics.push({
          label: "Κάλυψη σκιάς",
          value: `${bestM.shade_pct ?? 0}%`,
          delta: "πεζόδρομοι & δέντρα",
          tone: (bestM.shade_pct ?? 0) >= 40 ? "good" : "neutral",
        });
      }
    } else {
      // cool profile
      const shadeDelta = !cmp.same_as_baseline && baseM && deltas.shade_pct > 0
        ? `+${deltas.shade_pct}% vs ${baseM.shade_pct}%`
        : "δέντρα & πάρκα";
      metrics.push({
        label: "Κάλυψη σκιάς",
        value: `${bestM.shade_pct ?? 0}%`,
        delta: shadeDelta,
        tone: (deltas.shade_pct ?? 0) > 0 || (bestM.shade_pct ?? 0) >= 40 ? "good" : "neutral",
      });
      const busyDelta = !cmp.same_as_baseline && baseM && deltas.busy_pct < 0
        ? `${deltas.busy_pct}% vs ${baseM.busy_pct}%`
        : "χαμηλά καυσαέρια";
      metrics.push({
        label: "Δρόμοι κίνησης",
        value: `${bestM.busy_pct ?? 0}%`,
        delta: busyDelta,
        tone: (deltas.busy_pct ?? 0) < 0 || (bestM.busy_pct ?? 100) <= 30 ? "good" : "neutral",
      });
      if (envInfo.temp_c !== null && envInfo.temp_c !== undefined) {
        metrics.push({
          label: "Μικροκλίμα",
          value: `${envInfo.temp_c}°C`,
          delta: envInfo.uv_index != null ? `UV ${envInfo.uv_index}` : envInfo.aqi != null ? `AQI ${envInfo.aqi}` : "Αθήνα",
          tone: "neutral",
        });
      } else if (envInfo.aqi !== null && envInfo.aqi !== undefined) {
        metrics.push({
          label: "Ποιότητα αέρα",
          value: `AQI ${envInfo.aqi}`,
          delta: "καθαρότερη όδευση",
          tone: Number(envInfo.aqi) <= 40 ? "good" : "neutral",
        });
      } else {
        metrics.push({
          label: "Θερμική άνεση",
          value: "Δροσερή",
          delta: "υπολογισμός σκιάς",
          tone: "good",
        });
      }
    }
    if (profile === "car" && route?.traffic) {
      const lvl = route.traffic.level;
      const lvlText = lvl === "heavy" ? "Αυξημένη" : lvl === "moderate" ? "Μέτρια" : "Χαμηλή";
      const delay = Number(route.traffic.delay_min || 0);
      metrics.push({
        label: "Κίνηση",
        value: lvlText,
        delta: delay > 0 ? `+${delay}' καθυστέρηση` : "ομαλή ροή",
        tone: lvl === "heavy" ? "warn" : lvl === "moderate" ? "neutral" : "good",
      });
    }
  } else {
    // Graceful offline / mock fallback (never invents numbers)
    metrics.push({
      label: "Προφίλ",
      value: ALL_PROFILES.find((p) => p.id === profile)?.label ?? profile,
      delta: reasons.length > 0 ? `${reasons.length} κριτήρια` : "εκτός σύνδεσης",
      tone: "neutral",
    });
    metrics.push({
      label: "Αιτιολόγηση",
      value: reasons.length > 0 ? "Ενεργή" : "Ευθεία γραμμή",
      delta: reasons[0]?.text ?? "χωρίς ζωντανά εμπόδια",
      tone: reasons.length > 0 ? "good" : "neutral",
    });
  }

  return {
    icon: profileMeta.icon,
    headline: profileMeta.headline,
    accent: palette.accent,
    detourText,
    showGhostLegend,
    metrics,
    avoidedItems,
  };
}

// ---------- Turn-by-turn geometry & GPS puck helpers (UI/UX upgrade #6) ----------

const navGpsStateByMap = new WeakMap();

function haversineMeters([lon1, lat1], [lon2, lat2]) {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.min(1, Math.sqrt(a)));
}

export function computeBearing([lon1, lat1], [lon2, lat2]) {
  const rad = Math.PI / 180;
  const dLon = (lon2 - lon1) * rad;
  const y = Math.sin(dLon) * Math.cos(lat2 * rad);
  const x =
    Math.cos(lat1 * rad) * Math.sin(lat2 * rad) -
    Math.sin(lat1 * rad) * Math.cos(lat2 * rad) * Math.cos(dLon);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

function classifyTurn(prevBearing, nextBearing) {
  let delta = ((nextBearing - prevBearing + 540) % 360) - 180;
  if (delta > 30) return { icon: "↱", text: "Στρίψτε δεξιά" };
  if (delta < -30) return { icon: "↰", text: "Στρίψτε αριστερά" };
  return { icon: "⬆️", text: "Συνεχίστε ευθεία" };
}

export function sampleRouteAtDistance(coords, distanceM) {
  if (!Array.isArray(coords) || coords.length === 0) {
    return null;
  }
  if (coords.length === 1) {
    return {
      lon: coords[0][0],
      lat: coords[0][1],
      bearing: 0,
      remainingM: 0,
      distToTurnM: 0,
      turn: { icon: "🏁", text: "Φτάσατε στον προορισμό" },
      arrived: true,
    };
  }

  const segLens = [];
  let totalM = 0;
  for (let i = 0; i < coords.length - 1; i += 1) {
    const len = haversineMeters(coords[i], coords[i + 1]);
    segLens.push(len);
    totalM += len;
  }

  const clamped = Math.max(0, Math.min(totalM, distanceM));
  if (totalM === 0 || clamped >= totalM - 1) {
    const last = coords[coords.length - 1];
    const prev = coords[coords.length - 2];
    return {
      lon: last[0],
      lat: last[1],
      bearing: computeBearing(prev, last),
      remainingM: 0,
      distToTurnM: 0,
      turn: { icon: "🏁", text: "Φτάσατε στον προορισμό" },
      arrived: true,
    };
  }

  let acc = 0;
  let segIdx = 0;
  for (let i = 0; i < segLens.length; i += 1) {
    if (acc + segLens[i] >= clamped) {
      segIdx = i;
      break;
    }
    acc += segLens[i];
  }

  const segLen = segLens[segIdx] || 1;
  const t = Math.max(0, Math.min(1, (clamped - acc) / segLen));
  const p0 = coords[segIdx];
  const p1 = coords[segIdx + 1];
  const lon = p0[0] + (p1[0] - p0[0]) * t;
  const lat = p0[1] + (p1[1] - p0[1]) * t;
  const bearing = computeBearing(p0, p1);
  const remainingM = Math.max(0, totalM - clamped);

  // Look ahead for the next noticeable turn along the polyline.
  let distToTurnM = segLen * (1 - t);
  let turn = { icon: "🏁", text: "Προορισμός ευθεία" };
  let prevB = bearing;
  for (let j = segIdx + 1; j < coords.length - 1; j += 1) {
    const nextB = computeBearing(coords[j], coords[j + 1]);
    const candidate = classifyTurn(prevB, nextB);
    if (candidate.icon !== "⬆️") {
      turn = candidate;
      break;
    }
    distToTurnM += segLens[j];
    prevB = nextB;
  }

  return {
    lon,
    lat,
    bearing,
    remainingM,
    distToTurnM: Math.round(distToTurnM),
    turn,
    arrived: false,
  };
}

function ensureNavGpsOnMap(map, gpsPoint) {
  if (!map || !gpsPoint) {
    return;
  }
  const fc = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { bearing: gpsPoint.bearing ?? 0 },
        geometry: { type: "Point", coordinates: [gpsPoint.lon, gpsPoint.lat] },
      },
    ],
  };

  const existingSrc = typeof map.getSource === "function" ? map.getSource(NAV_GPS_SOURCE_ID) : null;
  if (existingSrc && typeof existingSrc.setData === "function") {
    existingSrc.setData(fc);
  } else if (typeof map.addSource === "function") {
    map.addSource(NAV_GPS_SOURCE_ID, { type: "geojson", data: fc });
  }

  if (typeof map.getLayer === "function" && !map.getLayer(NAV_GPS_HALO_LAYER_ID) && typeof map.addLayer === "function") {
    map.addLayer({
      id: NAV_GPS_HALO_LAYER_ID,
      type: "circle",
      source: NAV_GPS_SOURCE_ID,
      paint: {
        "circle-radius": 22,
        "circle-color": "#38bdf8",
        "circle-opacity": 0.28,
        "circle-blur": 0.5,
      },
    });
  }

  if (typeof map.getLayer === "function" && !map.getLayer(NAV_GPS_PUCK_LAYER_ID) && typeof map.addLayer === "function") {
    map.addLayer({
      id: NAV_GPS_PUCK_LAYER_ID,
      type: "circle",
      source: NAV_GPS_SOURCE_ID,
      paint: {
        "circle-radius": 9,
        "circle-color": "#2563eb",
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 3,
      },
    });
  }
}

function reapplyNavGpsOverlay(targetMap) {
  const gps = navGpsStateByMap.get(targetMap);
  if (!gps) return null;
  ensureNavGpsOnMap(targetMap, gps);
  return { id: NAV_GPS_SOURCE_ID, layerIds: [NAV_GPS_HALO_LAYER_ID, NAV_GPS_PUCK_LAYER_ID] };
}

function clearNavGpsFromMap(map) {
  if (!map) return;
  navGpsStateByMap.delete(map);
  const src = typeof map.getSource === "function" ? map.getSource(NAV_GPS_SOURCE_ID) : null;
  if (src && typeof src.setData === "function") {
    src.setData({ type: "FeatureCollection", features: [] });
  }
}

function readEnvBadgesNear(map, lon, lat, route) {
  let shadeText = null;
  if (Array.isArray(route?.reasons)) {
    for (const r of route.reasons) {
      const txt = typeof r === "string" ? r : r?.text ?? "";
      const m = txt.match(/(\d+\s*%[^,]*|−?\d+\s*°C[^,]*)/i);
      if (m) {
        shadeText = m[1].trim();
        break;
      }
    }
  }
  let aqiText = "AQI άγνωστο";
  const envSrc = typeof map?.getSource === "function" ? map.getSource("env-source") : null;
  const feats = extractFeaturesList(envSrc?.data ?? envSrc?._data);
  if (feats.length > 0 && Number.isFinite(lon) && Number.isFinite(lat)) {
    let best = null;
    let bestDist = Infinity;
    for (const f of feats) {
      const c = f?.geometry?.coordinates;
      if (!Array.isArray(c) || c.length < 2) continue;
      const d = haversineMeters([lon, lat], c);
      if (d < bestDist) {
        bestDist = d;
        best = f.properties;
      }
    }
    if (best) {
      if (Number.isFinite(Number(best.aqi))) {
        aqiText = `AQI ${best.aqi}`;
      } else if (Number.isFinite(Number(best.pm25))) {
        aqiText = `PM2.5 ${Math.round(Number(best.pm25))}`;
      }
    }
  }
  return {
    shadeBadge: shadeText ? `🌳 ${shadeText}` : "🌳 Προφίλ διαδρομής",
    aqiBadge: `🍃 ${aqiText}`,
  };
}

function getFeatureIdentifier(feature) {
  if (!feature || typeof feature !== "object") {
    return null;
  }
  const raw = feature.properties?.id ?? feature.id;
  return raw !== undefined && raw !== null && raw !== "" ? String(raw) : null;
}

function extractFeaturesList(collectionOrList) {
  if (!collectionOrList) {
    return [];
  }
  if (Array.isArray(collectionOrList)) {
    return collectionOrList;
  }
  if (collectionOrList.type === "FeatureCollection" && Array.isArray(collectionOrList.features)) {
    return collectionOrList.features;
  }
  if (collectionOrList.data?.type === "FeatureCollection" && Array.isArray(collectionOrList.data.features)) {
    return collectionOrList.data.features;
  }
  return [];
}

function lookupReasonFeature(map, layerName, featureId, lookup) {
  const targetId = String(featureId);

  if (typeof lookup === "function") {
    return lookup(layerName, featureId) ?? null;
  }

  if (lookup && typeof lookup === "object") {
    const entry =
      lookup instanceof Map
        ? lookup.get(layerName)
        : Object.hasOwn(lookup, layerName)
          ? lookup[layerName]
          : null;
    const features = extractFeaturesList(entry);
    const matched = features.find((f) => getFeatureIdentifier(f) === targetId);
    if (matched) {
      return matched;
    }
    if (Array.isArray(lookup) || lookup.type === "FeatureCollection") {
      const fromFlat = extractFeaturesList(lookup).find((f) => getFeatureIdentifier(f) === targetId);
      if (fromFlat) {
        return fromFlat;
      }
    }
  }

  if (map && typeof map.getSource === "function") {
    const sourceIds = LAYER_SOURCE_IDS[layerName] ?? [`${layerName}-source`, layerName];
    for (const sourceId of sourceIds) {
      const src = map.getSource(sourceId);
      const data = src?.data ?? src?._data;
      const matched = extractFeaturesList(data).find((f) => getFeatureIdentifier(f) === targetId);
      if (matched) {
        return matched;
      }
    }
  }

  return null;
}

function ensureReasonsHighlightOnMap(map, featureCollection) {
  if (!map) {
    return;
  }
  const existingSource =
    typeof map.getSource === "function" ? map.getSource(REASONS_HIGHLIGHT_SOURCE_ID) : null;
  if (existingSource && typeof existingSource.setData === "function") {
    existingSource.setData(featureCollection);
  } else if (typeof map.addSource === "function") {
    map.addSource(REASONS_HIGHLIGHT_SOURCE_ID, {
      type: "geojson",
      data: featureCollection,
    });
  }

  const hasLineLayer =
    typeof map.getLayer === "function" ? Boolean(map.getLayer(REASONS_HIGHLIGHT_LAYER_ID)) : false;
  if (!hasLineLayer && typeof map.addLayer === "function") {
    map.addLayer({
      id: REASONS_HIGHLIGHT_LAYER_ID,
      type: "line",
      source: REASONS_HIGHLIGHT_SOURCE_ID,
      layout: {
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": REASONS_HIGHLIGHT_COLOR,
        "line-width": REASONS_HIGHLIGHT_LINE_WIDTH_PX,
        "line-blur": REASONS_HIGHLIGHT_LINE_BLUR_PX,
        "line-opacity": 0.85,
      },
    });
  }

  const hasPointLayer =
    typeof map.getLayer === "function"
      ? Boolean(map.getLayer(REASONS_HIGHLIGHT_POINTS_LAYER_ID))
      : false;
  if (!hasPointLayer && typeof map.addLayer === "function") {
    map.addLayer({
      id: REASONS_HIGHLIGHT_POINTS_LAYER_ID,
      type: "circle",
      source: REASONS_HIGHLIGHT_SOURCE_ID,
      filter: ["in", ["geometry-type"], ["literal", ["Point", "MultiPoint"]]],
      paint: {
        "circle-radius": REASONS_HIGHLIGHT_POINT_RADIUS_PX,
        "circle-color": REASONS_HIGHLIGHT_COLOR,
        "circle-opacity": 0.45,
        "circle-stroke-color": REASONS_HIGHLIGHT_STROKE,
        "circle-stroke-width": 3,
      },
    });
  }
}

function reapplyReasonsHighlight(targetMap) {
  const fc = reasonsHighlightByMap.get(targetMap);
  if (!fc) {
    return null;
  }
  ensureReasonsHighlightOnMap(targetMap, fc);
  return {
    id: REASONS_HIGHLIGHT_SOURCE_ID,
    layerIds: [REASONS_HIGHLIGHT_LAYER_ID, REASONS_HIGHLIGHT_POINTS_LAYER_ID],
  };
}

// Highlight features referenced by route reasons on a dedicated map layer, clearing when reasons is empty (TASKS_A.md A5).
export function highlightReasons(map, reasons = [], lookup = null) {
  if (!map || typeof map !== "object") {
    return null;
  }

  const matchedFeatures = [];
  const seenKeys = new Set();

  if (Array.isArray(reasons)) {
    for (const reason of reasons) {
      if (!reason || typeof reason !== "object") {
        continue;
      }
      const layerName = typeof reason.layer === "string" ? reason.layer.trim() : "";
      const featureId = reason.feature_id;
      if (!layerName || featureId === undefined || featureId === null || featureId === "") {
        continue;
      }
      const dedupeKey = `${layerName}:${String(featureId)}`;
      if (seenKeys.has(dedupeKey)) {
        continue;
      }
      const feature = lookupReasonFeature(map, layerName, featureId, lookup);
      if (feature) {
        seenKeys.add(dedupeKey);
        matchedFeatures.push(feature);
      }
    }
  }

  const featureCollection = {
    type: "FeatureCollection",
    features: matchedFeatures,
  };

  reasonsHighlightByMap.set(map, featureCollection);
  registerOverlay(reapplyReasonsHighlight);
  ensureReasonsHighlightOnMap(map, featureCollection);
  return featureCollection;
}

export function initRouting(container, map, api, options = {}) {
  const doc = container?.ownerDocument ?? (typeof globalThis.document !== "undefined" ? globalThis.document : null);
  if (!container || !doc) {
    return null;
  }

  let activeProfile = loadSavedProfile();
  let collapsed =
    typeof options?.initialCollapsed === "boolean" ? options.initialCollapsed : true;
  let pickMode = null;
  let cancelAnimation = null;
  let lastRoute = null;
  let routeRequestSeq = 0;
  const coords = { from: null, to: null };

  const mapState = {
    geojson: null,
    progress: 1,
  };
  if (map && typeof map === "object") {
    routeStateByMap.set(map, mapState);
    registerOverlay(reapplyRouteOverlay);
  }

  const drawer = doc.createElement("section");
  drawer.className = "routing-drawer glass";
  drawer.setAttribute("aria-label", "Σχεδιασμός διαδρομής");

  const handleBtn = doc.createElement("button");
  handleBtn.type = "button";
  handleBtn.className = "routing-handle";
  handleBtn.setAttribute("aria-expanded", "true");
  handleBtn.setAttribute("aria-controls", "routing-body");
  handleBtn.setAttribute("aria-label", "Άνοιγμα ή κλείσιμο διαδρομών");

  const handleBar = doc.createElement("span");
  handleBar.className = "routing-handle-bar";
  handleBar.setAttribute("aria-hidden", "true");
  handleBtn.appendChild(handleBar);
  drawer.appendChild(handleBtn);

  const body = doc.createElement("div");
  body.id = "routing-body";
  body.className = "routing-body";
  drawer.appendChild(body);

  const drawerHeader = doc.createElement("div");
  drawerHeader.className = "workstab-header";
  const drawerTitle = doc.createElement("strong");
  drawerTitle.textContent = "Διαδρομή";
  const drawerCloseBtn = doc.createElement("button");
  drawerCloseBtn.type = "button";
  drawerCloseBtn.className = "overlay-close-btn";
  drawerCloseBtn.setAttribute("aria-label", "Κλείσιμο διαδρομής");
  drawerCloseBtn.textContent = "×";
  drawerCloseBtn.addEventListener("click", () => setCollapsed(true));
  drawerHeader.appendChild(drawerTitle);
  drawerHeader.appendChild(drawerCloseBtn);
  body.appendChild(drawerHeader);

  const form = doc.createElement("form");
  form.className = "routing-form";
  body.appendChild(form);

  function createPointField(kind, labelText, placeholderText) {
    const row = doc.createElement("div");
    row.className = "routing-field";

    const label = doc.createElement("label");
    label.className = "routing-label";
    const inputId = `routing-${kind}`;
    label.setAttribute("for", inputId);
    label.textContent = labelText;

    const inputWrap = doc.createElement("div");
    inputWrap.className = "routing-input-row";

    const input = doc.createElement("input");
    input.id = inputId;
    input.type = "text";
    input.className = "routing-input";
    input.setAttribute("placeholder", placeholderText);
    input.setAttribute("autocomplete", "off");
    input.addEventListener("input", () => {
      coords[kind] = null;
    });

    const pickBtn = doc.createElement("button");
    pickBtn.type = "button";
    pickBtn.className = "routing-pick-btn";
    pickBtn.setAttribute("data-pick", kind);
    pickBtn.setAttribute("aria-pressed", "false");
    pickBtn.setAttribute(
      "aria-label",
      kind === "from" ? "Επιλογή εκκίνησης στον χάρτη" : "Επιλογή προορισμού στον χάρτη",
    );
    pickBtn.textContent = "Χάρτης";

    inputWrap.appendChild(input);
    if (kind === "from" && typeof globalThis.navigator?.geolocation?.getCurrentPosition === "function") {
      const gpsBtn = doc.createElement("button");
      gpsBtn.type = "button";
      gpsBtn.className = "routing-pick-btn";
      gpsBtn.setAttribute("aria-label", "Χρήση τρέχουσας θέσης GPS");
      gpsBtn.textContent = "Θέση";
      gpsBtn.addEventListener("click", () => {
        gpsBtn.disabled = true;
        globalThis.navigator.geolocation.getCurrentPosition(
          (pos) => {
            gpsBtn.disabled = false;
            const pt = [Number(pos.coords.longitude.toFixed(5)), Number(pos.coords.latitude.toFixed(5))];
            coords.from = pt;
            input.value = `GPS (${pt[1]}, ${pt[0]})`;
          },
          () => {
            gpsBtn.disabled = false;
          },
          { enableHighAccuracy: true, timeout: 8000 },
        );
      });
      inputWrap.appendChild(gpsBtn);
    }
    inputWrap.appendChild(pickBtn);
    row.appendChild(label);
    row.appendChild(inputWrap);
    form.appendChild(row);

    return { input, pickBtn };
  }

  const placesList = doc.createElement("datalist");
  placesList.id = "routing-places";
  for (const placeName of ["Σύνταγμα", "Κυψέλη", "Πετράλωνα", "Αμπελόκηποι", "Παγκράτι", "Νέος Κόσμος", "Πατήσια", "Εξάρχεια", "Γκάζι", "Μοναστηράκι", "Ακρόπολη", "Σεράφειο"]) {
    const opt = doc.createElement("option");
    opt.value = placeName;
    placesList.appendChild(opt);
  }
  form.appendChild(placesList);

  const fromField = createPointField("from", "Από", "Σύνταγμα ή lat, lon");
  fromField.input.setAttribute("list", "routing-places");
  const toField = createPointField("to", "Προς", "Κυψέλη, Πετράλωνα ή lat, lon");
  toField.input.setAttribute("list", "routing-places");

  const profilesGroup = doc.createElement("div");
  profilesGroup.className = "routing-profiles";
  profilesGroup.setAttribute("role", "group");
  profilesGroup.setAttribute("aria-label", "Προφίλ διαδρομής");

  const profileButtons = new Map();

  function updateProfileButtons() {
    for (const [id, btn] of profileButtons.entries()) {
      const selected = id === activeProfile;
      btn.setAttribute("aria-pressed", String(selected));
      btn.classList.toggle("is-active", selected);
    }
  }

  for (const profile of ALL_PROFILES) {
    const btn = doc.createElement("button");
    btn.type = "button";
    btn.className = "routing-profile-btn";
    btn.setAttribute("data-profile", profile.id);
    btn.setAttribute("aria-pressed", String(profile.id === activeProfile));
    btn.textContent = profile.id === "car" ? `🚗 ${profile.label}` : profile.label;
    btn.addEventListener("click", () => {
      activeProfile = profile.id;
      saveProfile(activeProfile);
      updateProfileButtons();
      if (lastRoute && api && typeof api.routing === "function") {
        requestRoute();
      }
    });
    profileButtons.set(profile.id, btn);
    profilesGroup.appendChild(btn);
  }
  updateProfileButtons();
  form.appendChild(profilesGroup);

  const actionsRow = doc.createElement("div");
  actionsRow.className = "routing-actions";

  const routeBtn = doc.createElement("button");
  routeBtn.type = "button";
  routeBtn.className = "routing-submit-btn";
  routeBtn.textContent = "Υπολογισμός διαδρομής";
  routeBtn.addEventListener("click", () => {
    requestRoute();
  });
  actionsRow.appendChild(routeBtn);

  // Start Navigation CTA revealed once a route is ready (UI/UX upgrade #6).
  const startNavBtn = doc.createElement("button");
  startNavBtn.type = "button";
  startNavBtn.className = "routing-nav-start-btn hidden";
  startNavBtn.textContent = "🧭 Έναρξη Πλοήγησης";
  actionsRow.appendChild(startNavBtn);
  form.appendChild(actionsRow);

  const summaryEl = doc.createElement("div");
  summaryEl.className = "routing-summary";
  summaryEl.setAttribute("role", "status");
  summaryEl.setAttribute("aria-live", "polite");
  drawer.appendChild(summaryEl);

  // Layer B + C: "Γιατί αυτή η διαδρομή;" Comparison Scoreboard + Interactive Fly-To Chips + Stoa AI Button.
  const whyEl = doc.createElement("div");
  whyEl.className = "routing-why hidden";
  whyEl.setAttribute("aria-label", "Ανάλυση διαδρομής");
  drawer.appendChild(whyEl);

  function renderWhyCard(route) {
    if (!route || !whyEl) {
      whyEl?.classList?.add("hidden");
      return;
    }
    const insight = buildRouteInsight(route, activeProfile);
    if (whyEl.style && typeof whyEl.style.setProperty === "function") {
      whyEl.style.setProperty("--route-accent", insight.accent);
    }

    const header = doc.createElement("div");
    header.className = "routing-why__header";
    const titleEl = doc.createElement("span");
    titleEl.className = "routing-why__title";
    titleEl.textContent = `${insight.icon} ${insight.headline}`;
    const detourEl = doc.createElement("span");
    detourEl.className = "routing-why__detour";
    detourEl.textContent = insight.detourText;
    header.appendChild(titleEl);
    header.appendChild(detourEl);

    const grid = doc.createElement("div");
    grid.className = "routing-why__grid";
    for (const m of insight.metrics) {
      const tile = doc.createElement("div");
      tile.className = `routing-why__tile${m.tone === "good" ? " is-good" : m.tone === "warn" ? " is-warn" : ""}`;
      const lbl = doc.createElement("span");
      lbl.className = "routing-why__tile-label";
      lbl.textContent = m.label;
      const val = doc.createElement("span");
      val.className = "routing-why__tile-val";
      val.textContent = m.value;
      const dlt = doc.createElement("span");
      dlt.className = "routing-why__tile-delta";
      dlt.textContent = m.delta;
      tile.appendChild(lbl);
      tile.appendChild(val);
      tile.appendChild(dlt);
      grid.appendChild(tile);
    }

    const nodes = [header, grid];

    if (insight.avoidedItems.length > 0) {
      const chipsWrap = doc.createElement("div");
      chipsWrap.className = "routing-why__chips";
      for (const item of insight.avoidedItems) {
        const chip = doc.createElement("button");
        chip.type = "button";
        chip.className = "routing-why__chip";
        chip.textContent = `${item.icon} ${item.label}`;
        chip.addEventListener("click", () => {
          if (Number.isFinite(item.lon) && Number.isFinite(item.lat)) {
            bus?.dispatchEvent(
              new CustomEvent("map:flyto", {
                detail: { lon: item.lon, lat: item.lat, label: item.label },
              }),
            );
          }
        });
        chipsWrap.appendChild(chip);
      }
      nodes.push(chipsWrap);
    }

    const footer = doc.createElement("div");
    footer.className = "routing-why__footer";
    if (insight.showGhostLegend) {
      const legend = doc.createElement("div");
      legend.className = "routing-why__legend";
      const solidItem = doc.createElement("span");
      solidItem.className = "routing-why__legend-item";
      const solidSwatch = doc.createElement("span");
      solidSwatch.className = "routing-why__swatch routing-why__swatch--solid";
      const solidLbl = doc.createElement("span");
      solidLbl.textContent = "Επιλεγμένη";
      solidItem.appendChild(solidSwatch);
      solidItem.appendChild(solidLbl);

      const ghostItem = doc.createElement("span");
      ghostItem.className = "routing-why__legend-item";
      const ghostSwatch = doc.createElement("span");
      ghostSwatch.className = "routing-why__swatch routing-why__swatch--ghost";
      const ghostLbl = doc.createElement("span");
      ghostLbl.textContent = "Συντομότερη";
      ghostItem.appendChild(ghostSwatch);
      ghostItem.appendChild(ghostLbl);

      legend.appendChild(solidItem);
      legend.appendChild(ghostItem);
      footer.appendChild(legend);
    }

    const aiBtn = doc.createElement("button");
    aiBtn.type = "button";
    aiBtn.className = "routing-why__ai-btn";
    aiBtn.textContent = "✨ Εξήγηση από Stoa AI";
    aiBtn.addEventListener("click", () => {
      const profileLabel = ALL_PROFILES.find((p) => p.id === activeProfile)?.label ?? activeProfile;
      bus?.dispatchEvent(
        new CustomEvent("stoa:analyze-route", {
          detail: {
            profile: activeProfile,
            profileLabel,
            fromLabel: fromField.input.value.trim() || "Αφετηρία",
            toLabel: toField.input.value.trim() || "Προορισμός",
            route,
            insight,
          },
        }),
      );
    });
    footer.appendChild(aiBtn);
    nodes.push(footer);

    if (typeof whyEl.replaceChildren === "function") {
      whyEl.replaceChildren(...nodes);
    } else {
      whyEl.textContent = "";
      for (const n of nodes) whyEl.appendChild(n);
    }
    whyEl.classList?.remove("hidden");
  }

  // ---------- Live GPS Turn-by-Turn Navigation + Simulate GPS + Instant Waze "⚡ Αναφορά εδώ" ----------
  let navActive = false;
  let navWatchId = null;
  let navSimRafId = null;
  let navSimRunning = false;
  let navSimDistM = 0;
  let navSimLastTs = null;
  let navCurrentPos = null;
  let navChevronMarker = null;
  let navChevronEl = null;
  let navHudEl = null;
  let navReportWrap = null;
  let navReportTray = null;
  let navQuickOpen = false;
  let navRouteCoords = [];
  let navTurnIconEl = null;
  let navTurnTextEl = null;
  let navMetaEl = null;
  let navShadeEl = null;
  let navAqiEl = null;
  let navSimBtn = null;

  function updateChevronMarker(lon, lat, bearing) {
    if (!map) return;
    navGpsStateByMap.set(map, { lon, lat, bearing });
    registerOverlay(reapplyNavGpsOverlay);
    ensureNavGpsOnMap(map, { lon, lat, bearing });

    const MarkerCtor = globalThis.maplibregl?.Marker;
    if (typeof MarkerCtor !== "function" || typeof doc.createElement !== "function") {
      return;
    }
    if (!navChevronMarker) {
      navChevronEl = doc.createElement("div");
      navChevronEl.className = "nav-gps-chevron";
      navChevronEl.setAttribute("aria-hidden", "true");
      navChevronMarker = new MarkerCtor({ element: navChevronEl, rotationAlignment: "map" })
        .setLngLat([lon, lat])
        .addTo(map);
    } else {
      navChevronMarker.setLngLat([lon, lat]);
    }
    if (navChevronEl?.style) {
      navChevronEl.style.setProperty("--nav-bearing", `${Math.round(bearing)}deg`);
    }
  }

  function updateNavHudReadout(sample) {
    if (!sample) return;
    navCurrentPos = { lng: sample.lon, lat: sample.lat, bearing: sample.bearing };
    updateChevronMarker(sample.lon, sample.lat, sample.bearing);

    if (navTurnIconEl) navTurnIconEl.textContent = sample.turn.icon;
    if (navTurnTextEl) {
      navTurnTextEl.textContent = sample.arrived
        ? sample.turn.text
        : `${sample.turn.text} σε ${sample.distToTurnM} m`;
    }
    if (navMetaEl) {
      const etaMin = Math.max(1, Math.round(sample.remainingM / WALK_SPEED_MPS / 60));
      const distStr =
        sample.remainingM >= 1000
          ? `${(sample.remainingM / 1000).toFixed(1).replace(".", ",")} km`
          : `${Math.round(sample.remainingM)} m`;
      navMetaEl.textContent = sample.arrived ? "Άφιξη" : `${etaMin}′ · ${distStr}`;
    }
    const badges = readEnvBadgesNear(map, sample.lon, sample.lat, lastRoute);
    if (navShadeEl) navShadeEl.textContent = badges.shadeBadge;
    if (navAqiEl) navAqiEl.textContent = badges.aqiBadge;

    if (map && typeof map.easeTo === "function") {
      map.easeTo({
        center: [sample.lon, sample.lat],
        pitch: NAV_FOLLOW_PITCH,
        zoom: NAV_FOLLOW_ZOOM,
        bearing: sample.bearing,
        duration: navSimRunning ? 180 : 450,
      });
    }
  }

  function stopSim() {
    navSimRunning = false;
    navSimLastTs = null;
    if (navSimRafId !== null && typeof globalThis.cancelAnimationFrame === "function") {
      globalThis.cancelAnimationFrame(navSimRafId);
      navSimRafId = null;
    }
    if (navSimBtn) {
      navSimBtn.setAttribute("aria-pressed", "false");
      navSimBtn.classList?.remove("is-active");
      navSimBtn.textContent = "▶ Προσομοίωση GPS";
    }
  }

  function startSim() {
    if (navRouteCoords.length < 2) return;
    if (navSimRunning) {
      stopSim();
      return;
    }
    navSimRunning = true;
    navSimLastTs = null;
    const totalSample = sampleRouteAtDistance(navRouteCoords, navSimDistM);
    if (totalSample?.arrived) {
      navSimDistM = 0;
    }
    if (navSimBtn) {
      navSimBtn.setAttribute("aria-pressed", "true");
      navSimBtn.classList?.add("is-active");
      navSimBtn.textContent = "⏸ Παύση GPS";
    }
    const raf = globalThis.requestAnimationFrame;
    if (typeof raf !== "function") return;

    function tick(ts) {
      if (!navSimRunning || !navActive) return;
      const now = typeof ts === "number" ? ts : Date.now();
      if (navSimLastTs === null) navSimLastTs = now;
      const dtSec = Math.min(0.15, Math.max(0, (now - navSimLastTs) / 1000));
      navSimLastTs = now;
      navSimDistM += NAV_SIM_SPEED_MPS * dtSec;
      const sample = sampleRouteAtDistance(navRouteCoords, navSimDistM);
      if (sample) {
        updateNavHudReadout(sample);
        if (sample.arrived) {
          stopSim();
          bus?.dispatchEvent(
            new CustomEvent("toast:show", { detail: { message: "🏁 Φτάσατε στον προορισμό σας!" } }),
          );
          return;
        }
      }
      navSimRafId = raf(tick);
    }
    navSimRafId = raf(tick);
  }

  function toggleQuickReportTray(open) {
    navQuickOpen = Boolean(open);
    if (navReportTray) {
      navReportTray.hidden = !navQuickOpen;
    }
    const trigger = navReportWrap?.querySelector?.(".nav-quick-report-btn");
    if (trigger) {
      trigger.setAttribute("aria-expanded", String(navQuickOpen));
    }
  }

  function ensureNavUiBuilt() {
    if (navHudEl) return;
    const hudHost =
      doc.querySelector?.(".hud") ?? container.parentNode ?? container;

    navHudEl = doc.createElement("div");
    navHudEl.id = "nav-hud";
    navHudEl.className = "glass nav-hud hidden";
    navHudEl.setAttribute("role", "region");
    navHudEl.setAttribute("aria-label", "Πλοήγηση στροφή προς στροφή");

    const topRow = doc.createElement("div");
    topRow.className = "nav-hud__primary";
    navTurnIconEl = doc.createElement("span");
    navTurnIconEl.className = "nav-hud__icon";
    navTurnIconEl.textContent = "⬆️";

    const infoCol = doc.createElement("div");
    infoCol.className = "nav-hud__info";
    navTurnTextEl = doc.createElement("div");
    navTurnTextEl.className = "nav-hud__instruction";
    navTurnTextEl.textContent = "Έτοιμο για πλοήγηση";
    navMetaEl = doc.createElement("div");
    navMetaEl.className = "nav-hud__meta";
    infoCol.appendChild(navTurnTextEl);
    infoCol.appendChild(navMetaEl);

    const endBtn = doc.createElement("button");
    endBtn.type = "button";
    endBtn.className = "nav-hud__end-btn";
    endBtn.textContent = "Τέλος";
    endBtn.addEventListener("click", () => stopNavigation());

    topRow.appendChild(navTurnIconEl);
    topRow.appendChild(infoCol);
    topRow.appendChild(endBtn);

    const bottomRow = doc.createElement("div");
    bottomRow.className = "nav-hud__secondary";
    navShadeEl = doc.createElement("span");
    navShadeEl.className = "nav-hud__badge";
    navAqiEl = doc.createElement("span");
    navAqiEl.className = "nav-hud__badge";
    navSimBtn = doc.createElement("button");
    navSimBtn.type = "button";
    navSimBtn.className = "nav-hud__sim-btn";
    navSimBtn.setAttribute("aria-pressed", "false");
    navSimBtn.textContent = "▶ Προσομοίωση GPS";
    navSimBtn.addEventListener("click", () => startSim());

    bottomRow.appendChild(navShadeEl);
    bottomRow.appendChild(navAqiEl);
    bottomRow.appendChild(navSimBtn);

    navHudEl.appendChild(topRow);
    navHudEl.appendChild(bottomRow);
    hudHost.appendChild(navHudEl);

    // Floating "⚡ Αναφορά εδώ" button + 1-tap Waze hazard pills during navigation.
    navReportWrap = doc.createElement("div");
    navReportWrap.className = "nav-quick-report hidden";

    navReportTray = doc.createElement("div");
    navReportTray.className = "glass nav-quick-report__tray";
    navReportTray.hidden = true;
    for (const h of QUICK_NAV_HAZARDS) {
      const pill = doc.createElement("button");
      pill.type = "button";
      pill.className = "nav-quick-report__pill";
      pill.setAttribute("data-quick-hazard", h.id);
      pill.textContent = `${h.icon} ${h.label}`;
      pill.addEventListener("click", () => {
        const pos = navCurrentPos || map?.getCenter?.();
        toggleQuickReportTray(false);
        bus?.dispatchEvent(
          new CustomEvent("report:quick", {
            detail: { category: h.category, note: h.note, lngLat: pos },
          }),
        );
      });
      navReportTray.appendChild(pill);
    }

    const reportHereBtn = doc.createElement("button");
    reportHereBtn.type = "button";
    reportHereBtn.className = "glass glass-pill nav-quick-report-btn";
    reportHereBtn.setAttribute("aria-expanded", "false");
    reportHereBtn.textContent = "⚡ Αναφορά εδώ";
    reportHereBtn.addEventListener("click", () => toggleQuickReportTray(!navQuickOpen));

    navReportWrap.appendChild(navReportTray);
    navReportWrap.appendChild(reportHereBtn);
    hudHost.appendChild(navReportWrap);
  }

  function startNavigation() {
    if (!lastRoute) return;
    const pts = [];
    collectCoords(lastRoute, pts);
    if (pts.length < 2) return;

    navRouteCoords = pts;
    navActive = true;
    navSimDistM = 0;
    ensureNavUiBuilt();
    setCollapsed(true);
    navHudEl?.classList?.remove("hidden");
    navReportWrap?.classList?.remove("hidden");
    toggleQuickReportTray(false);

    const initialSample = sampleRouteAtDistance(navRouteCoords, 0);
    if (initialSample) {
      updateNavHudReadout(initialSample);
    }

    // Start real GPS tracking if browser geolocation is available (graceful indoors).
    const geo = globalThis.navigator?.geolocation;
    if (geo && typeof geo.watchPosition === "function") {
      let prevGps = null;
      try {
        navWatchId = geo.watchPosition(
          (pos) => {
            if (!navActive || navSimRunning) return;
            const lon = pos.coords.longitude;
            const lat = pos.coords.latitude;
            let heading = Number.isFinite(pos.coords.heading) ? pos.coords.heading : null;
            if (heading === null && prevGps && haversineMeters(prevGps, [lon, lat]) > 2) {
              const dLon = ((lon - prevGps[0]) * Math.PI) / 180;
              const lat1 = (prevGps[1] * Math.PI) / 180;
              const lat2 = (lat * Math.PI) / 180;
              const y = Math.sin(dLon) * Math.cos(lat2);
              const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
              heading = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
            }
            if (heading === null) heading = navCurrentPos?.bearing ?? 0;
            prevGps = [lon, lat];

            // Snap to nearest route vertex to compute real remaining route distance & upcoming turn.
            let bestDistAlong = 0;
            let bestGap = Infinity;
            let cum = 0;
            for (let i = 0; i < navRouteCoords.length; i += 1) {
              if (i > 0) cum += haversineMeters(navRouteCoords[i - 1], navRouteCoords[i]);
              const d = haversineMeters([lon, lat], navRouteCoords[i]);
              if (d < bestGap) {
                bestGap = d;
                bestDistAlong = cum;
              }
            }
            const snapped = sampleRouteAtDistance(navRouteCoords, bestDistAlong);
            const destPt = navRouteCoords[navRouteCoords.length - 1];
            const remM = snapped ? snapped.remainingM : haversineMeters([lon, lat], destPt);
            updateNavHudReadout({
              lon,
              lat,
              bearing: heading,
              remainingM: remM,
              distToTurnM: snapped ? snapped.distToTurnM : Math.round(Math.min(remM, 80)),
              turn: remM < 18
                ? { icon: "🏁", text: "Φτάσατε στον προορισμό" }
                : (snapped?.turn || { icon: "⬆️", text: "Ακολουθήστε τη διαδρομή" }),
              arrived: remM < 18,
            });
          },
          () => {
            // Indoors / denied GPS: user can tap "Προσομοίωση GPS" immediately.
          },
          { enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 },
        );
      } catch {
        navWatchId = null;
      }
    }
  }

  function stopNavigation() {
    navActive = false;
    stopSim();
    if (navWatchId !== null && typeof globalThis.navigator?.geolocation?.clearWatch === "function") {
      try {
        globalThis.navigator.geolocation.clearWatch(navWatchId);
      } catch {
        // ignore
      }
      navWatchId = null;
    }
    if (navChevronMarker && typeof navChevronMarker.remove === "function") {
      navChevronMarker.remove();
      navChevronMarker = null;
      navChevronEl = null;
    }
    clearNavGpsFromMap(map);
    toggleQuickReportTray(false);
    navHudEl?.classList?.add("hidden");
    navReportWrap?.classList?.add("hidden");
    if (map && typeof map.easeTo === "function") {
      map.easeTo({ pitch: 55, bearing: -15, zoom: 15.5, duration: 600 });
    }
  }

  startNavBtn.addEventListener("click", () => startNavigation());

  function setCollapsed(nextCollapsed) {
    collapsed = Boolean(nextCollapsed);
    drawer.classList.toggle("is-collapsed", collapsed);
    container.classList?.toggle?.("is-routing-expanded", !collapsed);
    handleBtn.setAttribute("aria-expanded", String(!collapsed));
  }
  setCollapsed(collapsed);

  // Optional vertical pointer drag gesture on the drawer handle (ignored safely in minimal fake DOMs).
  let dragStartY = null;
  let dragMoved = false;
  handleBtn.addEventListener("pointerdown", (e) => {
    if (typeof e?.clientY !== "number") return;
    dragStartY = e.clientY;
    dragMoved = false;
  });
  handleBtn.addEventListener("pointermove", (e) => {
    if (dragStartY === null || typeof e?.clientY !== "number") return;
    const dy = e.clientY - dragStartY;
    if (Math.abs(dy) >= DRAG_TOGGLE_THRESHOLD_PX) {
      dragMoved = true;
      setCollapsed(dy > 0);
      dragStartY = null;
    }
  });
  handleBtn.addEventListener("pointerup", () => {
    dragStartY = null;
  });
  handleBtn.addEventListener("click", () => {
    if (dragMoved) {
      dragMoved = false;
      return;
    }
    setCollapsed(!collapsed);
  });

  function updatePickButtons() {
    fromField.pickBtn.setAttribute("aria-pressed", String(pickMode === "from"));
    fromField.pickBtn.classList.toggle("is-active", pickMode === "from");
    toField.pickBtn.setAttribute("aria-pressed", String(pickMode === "to"));
    toField.pickBtn.classList.toggle("is-active", pickMode === "to");
  }

  function togglePickMode(kind) {
    pickMode = pickMode === kind ? null : kind;
    updatePickButtons();
    if (pickMode === "from") {
      summaryEl.textContent = "Κάντε κλικ στον χάρτη για σημείο εκκίνησης…";
    } else if (pickMode === "to") {
      summaryEl.textContent = "Κάντε κλικ στον χάρτη για προορισμό…";
    } else if (!lastRoute) {
      summaryEl.textContent = "";
    }
  }

  fromField.pickBtn.addEventListener("click", () => togglePickMode("from"));
  toField.pickBtn.addEventListener("click", () => togglePickMode("to"));

  function handleMapClick(evt) {
    if (!pickMode) {
      return;
    }
    const lngLat = evt?.lngLat;
    const lng = typeof lngLat?.lng === "number" ? lngLat.lng : Array.isArray(lngLat) ? lngLat[0] : null;
    const lat = typeof lngLat?.lat === "number" ? lngLat.lat : Array.isArray(lngLat) ? lngLat[1] : null;
    if (lng === null || lat === null) {
      return;
    }
    const targetKind = pickMode;
    coords[targetKind] = [lng, lat];
    const targetInput = targetKind === "from" ? fromField.input : toField.input;
    targetInput.value = formatCoordPair(coords[targetKind]);
    pickMode = null;
    updatePickButtons();
    summaryEl.textContent =
      targetKind === "from" ? "Ορίστηκε σημείο εκκίνησης." : "Ορίστηκε προορισμός.";
  }

  if (map && typeof map.on === "function") {
    map.on("click", handleMapClick);
  }

  function resolvePoint(kind) {
    if (Array.isArray(coords[kind])) {
      return coords[kind];
    }
    const inputEl = kind === "from" ? fromField.input : toField.input;
    return parseCoordsInput(inputEl.value);
  }

  function drawRoute(routeData) {
    const feature = toRouteFeature(routeData);
    if (!feature) {
      return;
    }
    if (typeof cancelAnimation === "function") {
      cancelAnimation();
      cancelAnimation = null;
    }

    const palette = paletteForProfile(activeProfile);
    mapState.geojson = feature;
    mapState.progress = 0;
    mapState.palette = palette;

    if (map) {
      if (routeData?.comparison) {
        baselineStateByMap.set(map, routeData.comparison);
        registerOverlay(reapplyBaselineOverlay);
        ensureBaselineAndAvoidedOnMap(map, routeData.comparison);
      } else {
        baselineStateByMap.delete(map);
        ensureBaselineAndAvoidedOnMap(map, null);
      }

      ensureRouteOverlayOnMap(map, feature, 0, palette);
      cancelAnimation = animateRoute(
        map,
        ROUTE_LAYER_ID,
        () => {
          mapState.progress = 1;
          cancelAnimation = null;
          fitRouteBounds(map, feature, drawer);
        },
        {
          palette,
          onProgress: (p) => {
            mapState.progress = p;
          },
        },
      );
    }
  }

  async function requestRoute() {
    const from = resolvePoint("from");
    const to = resolvePoint("to");
    if (!from || !to) {
      summaryEl.textContent = "Επιλέξτε εκκίνηση και προορισμό (όνομα περιοχής, συντεταγμένες ή χάρτη).";
      return null;
    }
    if (!api || typeof api.routing !== "function") {
      summaryEl.textContent = "Η υπηρεσία διαδρομών δεν είναι διαθέσιμη.";
      return null;
    }

    const reqId = ++routeRequestSeq;
    routeBtn.disabled = true;
    summaryEl.textContent = "Υπολογισμός διαδρομής…";
    try {
      const response = await api.routing({
        from,
        to,
        profile: activeProfile,
      });
      if (reqId !== routeRequestSeq) {
        return null;
      }
      const sourceTag = response?.source ?? null;
      const route = response?.geometry ? response : response?.data ?? response;
      if (!route || !route.geometry) {
        summaryEl.textContent = "Δεν βρέθηκε διαδρομή.";
        if (map) {
          highlightReasons(map, []);
        }
        return null;
      }

      lastRoute = route;
      startNavBtn.classList?.remove("hidden");
      if (sourceTag && sourceTag !== "live" && typeof options?.onNonLiveSource === "function") {
        options.onNonLiveSource(sourceTag);
      }

      const labelText = routeLabel(route);
      summaryEl.textContent =
        sourceTag === "mock"
          ? `${labelText} (δοκιμαστικό)`
          : sourceTag === "cache"
            ? `${labelText} (cache)`
            : labelText;

      renderWhyCard(route);
      drawRoute(route);
      if (map) {
        const lookup =
          typeof options?.getLookup === "function" ? options.getLookup() : (options?.lookup ?? null);
        highlightReasons(map, route.reasons ?? [], lookup);
      }
      return route;
    } catch {
      if (reqId !== routeRequestSeq) {
        return null;
      }
      summaryEl.textContent = "Δεν ήταν δυνατός ο υπολογισμός διαδρομής.";
      return null;
    } finally {
      if (reqId === routeRequestSeq) {
        routeBtn.disabled = false;
      }
    }
  }

  function handleRouteRequestEvent(event) {
    const detail = event?.detail;
    if (!detail || typeof detail !== "object") {
      return;
    }
    if (isValidProfileId(detail.profile)) {
      activeProfile = detail.profile;
      saveProfile(activeProfile);
      updateProfileButtons();
    }
    if (
      Array.isArray(detail.from) &&
      detail.from.length >= 2 &&
      detail.from[0] != null &&
      detail.from[1] != null &&
      Number.isFinite(Number(detail.from[0])) &&
      Number.isFinite(Number(detail.from[1]))
    ) {
      coords.from = [Number(detail.from[0]), Number(detail.from[1])];
      fromField.input.value = detail.fromLabel ?? formatCoordPair(coords.from);
    } else if (!resolvePoint("from")) {
      coords.from = [ATHENS_PLACES.συνταγμα[0], ATHENS_PLACES.συνταγμα[1]];
      fromField.input.value = "Σύνταγμα";
    }
    if (
      Array.isArray(detail.to) &&
      detail.to.length >= 2 &&
      detail.to[0] != null &&
      detail.to[1] != null &&
      Number.isFinite(Number(detail.to[0])) &&
      Number.isFinite(Number(detail.to[1]))
    ) {
      coords.to = [Number(detail.to[0]), Number(detail.to[1])];
      toField.input.value = detail.toLabel ?? formatCoordPair(coords.to);
    }
    setCollapsed(false);
    requestRoute();
  }

  function handleReportsChangedEvent() {
    if (!lastRoute) {
      return;
    }
    if (!resolvePoint("from") || !resolvePoint("to")) {
      return;
    }
    requestRoute();
  }

  const bus = options?.bus && typeof options.bus.addEventListener === "function" ? options.bus : null;
  if (bus) {
    bus.addEventListener("route:request", handleRouteRequestEvent);
    bus.addEventListener("reports:changed", handleReportsChangedEvent);
    bus.addEventListener("tab:change", (e) => {
      if (e?.detail?.tab && e.detail.tab !== "map" && !collapsed) {
        setCollapsed(true);
      }
    });
  }

  form.addEventListener("submit", (e) => {
    e?.preventDefault?.();
    requestRoute();
  });

  if (typeof container.replaceChildren === "function") {
    container.replaceChildren(drawer);
  } else {
    container.appendChild(drawer);
  }

  return {
    drawer,
    getProfile: () => activeProfile,
    setProfile: (profileId) => {
      if (!isValidProfileId(profileId)) return;
      activeProfile = profileId;
      saveProfile(activeProfile);
      updateProfileButtons();
    },
    setCollapsed,
    requestRoute,
    refreshActiveRoute: handleReportsChangedEvent,
    startNavigation,
    stopNavigation,
    destroy: () => {
      lastRoute = null;
      if (navActive) {
        stopNavigation();
      }
      if (typeof cancelAnimation === "function") {
        cancelAnimation();
        cancelAnimation = null;
      }
      if (map && typeof map.off === "function") {
        map.off("click", handleMapClick);
      }
      if (bus && typeof bus.removeEventListener === "function") {
        bus.removeEventListener("route:request", handleRouteRequestEvent);
        bus.removeEventListener("reports:changed", handleReportsChangedEvent);
      }
    },
  };
}
