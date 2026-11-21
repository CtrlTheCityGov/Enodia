// Transit layer: OASA live buses (20 s polling only while on) + Metro/Suburban lines & stations
// (SPEC.md F2, "Εξωτερικές πηγές", TASKS_A.md A2).
// Never touches document or maplibregl at import time so Node can import it safely.

// Module id from TASKS_A.md A2 (certainty: verified).
export const id = "transit";

// Sub-toggle ids and Greek chip labels from SPEC.md "HUD (glassmorphism)" & TASKS_A.md A2 (certainty: verified).
export const BUSES_ID = "transit-buses";
export const BUSES_LABEL = "Τηλεματική ΟΑΣΑ";
export const RAIL_ID = "transit-rail";
export const RAIL_LABEL = "Μετρό/Προαστιακός";

// Default module Greek label matching the OASA telematics chip (SPEC.md "HUD (glassmorphism)", certainty: verified).
export const label = BUSES_LABEL;

// Bus telematics polling interval: 20 s (source: SPEC.md "Εξωτερικές πηγές", TASKS_A.md A2, certainty: verified).
export const BUS_POLL_INTERVAL_MS = 20_000;

// Official Athens Metro & Suburban rail line colors (source: A2 prompt & STASY/OASA branding, certainty: verified in prompt).
export const ATHENS_LINE_COLORS = Object.freeze({
  M1: "#007a3d", // Line 1 (ISAP) green
  M2: "#dc2626", // Line 2 red
  M3: "#0066b3", // Line 3 blue
  Suburban: "#eab308", // Proastiakos / Suburban rail yellow
  default: "#6b7280", // Neutral fallback for unrecognized line codes (certainty: design default)
});

// MapLibre source and layer identifiers for transit sub-groups (certainty: design default).
const LINES_SOURCE_ID = "transit-lines-source";
const STATIONS_SOURCE_ID = "transit-stations-source";
const BUSES_SOURCE_ID = "transit-buses-source";

const RAIL_LINES_LAYER_ID = "transit-rail-lines";
const RAIL_STATIONS_LAYER_ID = "transit-rail-stations";
const BUSES_LAYER_ID = "transit-buses";

// Separate toggleable layer id lists for the two transit chips (TASKS_A.md A2, certainty: verified).
export const busLayerIds = [BUSES_LAYER_ID];
export const railLayerIds = [RAIL_LINES_LAYER_ID, RAIL_STATIONS_LAYER_ID];

// All MapLibre layer ids added by this module (TASKS_A.md A2, certainty: verified).
export const layerIds = [...railLayerIds, ...busLayerIds];

// Visual styling constants for rail lines, stations, and buses (certainty: design default).
const RAIL_LINE_WIDTH = 4;
const STATION_RADIUS = 5.5;
const STATION_FILL_COLOR = "#ffffff";
const STATION_STROKE_WIDTH = 3;
const BUS_COLOR = "#0284c7";
const BUS_RADIUS = 7;
const BUS_STROKE_COLOR = "#ffffff";
const BUS_STROKE_WIDTH = 2;

const busPollTimers = new WeakMap();

function emptyFeatureCollection() {
  return { type: "FeatureCollection", features: [] };
}

function toFeatureCollection(value) {
  if (value && value.type === "FeatureCollection" && Array.isArray(value.features)) {
    return value;
  }
  return emptyFeatureCollection();
}

function toTransitBundle(res) {
  const payload = res && res.data && typeof res.data === "object" ? res.data : res;
  return {
    lines: toFeatureCollection(payload?.lines),
    stations: toFeatureCollection(payload?.stations),
    buses: toFeatureCollection(payload?.buses),
  };
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

function lineColorExpression() {
  return [
    "match",
    ["coalesce", ["get", "line"], ["get", "ref"], ["get", "route_short_name"], ""],
    ["M1", "1", "Γραμμή 1"],
    ATHENS_LINE_COLORS.M1,
    ["M2", "2", "Γραμμή 2"],
    ATHENS_LINE_COLORS.M2,
    ["M3", "3", "Γραμμή 3"],
    ATHENS_LINE_COLORS.M3,
    ["Suburban", "suburban", "Proastiakos", "Προαστιακός", "P1", "P2", "P3", "Π1", "Π2", "Π3"],
    ATHENS_LINE_COLORS.Suburban,
    ["coalesce", ["get", "color"], ATHENS_LINE_COLORS.default],
  ];
}

function applyVisibility(map, ids, isVisible) {
  if (!map || typeof map.setLayoutProperty !== "function") {
    return;
  }
  const visibility = isVisible ? "visible" : "none";
  for (const layerId of ids) {
    if (typeof map.getLayer !== "function" || map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "visibility", visibility);
    }
  }
}

async function loadTransitData(map, api, { updateRail = false, updateBuses = false, state = null } = {}) {
  if (!map || !api || typeof api.transit !== "function") {
    return null;
  }
  try {
    const bbox = getMapBbox(map);
    const res = await api.transit(bbox ? { bbox } : undefined);
    if (res?.source && res.source !== "live" && typeof state?.onOffline === "function") {
      state.onOffline();
    }
    const bundle = toTransitBundle(res);
    if (updateRail && typeof map.getSource === "function") {
      const linesSrc = map.getSource(LINES_SOURCE_ID);
      if (linesSrc && typeof linesSrc.setData === "function") {
        linesSrc.setData(bundle.lines);
      }
      const stationsSrc = map.getSource(STATIONS_SOURCE_ID);
      if (stationsSrc && typeof stationsSrc.setData === "function") {
        stationsSrc.setData(bundle.stations);
      }
    }
    if (updateBuses && typeof map.getSource === "function") {
      const busesSrc = map.getSource(BUSES_SOURCE_ID);
      if (busesSrc && typeof busesSrc.setData === "function") {
        busesSrc.setData(bundle.buses);
      }
    }
    return bundle;
  } catch {
    return null;
  }
}

export function stopBusPolling(map) {
  if (!map) {
    return;
  }
  const timerId = busPollTimers.get(map);
  if (timerId !== undefined) {
    clearInterval(timerId);
    busPollTimers.delete(map);
  }
}

export function startBusPolling(map, api, state = null) {
  if (!map) {
    return;
  }
  stopBusPolling(map);
  if (!api || typeof api.transit !== "function") {
    return;
  }
  loadTransitData(map, api, { updateBuses: true, state });
  const timerId = setInterval(() => {
    loadTransitData(map, api, { updateBuses: true, state });
  }, BUS_POLL_INTERVAL_MS);
  busPollTimers.set(map, timerId);
}

export function setBusesEnabled(map, api, enabled, state = null) {
  const isOn = Boolean(enabled);
  applyVisibility(map, busLayerIds, isOn);
  if (isOn) {
    startBusPolling(map, api, state);
  } else {
    stopBusPolling(map);
  }
}

export function setRailEnabled(map, api, enabled, state = null) {
  const isOn = Boolean(enabled);
  applyVisibility(map, railLayerIds, isOn);
  if (isOn) {
    loadTransitData(map, api, { updateRail: true, state });
  }
}

export async function register(map, api, state = {}) {
  if (!map) {
    return { id, layerIds };
  }

  const busesOn = Boolean(state?.visible?.[BUSES_ID]);
  const railOn = Boolean(state?.visible?.[RAIL_ID]);

  if (typeof map.getSource === "function") {
    if (!map.getSource(LINES_SOURCE_ID)) {
      map.addSource(LINES_SOURCE_ID, {
        type: "geojson",
        data: emptyFeatureCollection(),
      });
    }
    if (!map.getSource(STATIONS_SOURCE_ID)) {
      map.addSource(STATIONS_SOURCE_ID, {
        type: "geojson",
        data: emptyFeatureCollection(),
      });
    }
    if (!map.getSource(BUSES_SOURCE_ID)) {
      map.addSource(BUSES_SOURCE_ID, {
        type: "geojson",
        data: emptyFeatureCollection(),
      });
    }
  }

  if (typeof map.getLayer === "function") {
    if (!map.getLayer(RAIL_LINES_LAYER_ID)) {
      map.addLayer({
        id: RAIL_LINES_LAYER_ID,
        type: "line",
        source: LINES_SOURCE_ID,
        layout: {
          visibility: railOn ? "visible" : "none",
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": lineColorExpression(),
          "line-width": RAIL_LINE_WIDTH,
          "line-opacity": 0.92,
        },
      });
    }

    if (!map.getLayer(RAIL_STATIONS_LAYER_ID)) {
      map.addLayer({
        id: RAIL_STATIONS_LAYER_ID,
        type: "circle",
        source: STATIONS_SOURCE_ID,
        layout: {
          visibility: railOn ? "visible" : "none",
        },
        paint: {
          "circle-radius": STATION_RADIUS,
          "circle-color": STATION_FILL_COLOR,
          "circle-stroke-color": lineColorExpression(),
          "circle-stroke-width": STATION_STROKE_WIDTH,
        },
      });
    }

    if (!map.getLayer(BUSES_LAYER_ID)) {
      map.addLayer({
        id: BUSES_LAYER_ID,
        type: "circle",
        source: BUSES_SOURCE_ID,
        layout: {
          visibility: busesOn ? "visible" : "none",
        },
        paint: {
          "circle-radius": BUS_RADIUS,
          "circle-color": BUS_COLOR,
          "circle-stroke-color": BUS_STROKE_COLOR,
          "circle-stroke-width": BUS_STROKE_WIDTH,
        },
      });
    }
  }

  // Only call api.transit when a transit sub-layer is actually active (TASKS_A.md A2).
  if (busesOn) {
    startBusPolling(map, api, state);
  } else {
    stopBusPolling(map);
  }

  if (railOn) {
    await loadTransitData(map, api, { updateRail: true, state });
  }

  return { id, layerIds };
}
