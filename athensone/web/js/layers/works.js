// Municipal works layer: road works highlighted with glow + status-colored line
// (SPEC.md F2, F4, "Φούσκα έργου", TASKS_A.md A2/A3).
// Never touches document or maplibregl at import time so Node can import it safely.

// Layer id from TASKS_A.md A2 (certainty: verified).
export const id = "works";

// Greek chip label from TASKS_A.md A2 / SPEC.md F2 (certainty: verified).
export const label = "Έργα";

// Source and layer IDs coordinated with A3 workpopup binding on "works-line" (source: A2 prompt, certainty: verified).
const SOURCE_ID = "works-source";
const GLOW_LAYER_ID = "works-glow";
const LINE_LAYER_ID = "works-line";
const POINTS_LAYER_ID = "works-points";

// MapLibre layer ids added by this module (TASKS_A.md A2, certainty: verified).
export const layerIds = [GLOW_LAYER_ID, LINE_LAYER_ID, POINTS_LAYER_ID];

// Status colors per SPEC.md "Φούσκα έργου" (orange for in_progress, blue for planned) (certainty: verified; hex values design default).
export const WORKS_STATUS_COLORS = Object.freeze({
  in_progress: "#f97316",
  planned: "#2563eb",
  completed: "#16a34a",
  unknown: "#64748b",
});

// Glow and line geometry dimensions for road highlight visibility (certainty: design default).
const GLOW_LINE_WIDTH = 12;
const GLOW_LINE_BLUR = 6;
const GLOW_LINE_OPACITY = 0.5;
const MAIN_LINE_WIDTH = 4.5;
const MAIN_LINE_OPACITY = 0.95;
const WORK_POINT_RADIUS = 7;
const WORK_POINT_STROKE_COLOR = "#ffffff";
const WORK_POINT_STROKE_WIDTH = 2;

function statusColorExpression() {
  return [
    "match",
    ["get", "status"],
    "in_progress",
    WORKS_STATUS_COLORS.in_progress,
    "planned",
    WORKS_STATUS_COLORS.planned,
    "completed",
    WORKS_STATUS_COLORS.completed,
    WORKS_STATUS_COLORS.unknown,
  ];
}

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

async function loadWorksData(map, api, state) {
  if (!api || typeof api.works !== "function") {
    return emptyFeatureCollection();
  }
  try {
    const bbox = getMapBbox(map);
    const res = await api.works(bbox ? { bbox } : undefined);
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

  if (typeof map.getLayer === "function" && !map.getLayer(GLOW_LAYER_ID)) {
    map.addLayer({
      id: GLOW_LAYER_ID,
      type: "line",
      source: SOURCE_ID,
      layout: {
        visibility: initialVisibility,
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": statusColorExpression(),
        "line-width": GLOW_LINE_WIDTH,
        "line-blur": GLOW_LINE_BLUR,
        "line-opacity": GLOW_LINE_OPACITY,
      },
    });
  }

  if (typeof map.getLayer === "function" && !map.getLayer(LINE_LAYER_ID)) {
    map.addLayer({
      id: LINE_LAYER_ID,
      type: "line",
      source: SOURCE_ID,
      layout: {
        visibility: initialVisibility,
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": statusColorExpression(),
        "line-width": MAIN_LINE_WIDTH,
        "line-opacity": MAIN_LINE_OPACITY,
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
        "circle-radius": WORK_POINT_RADIUS,
        "circle-color": statusColorExpression(),
        "circle-stroke-color": WORK_POINT_STROKE_COLOR,
        "circle-stroke-width": WORK_POINT_STROKE_WIDTH,
      },
    });
  }

  const data = await loadWorksData(map, api, state);
  const src = typeof map.getSource === "function" ? map.getSource(SOURCE_ID) : null;
  if (src && typeof src.setData === "function") {
    src.setData(data);
  }

  return { id, layerIds };
}
