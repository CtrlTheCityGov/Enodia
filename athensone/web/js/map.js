// Map core module: 3D camera, Light/Dark OpenFreeMap styles, 3D buildings,
// overlay lifecycle across setStyle(), and inline v8 offline fallback
// (SPEC.md "Engine και στυλ", "Offline fallback" 1-2; TASKS_A.md A1).
// Never touches document or maplibregl at import time so Node can import it safely.
// Never uses the Fetch API (CLAUDE.md: only api.js performs network requests).

// Initial Syntagma Square camera settings (source: SPEC.md "Engine και στυλ", certainty: verified).
export const CAMERA = {
  center: [23.7348, 37.9755],
  zoom: 15,
  pitch: 55,
  bearing: -15,
  maxPitch: 70,
};

// OpenFreeMap vector style URLs (source: SPEC.md "Engine και στυλ", certainty: verified in SPEC;
// live URL reachability unverified in offline test environment).
export const STYLES = {
  light: "https://tiles.openfreemap.org/styles/liberty",
  dark: "https://tiles.openfreemap.org/styles/fiord",
};

// Wait threshold before switching to the inline offline style (source: SPEC.md "Offline fallback" 1, certainty: verified).
const STYLE_LOAD_TIMEOUT_MS = 6000;

// 3D buildings layer spec constants (source: SPEC.md "Engine και στυλ", TASKS_A.md A1, certainty: verified).
const BUILDINGS_LAYER_ID = "3d-buildings";
const BUILDINGS_SOURCE = "openmaptiles";
const BUILDINGS_SOURCE_LAYER = "building";
const BUILDINGS_MINZOOM = 14;

// Architectural extrusion tint and translucency for light/dark themes (certainty: design default).
const BUILDINGS_COLOR_LIGHT = "#d4d8df";
const BUILDINGS_COLOR_DARK = "#3a4559";
const BUILDINGS_OPACITY = 0.75;

// Inline offline style colors aligned with light paper and dark Fiord palettes (certainty: design default).
const OFFLINE_BG_LIGHT = "#eef2f6";
const OFFLINE_BG_DARK = "#141820";
const OFFLINE_BOUNDARY_FILL_LIGHT = "rgba(37, 99, 235, 0.08)";
const OFFLINE_BOUNDARY_LINE_LIGHT = "#64748b";
const OFFLINE_ROADS_LINE_LIGHT = "#94a3b8";
const OFFLINE_BOUNDARY_FILL_DARK = "rgba(96, 165, 250, 0.12)";
const OFFLINE_BOUNDARY_LINE_DARK = "#64748b";
const OFFLINE_ROADS_LINE_DARK = "#475569";

// MapLibre Style Specification version required for inline styles (source: SPEC.md "Offline fallback" 1, certainty: verified).
const STYLE_SPEC_VERSION = 8;

const overlays = [];
const styleLoadBound = new WeakSet();
const boundStates = new WeakMap();

export function needs3dBuildings(style) {
  const layers = Array.isArray(style?.layers) ? style.layers : [];
  return !layers.some((layer) => layer && layer.type === "fill-extrusion");
}

export function buildingsLayer(theme = "light") {
  return {
    id: BUILDINGS_LAYER_ID,
    type: "fill-extrusion",
    source: BUILDINGS_SOURCE,
    "source-layer": BUILDINGS_SOURCE_LAYER,
    minzoom: BUILDINGS_MINZOOM,
    paint: {
      "fill-extrusion-color": theme === "dark" ? BUILDINGS_COLOR_DARK : BUILDINGS_COLOR_LIGHT,
      "fill-extrusion-height": ["coalesce", ["get", "render_height"], 0],
      "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
      "fill-extrusion-opacity": BUILDINGS_OPACITY,
    },
  };
}

export function offlineStyle(geo = null, theme = "light") {
  const isDark = theme === "dark";
  const sources = {};
  const layers = [
    {
      id: "offline-background",
      type: "background",
      paint: {
        "background-color": isDark ? OFFLINE_BG_DARK : OFFLINE_BG_LIGHT,
      },
    },
  ];

  if (geo && typeof geo === "object") {
    sources["offline-base"] = {
      type: "geojson",
      data: geo,
    };
    layers.push(
      {
        id: "offline-boundary-fill",
        type: "fill",
        source: "offline-base",
        filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
        paint: {
          "fill-color": isDark ? OFFLINE_BOUNDARY_FILL_DARK : OFFLINE_BOUNDARY_FILL_LIGHT,
        },
      },
      {
        id: "offline-boundary-line",
        type: "line",
        source: "offline-base",
        filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
        paint: {
          "line-color": isDark ? OFFLINE_BOUNDARY_LINE_DARK : OFFLINE_BOUNDARY_LINE_LIGHT,
          "line-width": 1.5,
        },
      },
      {
        id: "offline-roads",
        type: "line",
        source: "offline-base",
        filter: ["in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]]],
        paint: {
          "line-color": isDark ? OFFLINE_ROADS_LINE_DARK : OFFLINE_ROADS_LINE_LIGHT,
          "line-width": 2,
        },
      },
    );
  }

  return {
    version: STYLE_SPEC_VERSION,
    sources,
    layers,
  };
}

export function registerOverlay(fn) {
  if (typeof fn === "function" && !overlays.includes(fn)) {
    overlays.push(fn);
  }
}

export function clearOverlays() {
  overlays.length = 0;
}

export function addOverlays(map, state) {
  if (!map) {
    return;
  }

  const style = typeof map.getStyle === "function" ? map.getStyle() : null;
  const hasOpenMapTiles =
    typeof map.getSource === "function" ? Boolean(map.getSource(BUILDINGS_SOURCE)) : true;
  const has3dLayer =
    typeof map.getLayer === "function" ? Boolean(map.getLayer(BUILDINGS_LAYER_ID)) : false;

  if (
    needs3dBuildings(style) &&
    hasOpenMapTiles &&
    !has3dLayer &&
    typeof map.addLayer === "function"
  ) {
    map.addLayer(buildingsLayer(state?.theme));
  }

  const ownedLayers = new Map();
  for (const fn of overlays) {
    const result = fn(map, state);
    if (result && typeof result.id === "string" && Array.isArray(result.layerIds)) {
      ownedLayers.set(result.id, result.layerIds);
    }
  }

  const visible = state?.visible;
  if (visible && typeof visible === "object" && typeof map.setLayoutProperty === "function") {
    for (const [key, isVisible] of Object.entries(visible)) {
      const visibility = isVisible ? "visible" : "none";
      const targetIds = ownedLayers.get(key) ?? [key];
      for (const layerId of targetIds) {
        if (typeof map.getLayer !== "function" || map.getLayer(layerId)) {
          map.setLayoutProperty(layerId, "visibility", visibility);
        }
      }
    }
  }
}

export function setTheme(map, theme, state) {
  if (!map || typeof map.setStyle !== "function") {
    return;
  }

  const nextTheme = theme === "dark" ? "dark" : "light";
  if (state && typeof state === "object") {
    state.theme = nextTheme;
  }

  if (styleLoadBound.has(map)) {
    if (state && typeof state === "object") {
      boundStates.set(map, state);
    }
  } else if (typeof map.once === "function") {
    map.once("style.load", () => {
      addOverlays(map, state);
    });
  }

  if (state?.offline) {
    map.setStyle(offlineStyle(state.offlineGeo, nextTheme));
  } else {
    map.setStyle(STYLES[nextTheme]);
  }
}

export function createMap(container, state = {}) {
  const maplibregl = globalThis.maplibregl;
  if (!maplibregl || typeof maplibregl.Map !== "function") {
    return null;
  }

  const mapState = state && typeof state === "object" ? state : {};
  const initialTheme = mapState.theme === "dark" ? "dark" : "light";

  const map = new maplibregl.Map({
    container,
    style: STYLES[initialTheme],
    center: CAMERA.center,
    zoom: CAMERA.zoom,
    pitch: CAMERA.pitch,
    bearing: CAMERA.bearing,
    maxPitch: CAMERA.maxPitch,
  });

  let switchedOffline = false;
  let loadTimer = null;

  function clearLoadTimer() {
    if (loadTimer !== null) {
      clearTimeout(loadTimer);
      loadTimer = null;
    }
  }

  function switchToOffline() {
    if (switchedOffline) {
      return;
    }
    switchedOffline = true;
    clearLoadTimer();
    const activeState = boundStates.get(map) ?? mapState;
    activeState.offline = true;
    if (typeof activeState.onOffline === "function") {
      activeState.onOffline(map, activeState);
    }
    map.setStyle(offlineStyle(activeState.offlineGeo, activeState.theme));
  }

  styleLoadBound.add(map);
  boundStates.set(map, mapState);

  if (typeof map.on === "function") {
    map.on("style.load", () => {
      clearLoadTimer();
      addOverlays(map, boundStates.get(map) ?? mapState);
    });

    map.on("error", () => {
      switchToOffline();
    });
  }

  loadTimer = setTimeout(switchToOffline, STYLE_LOAD_TIMEOUT_MS);

  return map;
}
