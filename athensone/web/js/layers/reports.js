// Citizen reports (Waze pins) layer — always visible on the map, no pill bar chip
// (SPEC.md F3, TASKS_A.md A2, UI/UX upgrade #4: persistent newly submitted pins + pulse ring).
// Never touches document or maplibregl at import time so Node can import it safely.

// Layer id from TASKS_A.md A2 (certainty: verified).
export const id = "reports";

// Greek label for citizen reports (source: SPEC.md F3 "Αναφορές πολιτών", certainty: verified).
export const label = "Αναφορές";

// MapLibre source and layer identifiers for always-on report pins (certainty: design default).
export const SOURCE_ID = "reports-source";
export const PINS_LAYER_ID = "reports-pins";
const PULSE_SOURCE_ID = "reports-pulse-source";
const PULSE_LAYER_ID = "reports-pulse";

// MapLibre layer ids added by this module (TASKS_A.md A2, certainty: verified).
export const layerIds = [PINS_LAYER_ID];

// Category pin colors matching SPEC.md F3 categories (certainty: design default).
const REPORT_COLORS = Object.freeze({
  traffic: "#ef4444",
  congestion: "#ef4444",
  incident: "#dc2626",
  obstacle: "#f59e0b",
  damage: "#a855f7",
  work_progress: "#2563eb",
  default: "#f97316",
});

// Greek labels for clicked report pin popups (source: SPEC.md F3; certainty: verified).
const CATEGORY_LABELS = Object.freeze({
  congestion: "Συμφόρηση",
  traffic: "Συμφόρηση",
  incident: "Συμβάν",
  obstacle: "Εμπόδιο",
  damage: "Ζημιά",
  work_progress: "Πρόοδος έργου",
});

// Pin visual dimensions for light/dark readability (certainty: design default).
const REPORT_PIN_RADIUS = 8;
const REPORT_STROKE_COLOR = "#ffffff";
const REPORT_STROKE_WIDTH = 2.5;
const PULSE_DURATION_MS = 1200;
const PULSE_RIPPLES = 2;

// Per-map store of locally created reports so optimistic pins survive refresh() and style.load.
const localReportsByMap = new WeakMap();
const remoteReportsByMap = new WeakMap();
const pulseCancelByMap = new WeakMap();
const popupBoundMaps = new WeakSet();

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

function featureKey(feature) {
  const raw = feature?.properties?.id ?? feature?.id;
  if (raw !== undefined && raw !== null && raw !== "") {
    return `id:${String(raw)}`;
  }
  const c = feature?.geometry?.coordinates;
  const cat = feature?.properties?.category ?? "";
  if (Array.isArray(c) && c.length >= 2) {
    return `pt:${Number(c[0]).toFixed(4)},${Number(c[1]).toFixed(4)}:${cat}`;
  }
  return null;
}

function mergeFeatures(remoteFC, localList) {
  const remote = toFeatureCollection(remoteFC).features;
  if (!Array.isArray(localList) || localList.length === 0) {
    return { type: "FeatureCollection", features: [...remote] };
  }
  const seen = new Set();
  const merged = [];
  for (const f of remote) {
    const k = featureKey(f);
    if (k) seen.add(k);
    merged.push(f);
  }
  for (const f of localList) {
    const k = featureKey(f);
    if (k && seen.has(k)) continue;
    if (k) seen.add(k);
    merged.push(f);
  }
  return { type: "FeatureCollection", features: merged };
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

function ensureReportsSourceAndLayer(map) {
  if (!map) {
    return;
  }
  if (typeof map.getSource === "function" && !map.getSource(SOURCE_ID) && typeof map.addSource === "function") {
    map.addSource(SOURCE_ID, {
      type: "geojson",
      data: emptyFeatureCollection(),
    });
  }

  if (typeof map.getLayer === "function" && !map.getLayer(PINS_LAYER_ID) && typeof map.addLayer === "function") {
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
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function bindReportPopup(map) {
  if (!map || popupBoundMaps.has(map) || typeof map.on !== "function") {
    return;
  }
  popupBoundMaps.add(map);
  map.on("mouseenter", PINS_LAYER_ID, () => {
    const canvas = typeof map.getCanvas === "function" ? map.getCanvas() : null;
    if (canvas?.style) canvas.style.cursor = "pointer";
  });
  map.on("mouseleave", PINS_LAYER_ID, () => {
    const canvas = typeof map.getCanvas === "function" ? map.getCanvas() : null;
    if (canvas?.style) canvas.style.cursor = "";
  });
  map.on("click", PINS_LAYER_ID, (event) => {
    const feature = event?.features?.[0];
    const PopupCtor = globalThis.maplibregl?.Popup;
    if (!feature || !event?.lngLat || typeof PopupCtor !== "function") {
      return;
    }
    const p = feature.properties || {};
    const catLabel = CATEGORY_LABELS[p.category] || p.category || "Αναφορά";
    const note = p.note || p.description || "";
    const conf = Number(p.confirmations);
    const meta = Number.isFinite(conf) && conf > 0 ? `${conf} επιβεβαιώσεις` : "Νέα αναφορά";
    const html =
      `<div class="report-pin-popup">` +
      `<strong class="report-pin-popup__title">${escapeHtml(catLabel)}</strong>` +
      (note ? `<p class="report-pin-popup__note">${escapeHtml(note)}</p>` : "") +
      `<span class="report-pin-popup__meta">${escapeHtml(meta)}</span>` +
      `</div>`;
    new PopupCtor({ className: "glass work-popup" })
      .setLngLat(event.lngLat)
      .setHTML(html)
      .addTo(map);
  });
}

function playPinPulse(map, lon, lat, category) {
  if (!map || typeof map.getSource !== "function" || typeof map.addSource !== "function") {
    return;
  }
  const prevCancel = pulseCancelByMap.get(map);
  if (typeof prevCancel === "function") {
    prevCancel();
  }

  const color = REPORT_COLORS[category] || REPORT_COLORS.default;
  const fc = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { category },
        geometry: { type: "Point", coordinates: [lon, lat] },
      },
    ],
  };

  const existingSrc = map.getSource(PULSE_SOURCE_ID);
  if (existingSrc && typeof existingSrc.setData === "function") {
    existingSrc.setData(fc);
  } else {
    map.addSource(PULSE_SOURCE_ID, { type: "geojson", data: fc });
  }

  if (typeof map.getLayer === "function" && !map.getLayer(PULSE_LAYER_ID) && typeof map.addLayer === "function") {
    map.addLayer({
      id: PULSE_LAYER_ID,
      type: "circle",
      source: PULSE_SOURCE_ID,
      paint: {
        "circle-radius": 8,
        "circle-color": color,
        "circle-opacity": 0.65,
        "circle-stroke-color": color,
        "circle-stroke-width": 2,
        "circle-stroke-opacity": 0.9,
      },
    });
  } else if (typeof map.setPaintProperty === "function") {
    map.setPaintProperty(PULSE_LAYER_ID, "circle-color", color);
    map.setPaintProperty(PULSE_LAYER_ID, "circle-stroke-color", color);
  }

  const raf = globalThis.requestAnimationFrame;
  const cancelRaf = globalThis.cancelAnimationFrame;
  if (typeof raf !== "function") {
    return;
  }

  let cancelled = false;
  let rafId = null;
  let start = null;
  const totalMs = PULSE_DURATION_MS * PULSE_RIPPLES;

  function step(ts) {
    if (cancelled) return;
    const now = typeof ts === "number" ? ts : Date.now();
    if (start === null) start = now;
    const elapsed = now - start;
    if (elapsed >= totalMs) {
      const src = map.getSource(PULSE_SOURCE_ID);
      if (src && typeof src.setData === "function") {
        src.setData(emptyFeatureCollection());
      }
      pulseCancelByMap.delete(map);
      return;
    }
    const cycleT = (elapsed % PULSE_DURATION_MS) / PULSE_DURATION_MS;
    const eased = 1 - (1 - cycleT) ** 3;
    if (typeof map.setPaintProperty === "function" && map.getLayer?.(PULSE_LAYER_ID)) {
      map.setPaintProperty(PULSE_LAYER_ID, "circle-radius", 8 + eased * 28);
      map.setPaintProperty(PULSE_LAYER_ID, "circle-opacity", 0.5 * (1 - eased));
      map.setPaintProperty(PULSE_LAYER_ID, "circle-stroke-opacity", 0.9 * (1 - eased));
    }
    rafId = raf(step);
  }

  rafId = raf(step);
  pulseCancelByMap.set(map, () => {
    cancelled = true;
    if (rafId !== null && typeof cancelRaf === "function") {
      cancelRaf(rafId);
    }
  });
}

export function setData(map, geojson) {
  const src = map && typeof map.getSource === "function" ? map.getSource(SOURCE_ID) : null;
  if (src && typeof src.setData === "function") {
    src.setData(toFeatureCollection(geojson));
  }
}

// Immediately append a newly created citizen report pin to the map source, force layer visible,
// persist it across refreshes/style reloads, and play a pulsing ring animation (UI/UX upgrade #4).
export function addReportPin(map, detail) {
  if (!map || !detail || typeof detail !== "object") {
    return null;
  }
  const lon = Number(detail.lon ?? detail.lng);
  const lat = Number(detail.lat);
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
    return null;
  }

  const feature = {
    type: "Feature",
    id: detail.id || `local-${Date.now()}`,
    geometry: {
      type: "Point",
      coordinates: [lon, lat],
    },
    properties: {
      id: detail.id || `local-${Date.now()}`,
      category: detail.category || "incident",
      note: detail.note || "",
      created_at: detail.created_at || new Date().toISOString(),
      confirmations: detail.confirmations ?? 1,
      work_id: detail.work_id ?? null,
    },
  };

  ensureReportsSourceAndLayer(map);
  if (typeof map.setLayoutProperty === "function" && (typeof map.getLayer !== "function" || map.getLayer(PINS_LAYER_ID))) {
    map.setLayoutProperty(PINS_LAYER_ID, "visibility", "visible");
  }

  const locals = localReportsByMap.get(map) ?? [];
  const key = featureKey(feature);
  const nextLocals = locals.filter((f) => featureKey(f) !== key);
  nextLocals.push(feature);
  localReportsByMap.set(map, nextLocals);

  const existingSrc = typeof map.getSource === "function" ? map.getSource(SOURCE_ID) : null;
  const baseFC = remoteReportsByMap.get(map) ?? existingSrc?.data ?? emptyFeatureCollection();
  const merged = mergeFeatures(baseFC, nextLocals);
  setData(map, merged);
  playPinPulse(map, lon, lat, feature.properties.category);

  return feature;
}

export async function refresh(map, api, state = {}) {
  if (!map) {
    return emptyFeatureCollection();
  }
  const remoteData = await loadReportsData(map, api, state);
  remoteReportsByMap.set(map, remoteData);
  const locals = localReportsByMap.get(map) ?? [];
  const merged = mergeFeatures(remoteData, locals);
  setData(map, merged);
  return merged;
}

export async function register(map, api, state = {}) {
  if (!map) {
    return { id, layerIds };
  }

  ensureReportsSourceAndLayer(map);
  bindReportPopup(map);

  await refresh(map, api, state);

  return { id, layerIds };
}
