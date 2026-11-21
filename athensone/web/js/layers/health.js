// On-duty pharmacies and hospitals layer (SPEC.md F2, "Εξωτερικές πηγές", TASKS_A.md A2).
// Never touches document or maplibregl at import time so Node can import it safely.

// Layer id from TASKS_A.md A2 (certainty: verified).
export const id = "health";

// Greek chip label from SPEC.md "HUD (glassmorphism)" and TASKS_A.md A2 (certainty: verified).
export const label = "Εφημερεύοντα";

// MapLibre source and layer identifiers for on-duty health facilities (certainty: design default).
const SOURCE_ID = "health-source";
const POINTS_LAYER_ID = "health-points";

// MapLibre layer ids added by this module (TASKS_A.md A2, certainty: verified).
export const layerIds = [POINTS_LAYER_ID];

// Marker colors distinguishing pharmacies (green) and hospitals (red) (certainty: design default).
const PHARMACY_COLOR = "#16a34a";
const HOSPITAL_COLOR = "#dc2626";
const HEALTH_DEFAULT_COLOR = "#059669";
const HEALTH_POINT_RADIUS = 7;
const HEALTH_STROKE_COLOR = "#ffffff";
const HEALTH_STROKE_WIDTH = 2;

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

async function loadHealthData(api, state) {
  if (!api || typeof api.health !== "function") {
    return emptyFeatureCollection();
  }
  try {
    const res = await api.health();
    if (res?.source && res.source !== "live" && typeof state?.onOffline === "function") {
      state.onOffline();
    }
    return toFeatureCollection(res);
  } catch {
    return emptyFeatureCollection();
  }
}

export async function register(map, api, state = {}) {
  if (!map) {
    return { id, layerIds };
  }

  const initialVisibility = state?.visible?.[id] ? "visible" : "none";

  if (typeof map.getSource === "function" && !map.getSource(SOURCE_ID)) {
    map.addSource(SOURCE_ID, {
      type: "geojson",
      data: emptyFeatureCollection(),
    });
  }

  if (typeof map.getLayer === "function" && !map.getLayer(POINTS_LAYER_ID)) {
    map.addLayer({
      id: POINTS_LAYER_ID,
      type: "circle",
      source: SOURCE_ID,
      layout: {
        visibility: initialVisibility,
      },
      paint: {
        "circle-radius": HEALTH_POINT_RADIUS,
        "circle-color": [
          "match",
          ["coalesce", ["get", "kind"], ""],
          ["hospital", "νοσοκομείο", "Νοσοκομείο"],
          HOSPITAL_COLOR,
          ["pharmacy", "φαρμακείο", "Φαρμακείο"],
          PHARMACY_COLOR,
          HEALTH_DEFAULT_COLOR,
        ],
        "circle-stroke-color": HEALTH_STROKE_COLOR,
        "circle-stroke-width": HEALTH_STROKE_WIDTH,
      },
    });
  }

  const data = await loadHealthData(api, state);
  const src = typeof map.getSource === "function" ? map.getSource(SOURCE_ID) : null;
  if (src && typeof src.setData === "function") {
    src.setData(data);
  }

  return { id, layerIds };
}
