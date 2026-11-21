// Accessibility / Ramps layer: lowered kerbs, ramps, tactile paving, wheelchair POIs
// (SPEC.md F2, "Εξωτερικές πηγές", TASKS_A.md A2).
// Never touches document or maplibregl at import time so Node can import it safely.

// Layer id from TASKS_A.md A2 (certainty: verified).
export const id = "access";

// Greek chip label from SPEC.md "HUD (glassmorphism)" and TASKS_A.md A2 (certainty: verified).
export const label = "Προσβασιμότητα/Ράμπες";

// MapLibre source and layer identifiers for accessibility features (certainty: design default).
const SOURCE_ID = "access-source";
const LINES_LAYER_ID = "access-lines";
const POINTS_LAYER_ID = "access-points";

// MapLibre layer ids added by this module (TASKS_A.md A2, certainty: verified).
export const layerIds = [LINES_LAYER_ID, POINTS_LAYER_ID];

// Accessibility visual styling constants for light/dark readability (certainty: design default).
const ACCESS_LINE_COLOR = "#0d9488";
const ACCESS_LINE_WIDTH = 3;
const ACCESS_POINT_COLOR_OK = "#10b981";
const ACCESS_POINT_COLOR_LIMITED = "#f59e0b";
const ACCESS_POINT_COLOR_NO = "#dc2626";
const ACCESS_POINT_COLOR_DEFAULT = "#14b8a6";
const ACCESS_POINT_RADIUS = 6;
const ACCESS_STROKE_COLOR = "#ffffff";
const ACCESS_STROKE_WIDTH = 2;

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

async function loadAccessData(api, state) {
  if (!api || typeof api.access !== "function") {
    return emptyFeatureCollection();
  }
  try {
    const res = await api.access();
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

  if (typeof map.getLayer === "function" && !map.getLayer(LINES_LAYER_ID)) {
    map.addLayer({
      id: LINES_LAYER_ID,
      type: "line",
      source: SOURCE_ID,
      filter: ["in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]]],
      layout: {
        visibility: initialVisibility,
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": ACCESS_LINE_COLOR,
        "line-width": ACCESS_LINE_WIDTH,
        "line-opacity": 0.9,
      },
    });
  }

  if (typeof map.getLayer === "function" && !map.getLayer(POINTS_LAYER_ID)) {
    map.addLayer({
      id: POINTS_LAYER_ID,
      type: "circle",
      source: SOURCE_ID,
      filter: ["in", ["geometry-type"], ["literal", ["Point", "MultiPoint"]]],
      layout: {
        visibility: initialVisibility,
      },
      paint: {
        "circle-radius": ACCESS_POINT_RADIUS,
        "circle-color": [
          "match",
          ["coalesce", ["get", "wheelchair"], ""],
          "yes",
          ACCESS_POINT_COLOR_OK,
          "limited",
          ACCESS_POINT_COLOR_LIMITED,
          "no",
          ACCESS_POINT_COLOR_NO,
          ACCESS_POINT_COLOR_DEFAULT,
        ],
        "circle-stroke-color": ACCESS_STROKE_COLOR,
        "circle-stroke-width": ACCESS_STROKE_WIDTH,
      },
    });
  }

  const data = await loadAccessData(api, state);
  const src = typeof map.getSource === "function" ? map.getSource(SOURCE_ID) : null;
  if (src && typeof src.setData === "function") {
    src.setData(data);
  }

  return { id, layerIds };
}
