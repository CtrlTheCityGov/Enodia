// Citizen reports (Waze pins) layer — always visible on the map, no pill bar chip
// (SPEC.md F3, TASKS_A.md A2).
// Never touches document or maplibregl at import time so Node can import it safely.

// Layer id from TASKS_A.md A2 (certainty: verified).
export const id = "reports";

// Greek label for citizen reports (source: SPEC.md F3 "Αναφορές πολιτών", certainty: verified).
export const label = "Αναφορές";

// MapLibre source and layer identifiers for always-on report pins (certainty: design default).
const SOURCE_ID = "reports-source";
const PINS_LAYER_ID = "reports-pins";

// MapLibre layer ids added by this module (TASKS_A.md A2, certainty: verified).
export const layerIds = [PINS_LAYER_ID];

// Category pin colors matching SPEC.md F3 categories (certainty: design default).
const REPORT_COLORS = Object.freeze({
  traffic: "#ef4444",
  incident: "#dc2626",
  obstacle: "#f59e0b",
  damage: "#a855f7",
  work_progress: "#2563eb",
  default: "#f97316",
});

// Pin visual dimensions for light/dark readability (certainty: design default).
const REPORT_PIN_RADIUS = 7;
const REPORT_STROKE_COLOR = "#ffffff";
const REPORT_STROKE_WIDTH = 2;

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

async function loadReportsData(map, api, state) {
  if (!api || typeof api.reports !== "function") {
    return emptyFeatureCollection();
  }
  try {
    const bbox = getMapBbox(map);
    const res = await api.reports(bbox ? { bbox } : undefined);
    if (res?.source && res.source !== "live" && typeof state?.onOffline === "function") {
      state.onOffline();
    }
    return toFeatureCollection(res);
  } catch {
    return emptyFeatureCollection();
  }
}

export function setData(map, geojson) {
  const src = map && typeof map.getSource === "function" ? map.getSource(SOURCE_ID) : null;
  if (src && typeof src.setData === "function") {
    src.setData(toFeatureCollection(geojson));
  }
}

export async function refresh(map, api, state = {}) {
  if (!map) {
    return emptyFeatureCollection();
  }
  const data = await loadReportsData(map, api, state);
  setData(map, data);
  return data;
}

export async function register(map, api, state = {}) {
  if (!map) {
    return { id, layerIds };
  }

  if (typeof map.getSource === "function" && !map.getSource(SOURCE_ID)) {
    map.addSource(SOURCE_ID, {
      type: "geojson",
      data: emptyFeatureCollection(),
    });
  }

  if (typeof map.getLayer === "function" && !map.getLayer(PINS_LAYER_ID)) {
    map.addLayer({
      id: PINS_LAYER_ID,
      type: "circle",
      source: SOURCE_ID,
      layout: {
        // Citizen reports are always on and have no chip in the pill bar (TASKS_A.md A2).
        visibility: "visible",
      },
      paint: {
        "circle-radius": REPORT_PIN_RADIUS,
        "circle-color": [
          "match",
          ["coalesce", ["get", "category"], ""],
          ["congestion", "traffic", "συμφόρηση"],
          REPORT_COLORS.traffic,
          ["incident", "συμβάν"],
          REPORT_COLORS.incident,
          ["obstacle", "εμπόδιο"],
          REPORT_COLORS.obstacle,
          ["damage", "ζημιά"],
          REPORT_COLORS.damage,
          ["work_progress", "πρόοδος έργου"],
          REPORT_COLORS.work_progress,
          REPORT_COLORS.default,
        ],
        "circle-stroke-color": REPORT_STROKE_COLOR,
        "circle-stroke-width": REPORT_STROKE_WIDTH,
      },
    });
  }

  await refresh(map, api, state);

  return { id, layerIds };
}
