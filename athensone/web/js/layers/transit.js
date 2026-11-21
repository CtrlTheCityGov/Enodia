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

// Smooth bus glide animation duration between 20 s snapshots in ms (source: TASKS_A.md A5, certainty: design default).
export const BUS_ANIMATION_MS = 1000;

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
const busAnimByMap = new WeakMap();
const lastBusesByMap = new WeakMap();
const busPollGenByMap = new WeakMap();
const busesActiveByMap = new WeakMap();
const apiByMap = new WeakMap();
const stationPopupBoundMaps = new WeakSet();

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderStationPopupHtml(name, line, bodyHtml = "") {
  const lineBadge = line ? ` <span class="prov-updated">${escapeHtml(line)}</span>` : "";
  return (
    `<div class="transit-popup">` +
    `<strong class="transit-popup__title">${escapeHtml(name)}</strong>${lineBadge}` +
    bodyHtml +
    `</div>`
  );
}

function formatArrivalsHtml(res) {
  const arrivals = Array.isArray(res?.arrivals) ? res.arrivals : [];
  const rawSrc = String(res?.source ?? "").trim().toLowerCase();
  const provHtml =
    rawSrc === "live"
      ? `<span class="prov-pill prov-pill--live">LIVE</span>`
      : rawSrc === "cache" || rawSrc === "cached"
        ? `<span class="prov-pill prov-pill--cached">CACHED</span>`
        : rawSrc === "mock" || rawSrc === "demo"
          ? `<span class="prov-pill prov-pill--demo">DEMO</span>`
          : "";
  const header = provHtml ? `<div class="work-popup__prov">${provHtml}</div>` : "";
  if (arrivals.length === 0) {
    return `${header}<p class="transit-popup__empty">Δεν υπάρχουν διαθέσιμες αφίξεις.</p>`;
  }
  const items = arrivals
    .filter((a) => a && a.wait_min != null && Number.isFinite(Number(a.wait_min)))
    .slice(0, 6)
    .map((a) => {
      const route = a.line || a.route_code || a.route || a.line_id || "Γραμμή";
      const mins = Math.max(0, Math.round(Number(a.wait_min)));
      return `<li class="transit-popup__item"><span>${escapeHtml(route)}</span><strong>${mins} λεπτά</strong></li>`;
    })
    .join("");
  if (!items) {
    return `${header}<p class="transit-popup__empty">Δεν υπάρχουν διαθέσιμες αφίξεις.</p>`;
  }
  return `${header}<ul class="transit-popup__list">${items}</ul>`;
}

function bindStationPopup(map) {
  if (!map || stationPopupBoundMaps.has(map) || typeof map.on !== "function") {
    return;
  }
  stationPopupBoundMaps.add(map);
  map.on("mouseenter", RAIL_STATIONS_LAYER_ID, () => {
    const canvas = typeof map.getCanvas === "function" ? map.getCanvas() : null;
    if (canvas?.style) canvas.style.cursor = "pointer";
  });
  map.on("mouseleave", RAIL_STATIONS_LAYER_ID, () => {
    const canvas = typeof map.getCanvas === "function" ? map.getCanvas() : null;
    if (canvas?.style) canvas.style.cursor = "";
  });
  map.on("click", RAIL_STATIONS_LAYER_ID, async (event) => {
    const feature = event?.features?.[0];
    const PopupCtor = globalThis.maplibregl?.Popup;
    if (!feature || !event?.lngLat || typeof PopupCtor !== "function") {
      return;
    }
    const p = feature.properties || {};
    const name = p.name || p.title || p.label || "Στάση / Σταθμός";
    const line = p.line || p.ref || "";
    const rawCode = p.stop_code ?? p.stopCode ?? "";
    const stopCode = rawCode != null ? String(rawCode).trim() : "";
    const currentApi = apiByMap.get(map);
    const canFetch = Boolean(stopCode && typeof currentApi?.transitArrivals === "function");

    const initialBody = canFetch
      ? `<p class="transit-popup__loading">Φόρτωση αφίξεων…</p>`
      : "";
    const popup = new PopupCtor({ className: "glass work-popup" })
      .setLngLat(event.lngLat)
      .setHTML(renderStationPopupHtml(name, line, initialBody))
      .addTo(map);

    if (!canFetch) {
      return;
    }
    try {
      const res = await currentApi.transitArrivals(stopCode);
      if (typeof popup.setHTML === "function") {
        popup.setHTML(renderStationPopupHtml(name, line, formatArrivalsHtml(res)));
      }
    } catch {
      if (typeof popup.setHTML === "function") {
        popup.setHTML(renderStationPopupHtml(name, line, `<p class="transit-popup__empty">Μη διαθέσιμες αφίξεις.</p>`));
      }
    }
  });
}

function getBusFeatureId(feature) {
  if (!feature || typeof feature !== "object") {
    return null;
  }
  const raw = feature.properties?.id ?? feature.id;
  if (raw === undefined || raw === null || raw === "") {
    return null;
  }
  return String(raw);
}

function isValidPointCoords(coords) {
  return (
    Array.isArray(coords) &&
    coords.length >= 2 &&
    Number.isFinite(coords[0]) &&
    Number.isFinite(coords[1])
  );
}

// Linearly interpolate bus [lon, lat] positions between snapshots sharing an id/properties.id (TASKS_A.md A5).
export function interpolateBuses(prevFC, nextFC, t) {
  const prev = toFeatureCollection(prevFC);
  const next = toFeatureCollection(nextFC);
  const numericT = Number(t);
  const clampedT = Number.isFinite(numericT) ? Math.max(0, Math.min(1, numericT)) : 1;

  const prevCoordsById = new Map();
  for (const feature of prev.features) {
    const busId = getBusFeatureId(feature);
    if (
      busId !== null &&
      feature?.geometry?.type === "Point" &&
      isValidPointCoords(feature.geometry.coordinates)
    ) {
      prevCoordsById.set(busId, feature.geometry.coordinates);
    }
  }

  const features = next.features.map((feature) => {
    if (
      !feature ||
      feature.geometry?.type !== "Point" ||
      !isValidPointCoords(feature.geometry.coordinates)
    ) {
      return feature;
    }
    const busId = getBusFeatureId(feature);
    const prevCoords = busId !== null ? prevCoordsById.get(busId) : null;
    if (!prevCoords) {
      return feature;
    }
    const [prevLon, prevLat] = prevCoords;
    const [nextLon, nextLat] = feature.geometry.coordinates;
    const lon = prevLon + (nextLon - prevLon) * clampedT;
    const lat = prevLat + (nextLat - prevLat) * clampedT;
    return {
      ...feature,
      geometry: {
        ...feature.geometry,
        coordinates: [lon, lat],
      },
    };
  });

  return {
    type: "FeatureCollection",
    features,
  };
}

function cancelBusAnimation(map) {
  if (!map) {
    return;
  }
  const anim = busAnimByMap.get(map);
  if (!anim) {
    return;
  }
  anim.cancelled = true;
  if (anim.rafId !== null && typeof globalThis.cancelAnimationFrame === "function") {
    globalThis.cancelAnimationFrame(anim.rafId);
  }
  anim.rafId = null;
  busAnimByMap.delete(map);
}

function updateBusesData(map, nextBuses) {
  if (!map || typeof map.getSource !== "function") {
    return;
  }
  const busesSrc = map.getSource(BUSES_SOURCE_ID);
  if (!busesSrc || typeof busesSrc.setData !== "function") {
    return;
  }

  const prevAnim = busAnimByMap.get(map);
  const prevFC = prevAnim?.currentFC ?? lastBusesByMap.get(map) ?? null;
  cancelBusAnimation(map);

  const raf = globalThis.requestAnimationFrame;
  const hasPrev = Boolean(prevFC && Array.isArray(prevFC.features) && prevFC.features.length > 0);
  const hasNext = Boolean(nextBuses && Array.isArray(nextBuses.features) && nextBuses.features.length > 0);

  if (!hasPrev || !hasNext || typeof raf !== "function") {
    lastBusesByMap.set(map, nextBuses);
    busesSrc.setData(nextBuses);
    return;
  }

  const anim = {
    cancelled: false,
    rafId: null,
    startTime: null,
    currentFC: prevFC,
  };
  busAnimByMap.set(map, anim);

  function step(timestamp) {
    if (anim.cancelled || !busesActiveByMap.get(map)) {
      return;
    }
    const now =
      typeof timestamp === "number"
        ? timestamp
        : typeof globalThis.performance?.now === "function"
          ? globalThis.performance.now()
          : Date.now();
    if (anim.startTime === null) {
      anim.startTime = now;
    }
    const elapsed = Math.max(0, now - anim.startTime);
    const progress = Math.min(1, elapsed / BUS_ANIMATION_MS);
    const frameFC = interpolateBuses(prevFC, nextBuses, progress);
    anim.currentFC = frameFC;

    const liveSrc = typeof map.getSource === "function" ? map.getSource(BUSES_SOURCE_ID) : null;
    if (liveSrc && typeof liveSrc.setData === "function") {
      liveSrc.setData(frameFC);
    }

    if (progress < 1) {
      anim.rafId = raf(step);
    } else {
      anim.rafId = null;
      lastBusesByMap.set(map, nextBuses);
      busAnimByMap.delete(map);
    }
  }

  anim.rafId = raf(step);
}

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
    ["coalesce", ["get", "line"], ["get", "id"], ["get", "ref"], ["get", "route_short_name"], ""],
    ["M1", "1", "Γραμμή 1"],
    ATHENS_LINE_COLORS.M1,
    ["M2", "2", "Γραμμή 2"],
    ATHENS_LINE_COLORS.M2,
    ["M3", "3", "Γραμμή 3"],
    ATHENS_LINE_COLORS.M3,
    [
      "PROASTIAKOS",
      "Suburban",
      "suburban",
      "Proastiakos",
      "Προαστιακός",
      "P1",
      "P2",
      "P3",
      "Π1",
      "Π2",
      "Π3",
    ],
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
  // Increment per-poll generation so an older slower bus poll can never overwrite a newer poll (TASKS_A.md A6).
  let busGen = null;
  if (updateBuses) {
    busGen = (busPollGenByMap.get(map) ?? 0) + 1;
    busPollGenByMap.set(map, busGen);
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
    if (updateBuses) {
      if (!busesActiveByMap.get(map) || (busPollGenByMap.get(map) ?? 0) !== busGen) {
        return bundle;
      }
      updateBusesData(map, bundle.buses);
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
  busesActiveByMap.set(map, false);
  busPollGenByMap.set(map, (busPollGenByMap.get(map) ?? 0) + 1);
  cancelBusAnimation(map);
  lastBusesByMap.delete(map);
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
  busesActiveByMap.set(map, true);
  busPollGenByMap.set(map, (busPollGenByMap.get(map) ?? 0) + 1);
  loadTransitData(map, api, { updateBuses: true, state });
  const timerId = setInterval(() => {
    loadTransitData(map, api, { updateBuses: true, state });
  }, BUS_POLL_INTERVAL_MS);
  busPollTimers.set(map, timerId);
}

export function setBusesEnabled(map, apiOrEnabled, enabled, state = null) {
  let api = apiOrEnabled;
  let isOn;
  let activeState = state;
  if (typeof apiOrEnabled === "boolean" && enabled === undefined) {
    api = null;
    isOn = apiOrEnabled;
    activeState = null;
  } else {
    isOn = Boolean(enabled);
  }
  applyVisibility(map, busLayerIds, isOn);
  if (isOn) {
    startBusPolling(map, api, activeState);
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

  apiByMap.set(map, api);
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

  bindStationPopup(map);

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
