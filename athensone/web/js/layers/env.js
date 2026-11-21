// Environment layer: Temperature / AQI heatmap (SPEC.md F2, "Εξωτερικές πηγές", TASKS_A.md A2).
// Never touches document or maplibregl at import time so Node can import it safely.

// Layer id from TASKS_A.md A2 (certainty: verified).
export const id = "env";

// Greek chip label from SPEC.md "HUD (glassmorphism)" and TASKS_A.md A2 (certainty: verified).
export const label = "Θερμοκρασία/AQI";

// MapLibre source and layer identifiers for the environment heatmap (certainty: design default).
const SOURCE_ID = "env-source";
const HEATMAP_LAYER_ID = "env-heat";

// MapLibre layer ids added by this module (TASKS_A.md A2, certainty: verified).
export const layerIds = [HEATMAP_LAYER_ID];

// Supported heatmap weight modes matching SPEC.md "Backend contracts" GET /env fields (certainty: verified).
export const MODES = Object.freeze({
  temp: "temp",
  aqi: "aqi",
});

// Temperature normalization bounds (15-42 C for Athens summer/winter range) (certainty: design default).
const TEMP_MIN_C = 15;
const TEMP_MAX_C = 42;

// AQI normalization bounds (0-150 standard air quality index scale) (certainty: design default).
const AQI_MIN = 0;
const AQI_MAX = 150;

// Heatmap visual tuning constants for urban point grids (certainty: design default).
const HEATMAP_INTENSITY = 1.1;
const HEATMAP_RADIUS_LOW_ZOOM = 24;
const HEATMAP_RADIUS_HIGH_ZOOM = 42;
const HEATMAP_OPACITY = 0.72;

// Heatmap color ramp for temperature mode (cool blue -> amber -> hot red) (certainty: design default).
const TEMP_COLOR_RAMP = [
  "interpolate",
  ["linear"],
  ["heatmap-density"],
  0, "rgba(37, 99, 235, 0)",
  0.25, "rgba(56, 189, 248, 0.55)",
  0.5, "rgba(250, 204, 21, 0.75)",
  0.75, "rgba(249, 115, 22, 0.85)",
  1, "rgba(220, 38, 38, 0.92)",
];

// Heatmap color ramp for AQI mode (good green -> moderate yellow -> unhealthy purple/red) (certainty: design default).
const AQI_COLOR_RAMP = [
  "interpolate",
  ["linear"],
  ["heatmap-density"],
  0, "rgba(34, 197, 94, 0)",
  0.25, "rgba(34, 197, 94, 0.55)",
  0.5, "rgba(234, 179, 8, 0.75)",
  0.75, "rgba(249, 115, 22, 0.85)",
  1, "rgba(147, 51, 234, 0.92)",
];

const modeByMap = new WeakMap();

function emptyFeatureCollection() {
  return { type: "FeatureCollection", features: [] };
}

function toFeatureCollection(res) {
  if (res && res.type === "FeatureCollection" && Array.isArray(res.features)) {
    return res;
  }
  if (res && res.data && res.data.type === "FeatureCollection" && Array.isArray(res.data.features)) {
    return res.data;
  }
  return emptyFeatureCollection();
}

function getMapBbox(map) {
  if (!map || typeof map.getBounds !== "function") {
    return null;
  }
  const b = map.getBounds();
  if (!b || typeof b.getWest !== "function") {
    return null;
  }
  return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
}

function normalizeMode(mode) {
  return mode === MODES.aqi ? MODES.aqi : MODES.temp;
}

export function heatmapWeightForMode(mode = MODES.temp) {
  if (normalizeMode(mode) === MODES.aqi) {
    return [
      "interpolate",
      ["linear"],
      ["coalesce", ["to-number", ["get", "aqi"]], 0],
      AQI_MIN,
      0,
      AQI_MAX,
      1,
    ];
  }
  return [
    "interpolate",
    ["linear"],
    ["coalesce", ["to-number", ["get", "temp_c"]], 0],
    TEMP_MIN_C,
    0,
    TEMP_MAX_C,
    1,
  ];
}

export function getMode(map) {
  return (map && modeByMap.get(map)) ?? MODES.temp;
}

export function setMode(map, mode) {
  const nextMode = normalizeMode(mode);
  if (map) {
    modeByMap.set(map, nextMode);
  }
  if (!map || typeof map.setPaintProperty !== "function") {
    return nextMode;
  }
  if (typeof map.getLayer !== "function" || map.getLayer(HEATMAP_LAYER_ID)) {
    map.setPaintProperty(HEATMAP_LAYER_ID, "heatmap-weight", heatmapWeightForMode(nextMode));
    map.setPaintProperty(
      HEATMAP_LAYER_ID,
      "heatmap-color",
      nextMode === MODES.aqi ? AQI_COLOR_RAMP : TEMP_COLOR_RAMP,
    );
  }
  return nextMode;
}

async function loadEnvData(map, api, state) {
  if (!api || typeof api.env !== "function") {
    return emptyFeatureCollection();
  }
  try {
    const bbox = getMapBbox(map);
    const res = await api.env(bbox ? { bbox } : undefined);
    if (res?.source && res.source !== "live" && typeof state?.onOffline === "function") {
      state.onOffline();
    }
    return toFeatureCollection(res);
  } catch {
    return emptyFeatureCollection();
  }
}

export async function register(map, api, options = {}) {
  if (!map) {
    return { id, layerIds };
  }

  const mode = normalizeMode(options?.mode ?? options?.envMode ?? modeByMap.get(map));
  modeByMap.set(map, mode);

  const initialVisibility = options?.visible?.[id] ? "visible" : "none";

  if (typeof map.getSource === "function" && !map.getSource(SOURCE_ID)) {
    map.addSource(SOURCE_ID, {
      type: "geojson",
      data: emptyFeatureCollection(),
    });
  }

  if (typeof map.getLayer === "function" && !map.getLayer(HEATMAP_LAYER_ID)) {
    map.addLayer({
      id: HEATMAP_LAYER_ID,
      type: "heatmap",
      source: SOURCE_ID,
      layout: {
        visibility: initialVisibility,
      },
      paint: {
        "heatmap-weight": heatmapWeightForMode(mode),
        "heatmap-intensity": HEATMAP_INTENSITY,
        "heatmap-radius": [
          "interpolate",
          ["linear"],
          ["zoom"],
          11,
          HEATMAP_RADIUS_LOW_ZOOM,
          16,
          HEATMAP_RADIUS_HIGH_ZOOM,
        ],
        "heatmap-color": mode === MODES.aqi ? AQI_COLOR_RAMP : TEMP_COLOR_RAMP,
        "heatmap-opacity": HEATMAP_OPACITY,
      },
    });
  }

  const data = await loadEnvData(map, api, options);
  const src = typeof map.getSource === "function" ? map.getSource(SOURCE_ID) : null;
  if (src && typeof src.setData === "function") {
    src.setData(data);
  }

  return { id, layerIds };
}
