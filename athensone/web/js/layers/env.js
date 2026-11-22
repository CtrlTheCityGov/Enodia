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

// Supported heatmap weight modes matching SPEC.md "Backend contracts" GET /env fields and A-37 pm25 mode (certainty: verified).
export const MODES = Object.freeze({
  temp: "temp",
  aqi: "aqi",
  pm25: "pm25",
});

// Temperature normalization bounds (5-38 C covering winter through summer heatwaves in Athens).
const TEMP_MIN_C = 5;
const TEMP_MAX_C = 38;

// AQI normalization bounds (0-150 standard air quality index scale) (certainty: design default).
const AQI_MIN = 0;
const AQI_MAX = 150;

// PM2.5 normalization bounds in ug/m3 (0-75 covering EU/EEA Good through Very Poor bands; source: TASKS_A.md A5 / A-37, bounds certainty: design default).
const PM25_MIN = 0;
const PM25_MAX = 75;

// Heatmap visual tuning constants for 600 m urban point grids (continuous smooth blanket across zooms).
const HEATMAP_INTENSITY = 0.65;
const HEATMAP_RADIUS_LOW_ZOOM = 42;
const HEATMAP_RADIUS_HIGH_ZOOM = 320;
const HEATMAP_OPACITY = 0.68;

// Heatmap color ramp for temperature mode (cool blue -> amber -> hot red) (certainty: design default).
const TEMP_COLOR_RAMP = [
  "interpolate",
  ["linear"],
  ["heatmap-density"],
  0, "rgba(37, 99, 235, 0)",
  0.06, "rgba(56, 189, 248, 0.42)",
  0.28, "rgba(250, 204, 21, 0.62)",
  0.58, "rgba(249, 115, 22, 0.76)",
  0.88, "rgba(220, 38, 38, 0.88)",
];

// Heatmap color ramp for AQI mode (good green -> moderate yellow -> unhealthy purple/red) (certainty: design default).
const AQI_COLOR_RAMP = [
  "interpolate",
  ["linear"],
  ["heatmap-density"],
  0, "rgba(34, 197, 94, 0)",
  0.06, "rgba(34, 197, 94, 0.42)",
  0.28, "rgba(234, 179, 8, 0.62)",
  0.58, "rgba(249, 115, 22, 0.76)",
  0.88, "rgba(147, 51, 234, 0.88)",
];

// Heatmap color ramp for PM2.5 mode (low teal/green -> moderate yellow -> elevated orange -> high crimson) (certainty: design default).
const PM25_COLOR_RAMP = [
  "interpolate",
  ["linear"],
  ["heatmap-density"],
  0, "rgba(16, 185, 129, 0)",
  0.06, "rgba(20, 184, 166, 0.42)",
  0.28, "rgba(250, 204, 21, 0.62)",
  0.58, "rgba(249, 115, 22, 0.76)",
  0.88, "rgba(190, 24, 93, 0.88)",
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
  if (mode === MODES.aqi) {
    return MODES.aqi;
  }
  if (mode === MODES.pm25) {
    return MODES.pm25;
  }
  return MODES.temp;
}

function heatmapColorForMode(mode = MODES.temp) {
  const normalized = normalizeMode(mode);
  if (normalized === MODES.aqi) {
    return AQI_COLOR_RAMP;
  }
  if (normalized === MODES.pm25) {
    return PM25_COLOR_RAMP;
  }
  return TEMP_COLOR_RAMP;
}

export function heatmapWeightForMode(mode = MODES.temp) {
  const normalized = normalizeMode(mode);
  if (normalized === MODES.aqi) {
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
  if (normalized === MODES.pm25) {
    return [
      "interpolate",
      ["linear"],
      ["coalesce", ["to-number", ["get", "pm25"]], 0],
      PM25_MIN,
      0,
      PM25_MAX,
      1,
    ];
  }
  return [
    "interpolate",
    ["linear"],
    ["coalesce", ["to-number", ["get", "temp_c"]], TEMP_MIN_C],
    TEMP_MIN_C,
    0.25,
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
    map.setPaintProperty(HEATMAP_LAYER_ID, "heatmap-color", heatmapColorForMode(nextMode));
  }
  return nextMode;
}

async function loadEnvData(map, api, state) {
  if (!api || typeof api.env !== "function") {
    return emptyFeatureCollection();
  }
  try {
    const res = await api.env();
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
          ["exponential", 2],
          ["zoom"],
          11,
          HEATMAP_RADIUS_LOW_ZOOM,
          14,
          135,
          16,
          HEATMAP_RADIUS_HIGH_ZOOM,
          18,
          640,
        ],
        "heatmap-color": heatmapColorForMode(mode),
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
