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

// MapLibre source and layer IDs for the active route (source: A4_routing.test.js; certainty: verified).
export const ROUTE_SOURCE_ID = "route";
export const ROUTE_LAYER_ID = "route-line";

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
  μοναστηρακι: [23.7257, 37.9764],
  monastiraki: [23.7257, 37.9764],
  ομονοια: [23.728, 37.9841],
  omonia: [23.728, 37.9841],
  ακροπολη: [23.7257, 37.9715],
  acropolis: [23.7257, 37.9715],
  σεραφειο: [23.7115, 37.9776],
  serafio: [23.7115, 37.9776],
};

// Per-map active route state so Light/Dark setStyle() switches restore the active route without leaking fake maps in tests.
const routeStateByMap = new WeakMap();

function isValidProfileId(id) {
  return PROFILES.some((p) => p.id === id);
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

export function loadSavedProfile(storage = typeof globalThis.localStorage !== "undefined" ? globalThis.localStorage : null) {
  const fallback = PROFILES[0].id;
  if (!storage || typeof storage.getItem !== "function") {
    return fallback;
  }
  try {
    const saved = storage.getItem(PROFILE_STORAGE_KEY);
    return isValidProfileId(saved) ? saved : fallback;
  } catch {
    return fallback;
  }
}

export function saveProfile(profileId, storage = typeof globalThis.localStorage !== "undefined" ? globalThis.localStorage : null) {
  if (!isValidProfileId(profileId) || !storage || typeof storage.setItem !== "function") {
    return false;
  }
  try {
    storage.setItem(PROFILE_STORAGE_KEY, profileId);
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

export function gradientAt(progress) {
  const numeric = Number(progress);
  const p = Number.isFinite(numeric) ? Math.max(0, Math.min(1, numeric)) : 0;

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
      ROUTE_COLOR_START,
      1,
      ROUTE_COLOR_END,
    ];
  }

  const fadeStop = Math.min(1, p + GRADIENT_EDGE_EPSILON);
  const expr = [
    "interpolate",
    ["linear"],
    ["line-progress"],
    0,
    ROUTE_COLOR_START,
    p,
    ROUTE_COLOR_END,
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
  const raf = globalThis.requestAnimationFrame;
  const cancelRaf = globalThis.cancelAnimationFrame;

  let cancelled = false;
  let rafId = null;
  let startTime = null;

  function applyProgress(progress) {
    if (onProgress) {
      onProgress(progress);
    }
    if (
      map &&
      typeof map.setPaintProperty === "function" &&
      (typeof map.getLayer !== "function" || map.getLayer(layerId))
    ) {
      map.setPaintProperty(layerId, "line-gradient", gradientAt(progress));
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

function routeLayerSpec(progress) {
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
      "line-gradient": gradientAt(progress),
    },
  };
}

function ensureRouteOverlayOnMap(map, geojson, progress) {
  if (!map || !geojson) {
    return;
  }
  const existingSource = typeof map.getSource === "function" ? map.getSource(ROUTE_SOURCE_ID) : null;
  if (existingSource && typeof existingSource.setData === "function") {
    existingSource.setData(geojson);
  } else if (typeof map.addSource === "function") {
    map.addSource(ROUTE_SOURCE_ID, routeSource(geojson));
  }

  const hasLayer = typeof map.getLayer === "function" ? Boolean(map.getLayer(ROUTE_LAYER_ID)) : false;
  if (!hasLayer && typeof map.addLayer === "function") {
    map.addLayer(routeLayerSpec(progress));
  } else if (hasLayer && typeof map.setPaintProperty === "function") {
    map.setPaintProperty(ROUTE_LAYER_ID, "line-gradient", gradientAt(progress));
  }
}

function reapplyRouteOverlay(targetMap) {
  const routeState = routeStateByMap.get(targetMap);
  if (!routeState || !routeState.geojson) {
    return null;
  }
  ensureRouteOverlayOnMap(targetMap, routeState.geojson, routeState.progress);
  return {
    id: ROUTE_SOURCE_ID,
    layerIds: [ROUTE_LAYER_ID],
  };
}

export function initRouting(container, map, api, options = {}) {
  const doc = container?.ownerDocument ?? (typeof globalThis.document !== "undefined" ? globalThis.document : null);
  if (!container || !doc) {
    return null;
  }

  let activeProfile = loadSavedProfile();
  let collapsed = false;
  let pickMode = null;
  let cancelAnimation = null;
  let lastRoute = null;
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
    inputWrap.appendChild(pickBtn);
    row.appendChild(label);
    row.appendChild(inputWrap);
    form.appendChild(row);

    return { input, pickBtn };
  }

  const fromField = createPointField("from", "Από", "Σύνταγμα ή lat, lon");
  const toField = createPointField("to", "Προς", "Μοναστηράκι ή lat, lon");

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

  for (const profile of PROFILES) {
    const btn = doc.createElement("button");
    btn.type = "button";
    btn.className = "routing-profile-btn";
    btn.setAttribute("data-profile", profile.id);
    btn.setAttribute("aria-pressed", String(profile.id === activeProfile));
    btn.textContent = profile.label;
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
  form.appendChild(actionsRow);

  const summaryEl = doc.createElement("div");
  summaryEl.className = "routing-summary";
  summaryEl.setAttribute("role", "status");
  summaryEl.setAttribute("aria-live", "polite");
  drawer.appendChild(summaryEl);

  function setCollapsed(nextCollapsed) {
    collapsed = Boolean(nextCollapsed);
    drawer.classList.toggle("is-collapsed", collapsed);
    handleBtn.setAttribute("aria-expanded", String(!collapsed));
  }

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

    mapState.geojson = feature;
    mapState.progress = 0;

    if (map) {
      ensureRouteOverlayOnMap(map, feature, 0);
      cancelAnimation = animateRoute(
        map,
        ROUTE_LAYER_ID,
        () => {
          mapState.progress = 1;
          cancelAnimation = null;
          fitRouteBounds(map, feature, drawer);
        },
        {
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

    routeBtn.disabled = true;
    summaryEl.textContent = "Υπολογισμός διαδρομής…";
    try {
      const response = await api.routing({
        from,
        to,
        profile: activeProfile,
      });
      const sourceTag = response?.source ?? null;
      const route = response?.geometry ? response : response?.data ?? response;
      if (!route || !route.geometry) {
        summaryEl.textContent = "Δεν βρέθηκε διαδρομή.";
        return null;
      }

      lastRoute = route;
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

      drawRoute(route);
      return route;
    } catch {
      summaryEl.textContent = "Δεν ήταν δυνατός ο υπολογισμός διαδρομής.";
      return null;
    } finally {
      routeBtn.disabled = false;
    }
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
    destroy: () => {
      if (typeof cancelAnimation === "function") {
        cancelAnimation();
        cancelAnimation = null;
      }
      if (map && typeof map.off === "function") {
        map.off("click", handleMapClick);
      }
    },
  };
}
