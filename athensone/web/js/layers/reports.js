// Citizen reports (Waze pins) layer — always visible on the map, no pill bar chip
// (SPEC.md F3, TASKS_A.md A2, UI/UX upgrade #4: persistent newly submitted pins + pulse ring).
// Never touches document or maplibregl at import time so Node can import it safely.

import { DEMO_FORUM_REPORTS } from "../ui/reportsfeed.js";

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
  pothole: "Λακκούβα",
  sidewalk: "Πεζοδρόμιο",
  lighting: "Φωτισμός",
  streetlight: "Φωτισμός",
  water_leak: "Διαρροή νερού",
  trash: "Απορρίμματα",
});

// Pin visual dimensions for light/dark readability (certainty: design default).
const REPORT_PIN_RADIUS = 8;
const REPORT_STROKE_COLOR = "#ffffff";
const REPORT_STROKE_WIDTH = 2.5;
// Status ring colours (Wave 3; Tailwind green-600 / blue-600, ≥3:1 against the map for a UI component).
const RESOLVED_STROKE_COLOR = "#16a34a";
const IN_PROGRESS_STROKE_COLOR = "#2563eb";
const PULSE_DURATION_MS = 1200;
const PULSE_RIPPLES = 2;

const STATUS_LABELS = Object.freeze({
  submitted: "Νέα αναφορά",
  acknowledged: "Ανατέθηκε",
  received: "Σε εξέλιξη",
  in_progress: "Συνεργείο καθ' οδόν",
  resolved: "Επιλύθηκε",
  rejected: "Απορρίφθηκε",
});

// Per-map store of locally created reports so optimistic pins survive refresh() and style.load.
const localReportsByMap = new WeakMap();
const remoteReportsByMap = new WeakMap();
const pulseCancelByMap = new WeakMap();
const apiByMap = new WeakMap();
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
        // Ring colour tells the case status at a glance (Wave 3): green resolved, blue in progress, else white.
        "circle-stroke-color": [
          "match",
          ["coalesce", ["get", "status"], ""],
          "resolved",
          RESOLVED_STROKE_COLOR,
          "in_progress",
          IN_PROGRESS_STROKE_COLOR,
          REPORT_STROKE_COLOR,
        ],
        "circle-stroke-width": REPORT_STROKE_WIDTH,
      },
    });
  }
}

// Real backend ids only: optimistic ("local-…"), offline ("offline-…"), and demo ("demo-…") pins have no tracker page.
function isTrackableId(value) {
  const s = String(value ?? "");
  return Boolean(s) && !s.startsWith("offline-") && !s.startsWith("local-") && !s.startsWith("demo-");
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
    const statusLabel = STATUS_LABELS[p.status] || STATUS_LABELS.submitted;
    const note = p.note || p.description || "";
    const addr = [p.address, p.neighborhood].filter(Boolean).join(" · ");
    const author = p.author || "";
    const conf = Number(p.confirmations ?? p.upvotes);
    const meta = Number.isFinite(conf) && conf > 0 ? `${conf} επιβεβαιώσεις` : "Χωρίς επιβεβαιώσεις ακόμη";
    const canConfirm = Boolean(p.id && !String(p.id).startsWith("demo-") && apiByMap.get(map)?.api?.confirmReport);
    const trackLink = isTrackableId(p.id)
      ? `<a class="report-pin-popup__track" href="/web/track.html?id=${encodeURIComponent(String(p.id))}">Παρακολούθηση ↗</a>`
      : "";
    const html =
      `<div class="report-pin-popup">` +
      `<strong class="report-pin-popup__title">${escapeHtml(catLabel)}</strong> ` +
      `<span class="report-pin-popup__status report-pin-popup__status--${escapeHtml(p.status || "submitted")}">${escapeHtml(statusLabel)}</span>` +
      (addr ? `<div class="report-pin-popup__meta">📍 ${escapeHtml(addr)}</div>` : "") +
      (author ? `<div class="report-pin-popup__meta">${escapeHtml(author)}</div>` : "") +
      (note ? `<p class="report-pin-popup__note">${escapeHtml(note)}</p>` : "") +
      `<span class="report-pin-popup__meta">${escapeHtml(meta)}</span>` +
      (canConfirm || trackLink
        ? `<div class="report-pin-popup__actions">` +
          (canConfirm ? `<button type="button" class="report-pin-popup__confirm">+1 Επιβεβαίωση</button>` : "") +
          trackLink +
          `</div>`
        : "") +
      `</div>`;
    const popup = new PopupCtor({ className: "glass work-popup" })
      .setLngLat(event.lngLat)
      .setHTML(html)
      .addTo(map);
    const ctx = apiByMap.get(map);
    const btn = popup.getElement?.()?.querySelector?.(".report-pin-popup__confirm");
    if (btn && ctx?.api?.confirmReport && p.id) {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          const res = await ctx.api.confirmReport(p.id);
          const metaEl = popup.getElement?.()?.querySelector?.(".report-pin-popup__meta");
          if (metaEl && typeof res?.confirmations === "number") {
            metaEl.textContent = `${res.confirmations} επιβεβαιώσεις`;
          }
          // +2 for confirming someone else's report: let the Points pill pulse live (Wave 3).
          const bus = ctx?.state?.bus;
          if (Number(res?.points_awarded) > 0 && typeof bus?.dispatchEvent === "function"
              && typeof globalThis.CustomEvent === "function") {
            bus.dispatchEvent(new CustomEvent("points:earned", {
              detail: { delta: Number(res.points_awarded), reason: "Επιβεβαίωση αναφοράς" },
            }));
          }
          await refresh(map, ctx.api, ctx.state);
        } catch {
          btn.disabled = false;
        }
      });
    }
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
  const demoWrapped =
    remoteData.features.length === 0
      ? DEMO_FORUM_REPORTS.map((d) => ({ type: "Feature", id: d.id, geometry: d.geometry, properties: d.properties }))
      : [];
  const withDemo = mergeFeatures(remoteData, demoWrapped);
  remoteReportsByMap.set(map, withDemo);
  const locals = localReportsByMap.get(map) ?? [];
  const merged = mergeFeatures(withDemo, locals);
  setData(map, merged);
  return merged;
}

export function showAllOnMap(map) {
  if (!map) return;
  ensureReportsSourceAndLayer(map);
  if (typeof map.setLayoutProperty === "function" && (typeof map.getLayer !== "function" || map.getLayer(PINS_LAYER_ID))) {
    map.setLayoutProperty(PINS_LAYER_ID, "visibility", "visible");
  }
  const src = typeof map.getSource === "function" ? map.getSource(SOURCE_ID) : null;
  const feats = src?._data?.features ?? src?.data?.features ?? [];
  const pts = feats.map((f) => f?.geometry?.coordinates).filter((c) => Array.isArray(c) && c.length >= 2);
  if (pts.length >= 2 && typeof map.fitBounds === "function") {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const [x, y] of pts) {
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
    map.fitBounds([[minX, minY], [maxX, maxY]], { padding: 72, duration: 700, maxZoom: 15.5 });
  }
}

export async function register(map, api, state = {}) {
  if (!map) {
    return { id, layerIds };
  }

  apiByMap.set(map, { api, state });
  ensureReportsSourceAndLayer(map);
  bindReportPopup(map);

  await refresh(map, api, state);

  return { id, layerIds };
}
