// Transit layer: OASA live buses (20 s polling only while on) + Metro/Suburban lines & stations
// (SPEC.md F2, "Εξωτερικές πηγές", TASKS_A.md A2), plus Wave 1: station labels, bus labels + popup,
// per-line filters for the transit menu (ui/transitmenu.js) and a "transit:updated" event on state.bus.
// Never touches document or maplibregl at import time so Node can import it safely.
// All data comes through api.js (api.transit / api.transitArrivals); this file never does network I/O itself.

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

// Athens Metro & Suburban display colours, kept identical to app/transit_src.py LINE_COLORS so the map,
// the station dots and the transit menu agree (Wave 1 card; STASY branding approximated, certainty: design default).
export const ATHENS_LINE_COLORS = Object.freeze({
  M1: "#007a33", // Line 1 (ISAP) green
  M2: "#dc2626", // Line 2 red
  M3: "#0066b3", // Line 3 blue
  Suburban: "#eab308", // Proastiakos / Suburban rail yellow (A1–A4)
  default: "#6b7280", // Neutral fallback for unrecognized line codes (certainty: design default)
});

// Bus / trolley marker fills. Both pass WCAG AA (>4.5:1) against the white line label halo-free text:
// #0369a1 ≈ 5.9:1, #c2410c ≈ 5.2:1 with #ffffff (computed with the WCAG 2.x formula; certainty: sure).
export const BUS_COLOR = "#0369a1";
export const TROLLEY_COLOR = "#c2410c";

// MapLibre source and layer identifiers for transit sub-groups (certainty: design default).
const LINES_SOURCE_ID = "transit-lines-source";
const STATIONS_SOURCE_ID = "transit-stations-source";
const BUSES_SOURCE_ID = "transit-buses-source";
const BUS_ROUTES_SOURCE_ID = "transit-bus-routes-source";

const RAIL_LINES_LAYER_ID = "transit-rail-lines";
const RAIL_STATIONS_LAYER_ID = "transit-rail-stations";
const RAIL_LABELS_LAYER_ID = "transit-rail-labels";
const BUS_ROUTES_LAYER_ID = "transit-bus-routes";
const BUSES_LAYER_ID = "transit-buses";
const BUSES_LABELS_LAYER_ID = "transit-buses-labels";

// Separate toggleable layer id lists for the two transit chips (TASKS_A.md A2, certainty: verified).
export const busLayerIds = [BUS_ROUTES_LAYER_ID, BUSES_LAYER_ID, BUSES_LABELS_LAYER_ID];
export const railLayerIds = [RAIL_LINES_LAYER_ID, RAIL_STATIONS_LAYER_ID, RAIL_LABELS_LAYER_ID];

// All MapLibre layer ids added by this module (TASKS_A.md A2, certainty: verified).
export const layerIds = [...railLayerIds, ...busLayerIds];

// Visual styling constants for rail lines, stations, and buses (certainty: design default).
const RAIL_LINE_WIDTH = 4;
const STATION_RADIUS = 5.5;
const STATION_FILL_COLOR = "#ffffff";
const STATION_STROKE_WIDTH = 3;
const BUS_RADIUS = 10;
const BUS_STROKE_COLOR = "#ffffff";
const BUS_STROKE_WIDTH = 2.5;
// Station names appear from zoom 13 so the city-wide view stays clean (design default).
const RAIL_LABELS_MINZOOM = 13;
// OpenFreeMap styles (liberty / fiord) serve Noto Sans glyphs; this font name is unverified offline,
// a missing glyph only hides the label, the map keeps working (certainty: unverified).
// Verified by Antigravity against the live styles (22 Nov 2026): liberty serves Noto Sans Bold + Regular,
// fiord (dark) only Noto Sans Regular, so Regular is the fallback in the stack (certainty: verified).
const LABEL_FONT = ["Noto Sans Bold"];

const busPollTimers = new WeakMap();
const busAnimByMap = new WeakMap();
const lastBusesByMap = new WeakMap();
const busPollGenByMap = new WeakMap();
const busesActiveByMap = new WeakMap();
const apiByMap = new WeakMap();
const stationPopupBoundMaps = new WeakSet();
const busPopupBoundMaps = new WeakSet();
const busPopupByMap = new WeakMap();
const snapshotByMap = new WeakMap();
const filterByMap = new WeakMap();

// ------------------------------------------------------------------ pure helpers

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// "Μ1" (Greek capital Mu, U+039C) -> "M1", "Α2" (Greek Alpha) -> "A2", "Π1" -> "P1"; upper-case Latin key.
export function canonicalLine(ref) {
  return String(ref ?? "")
    .trim()
    .replace(/Μ/g, "M")
    .replace(/Α/g, "A")
    .replace(/Π/g, "P")
    .toUpperCase();
}

// Display colour for a Metro / Suburban ref in Greek or Latin letters.
export function lineColorForRef(ref, fallback = ATHENS_LINE_COLORS.default) {
  const key = canonicalLine(ref);
  if (key === "M1") return ATHENS_LINE_COLORS.M1;
  if (key === "M2") return ATHENS_LINE_COLORS.M2;
  if (key === "M3") return ATHENS_LINE_COLORS.M3;
  const raw = String(ref ?? "").toLowerCase();
  if (/^(A[1-4]|P[1-3])$/.test(key) || /suburban|proastiakos|προαστ/.test(raw)) {
    return ATHENS_LINE_COLORS.Suburban;
  }
  return isHexColor(fallback) ? fallback : ATHENS_LINE_COLORS.default;
}

function isHexColor(value) {
  return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);
}

// Black or white badge text for a hex background, whichever passes WCAG AA (relative luminance threshold).
export function badgeTextColor(hex) {
  if (!isHexColor(hex)) return "#ffffff";
  const ch = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const lum = 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  // White wins while its contrast (1.05 / (lum + 0.05)) beats black's ((lum + 0.05) / 0.05).
  return 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.05 ? "#ffffff" : "#0f172a";
}

export function busColorForMode(mode) {
  return mode === "trolley" ? TROLLEY_COLOR : BUS_COLOR;
}

function lineBadgeHtml(ref, color) {
  const bg = isHexColor(color) ? color : lineColorForRef(ref);
  return (
    `<span class="transit-badge" style="background:${bg};color:${badgeTextColor(bg)}">` +
    `${escapeHtml(ref)}</span>`
  );
}

// LIVE / CACHED / DEMO pill from an api.js source ("live" | "cache" | "mock"), or the backend's
// "snapshot" (served as cached) (SPEC "Mock data is labelled"). Unknown sources render nothing.
export function provenancePillHtml(source) {
  const raw = String(source ?? "").trim().toLowerCase();
  if (raw === "live") return `<span class="prov-pill prov-pill--live">LIVE</span>`;
  if (raw === "cache" || raw === "cached" || raw === "snapshot") {
    return `<span class="prov-pill prov-pill--cached">CACHED</span>`;
  }
  if (raw === "mock" || raw === "demo" || raw === "seed") {
    return `<span class="prov-pill prov-pill--demo">DEMO</span>`;
  }
  return "";
}

// Local Athens time for an ISO timestamp ("20:54:04"); the raw text if it cannot be parsed.
export function formatTimeEl(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  try {
    return d.toLocaleTimeString("el-GR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: "Europe/Athens",
    });
  } catch {
    return d.toISOString().slice(11, 19);
  }
}

// Greek 8-point compass label for a heading in degrees; null when the heading is unknown (never guessed).
export function compassEl(bearing) {
  if (bearing === null || bearing === undefined || bearing === "") return null;
  const b = Number(bearing);
  if (!Number.isFinite(b)) return null;
  const names = ["Β", "ΒΑ", "Α", "ΝΑ", "Ν", "ΝΔ", "Δ", "ΒΔ"];
  return names[Math.round((((b % 360) + 360) % 360) / 45) % 8];
}

function stationLines(props) {
  const p = props || {};
  let lines = p.lines;
  if (typeof lines === "string") {
    // GeoJSON sources hand back array properties as JSON strings on click (MapLibre behaviour).
    const rawText = lines;
    try {
      lines = JSON.parse(rawText);
    } catch {
      lines = null;
    }
    if (!Array.isArray(lines)) lines = rawText.trim() ? [rawText.trim()] : [];
  }
  const out = Array.isArray(lines) ? lines.filter((x) => x !== null && x !== undefined && x !== "").map(String) : [];
  const primary = p.primary_line || p.line || p.ref || "";
  if (primary && !out.includes(String(primary))) out.unshift(String(primary));
  return out;
}

// Station feature -> copy with primary_line, lines, line_keys ("|M2|A1|") and a palette colour.
export function normalizeStation(feature) {
  if (!feature || typeof feature !== "object") return feature;
  const props = { ...(feature.properties || {}) };
  const lines = stationLines(props);
  const primary = String(props.line || props.ref || lines[0] || "");
  props.lines = lines;
  props.primary_line = primary;
  props.line_keys = `|${lines.map(canonicalLine).join("|")}|`;
  props.color = primary ? lineColorForRef(primary, props.color) : isHexColor(props.color) ? props.color : ATHENS_LINE_COLORS.default;
  return { ...feature, properties: props };
}

// Line feature -> copy with line_key ("M1", "A3") used by the per-line filter.
export function normalizeLine(feature) {
  if (!feature || typeof feature !== "object") return feature;
  const props = { ...(feature.properties || {}) };
  props.line_key = canonicalLine(props.ref ?? props.line ?? props.id ?? props.route_short_name ?? "");
  return { ...feature, properties: props };
}

// Bus feature -> copy with id, string line and mode, so interpolation and labels always have keys.
export function normalizeBus(feature) {
  if (!feature || typeof feature !== "object") return feature;
  const props = { ...(feature.properties || {}) };
  if (props.line !== undefined && props.line !== null) props.line = String(props.line);
  if (!props.mode) props.mode = props.line === "2" ? "trolley" : "bus";
  if (props.id === undefined || props.id === null || props.id === "") {
    const fallbackId = props.vehicle_id ?? feature.id;
    if (fallbackId !== undefined && fallbackId !== null && fallbackId !== "") props.id = String(fallbackId);
  }
  return { ...feature, properties: props };
}

function mapFeatures(fc, fn) {
  const src = toFeatureCollection(fc);
  return { type: "FeatureCollection", features: src.features.map(fn) };
}

function geometryBbox(geometry) {
  const pts = [];
  const walk = (c) => {
    if (!Array.isArray(c)) return;
    if (typeof c[0] === "number" && typeof c[1] === "number") {
      pts.push(c);
      return;
    }
    for (const x of c) walk(x);
  };
  walk(geometry?.coordinates);
  if (pts.length === 0) return null;
  let [w, s, e, n] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y] of pts) {
    if (x < w) w = x;
    if (y < s) s = y;
    if (x > e) e = x;
    if (y > n) n = y;
  }
  return [w, s, e, n];
}

function mergeBbox(a, b) {
  if (!a) return b;
  if (!b) return a;
  return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])];
}

// Menu catalog from a bundle when the backend gave no `routes` (offline mock): Metro / Suburban lines
// from line features, OASA routes grouped from the live bus features.
export function deriveRoutesCatalog(bundle) {
  const lines = toFeatureCollection(bundle?.lines).features;
  const stations = toFeatureCollection(bundle?.stations).features;
  const buses = toFeatureCollection(bundle?.buses).features;

  const stationCounts = new Map();
  for (const st of stations) {
    for (const ref of stationLines(st?.properties)) {
      const key = canonicalLine(ref);
      stationCounts.set(key, (stationCounts.get(key) ?? 0) + 1);
    }
  }

  const railByKey = new Map();
  for (const f of lines) {
    const p = f?.properties || {};
    const ref = String(p.ref ?? p.line ?? p.id ?? "");
    const key = canonicalLine(ref);
    if (!key) continue;
    const prev = railByKey.get(key);
    const bbox = geometryBbox(f?.geometry);
    if (prev) {
      prev.bbox = mergeBbox(prev.bbox, bbox);
      continue;
    }
    railByKey.set(key, {
      ref,
      name: String(p.name || ref),
      color: lineColorForRef(ref, p.color),
      station_count: stationCounts.get(key) ?? 0,
      bbox,
      _metro: p.mode === "subway" || key.startsWith("M"),
    });
  }
  const metro = [];
  const suburban = [];
  for (const entry of [...railByKey.values()].sort((a, b) => canonicalLine(a.ref).localeCompare(canonicalLine(b.ref)))) {
    const { _metro, ...clean } = entry;
    (_metro ? metro : suburban).push(clean);
  }

  const busByRoute = new Map();
  for (const f of buses) {
    const p = f?.properties || {};
    const rc = String(p.route_code ?? p.line ?? "");
    if (!rc) continue;
    const coords = f?.geometry?.coordinates;
    const ptBbox = Array.isArray(coords) && coords.length >= 2 ? [coords[0], coords[1], coords[0], coords[1]] : null;
    const prev = busByRoute.get(rc);
    if (prev) {
      prev.active_vehicles += 1;
      prev.bbox = mergeBbox(prev.bbox, ptBbox);
      continue;
    }
    const line = String(p.line ?? rc);
    busByRoute.set(rc, {
      route_code: rc,
      line,
      name: String(p.route_name || ""),
      mode: p.mode || (line === "2" ? "trolley" : "bus"),
      active_vehicles: 1,
      bbox: ptBbox,
    });
  }
  return { metro, suburban, buses: [...busByRoute.values()] };
}

function routesFromResponse(payload, bundle) {
  const r = payload?.routes;
  if (r && typeof r === "object" && (Array.isArray(r.metro) || Array.isArray(r.suburban) || Array.isArray(r.buses))) {
    return {
      metro: Array.isArray(r.metro) ? r.metro : [],
      suburban: Array.isArray(r.suburban) ? r.suburban : [],
      buses: Array.isArray(r.buses) ? r.buses : [],
    };
  }
  return deriveRoutesCatalog(bundle);
}

// ------------------------------------------------------------------ popups

function renderStationPopupHtml(name, linesOrLine, bodyHtml = "", extras = {}) {
  const lines = Array.isArray(linesOrLine) ? linesOrLine : linesOrLine ? [linesOrLine] : [];
  const badges = lines.length
    ? `<div class="transit-popup__badges">${lines.map((ref) => lineBadgeHtml(ref, lineColorForRef(ref))).join("")}</div>`
    : "";
  const elevator =
    extras.elevator === true || extras.elevator === "true"
      ? `<div class="transit-popup__access"><span class="transit-access-badge">♿ Ανελκυστήρας</span></div>`
      : "";
  return (
    `<div class="transit-popup">` +
    `<strong class="transit-popup__title">${escapeHtml(name)}</strong>` +
    badges +
    elevator +
    bodyHtml +
    `</div>`
  );
}

function formatArrivalsHtml(res) {
  const arrivals = Array.isArray(res?.arrivals) ? res.arrivals : [];
  const provHtml = provenancePillHtml(res?.source);
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

function scheduleFallbackHtml(map, lines, lngLat) {
  const refs = Array.isArray(lines) ? lines.map((l) => String(l).toUpperCase()) : [];
  const isProastiakos = refs.some((r) => r.includes("Π") || r.includes("SUB") || r.includes("PRO"));
  const hasMetro = refs.some((r) => /^Μ?[123]$/.test(r) || r.startsWith("M"));
  const items = [];
  if (hasMetro) {
    items.push(`<li class="transit-popup__item"><span>Μετρό ΣΤΑΣΥ</span><strong>κάθε 4–7 λεπτά (05:30–00:30)</strong></li>`);
  }
  if (isProastiakos) {
    items.push(`<li class="transit-popup__item"><span>Προαστιακός</span><strong>κάθε 15–30 λεπτά (05:00–23:30)</strong></li>`);
  }
  // Show up to 3 nearby live OASA buses from the buses GeoJSON source.
  const busSrc = typeof map?.getSource === "function" ? map.getSource(BUSES_SOURCE_ID) : null;
  const busFeatures = busSrc?._data?.features || busSrc?.data?.features || [];
  if (Array.isArray(busFeatures) && busFeatures.length > 0 && lngLat) {
    const nearby = [];
    for (const bf of busFeatures) {
      const c = bf?.geometry?.coordinates;
      if (!Array.isArray(c) || c.length < 2) continue;
      const dKm = Math.hypot((c[0] - lngLat.lng) * 88, (c[1] - lngLat.lat) * 111.3);
      if (dKm <= 1.8) {
        nearby.push({ dM: Math.round(dKm * 1000), p: bf.properties || {} });
      }
    }
    nearby.sort((a, b) => a.dM - b.dM);
    for (const n of nearby.slice(0, 3)) {
      const line = n.p.line || n.p.route_code || "ΟΑΣΑ";
      items.push(`<li class="transit-popup__item"><span>Λεωφ. ${escapeHtml(line)} (ζωντανό)</span><strong>~${n.dM} m</strong></li>`);
    }
  }
  if (!items.length) return "";
  return `<ul class="transit-popup__list">${items.join("")}</ul>`;
}

function setCursor(map, value) {
  const canvas = typeof map.getCanvas === "function" ? map.getCanvas() : null;
  if (canvas?.style) canvas.style.cursor = value;
}

function bindStationPopup(map) {
  if (!map || stationPopupBoundMaps.has(map) || typeof map.on !== "function") {
    return;
  }
  stationPopupBoundMaps.add(map);
  // The station name label is clickable too (Wave 1 review): same handlers on both layers.
  for (const layerId of [RAIL_STATIONS_LAYER_ID, RAIL_LABELS_LAYER_ID]) {
    map.on("mouseenter", layerId, () => setCursor(map, "pointer"));
    map.on("mouseleave", layerId, () => setCursor(map, ""));
    map.on("click", layerId, onStationClick);
  }

  async function onStationClick(event) {
    const feature = event?.features?.[0];
    const PopupCtor = globalThis.maplibregl?.Popup;
    if (!feature || !event?.lngLat || typeof PopupCtor !== "function") {
      return;
    }
    const p = feature.properties || {};
    const name = p.name || p.title || p.label || "Στάση / Σταθμός";
    const lines = stationLines(p);
    const extras = { elevator: p.elevator };
    const rawCode = p.stop_code ?? p.stopCode ?? "";
    const stopCode = rawCode != null ? String(rawCode).trim() : "";
    const currentApi = apiByMap.get(map);
    const canLoad = Boolean(stopCode && typeof currentApi?.transitArrivals === "function");

    const initialBody = canLoad
      ? `<p class="transit-popup__loading">Φόρτωση αφίξεων…</p>`
      : scheduleFallbackHtml(map, lines, event.lngLat);
    const popup = new PopupCtor({ className: "glass work-popup" })
      .setLngLat(event.lngLat)
      .setHTML(renderStationPopupHtml(name, lines, initialBody, extras))
      .addTo(map);

    if (!canLoad) {
      return;
    }
    try {
      const res = await currentApi.transitArrivals(stopCode);
      if (typeof popup.setHTML === "function") {
        popup.setHTML(renderStationPopupHtml(name, lines, formatArrivalsHtml(res), extras));
      }
    } catch {
      if (typeof popup.setHTML === "function") {
        popup.setHTML(
          renderStationPopupHtml(name, lines, `<p class="transit-popup__empty">Μη διαθέσιμες αφίξεις.</p>`, extras),
        );
      }
    }
  }
}

// Bus popup HTML: line badge, Greek route name, vehicle, heading, next stop/ETA, update time, provenance.
// Unknown values show as «άγνωστο» (CLAUDE.md: never 0 or a made-up value).
export function renderBusPopupHtml(props = {}, source = "") {
  const p = props || {};
  const line = String(p.line ?? p.route_code ?? "");
  const mode = p.mode || (line === "2" ? "trolley" : "bus");
  const modeLabel = mode === "trolley" ? "Τρόλεϊ" : "Λεωφορείο";
  const color = busColorForMode(mode);
  const rows = [];
  const row = (k, v) =>
    rows.push(`<li class="transit-popup__item"><span>${escapeHtml(k)}</span><strong>${escapeHtml(v)}</strong></li>`);

  row("Δρομολόγιο", p.route_name || "άγνωστο");
  row("Όχημα", p.vehicle_id || "άγνωστο");
  const compass = compassEl(p.bearing);
  row("Κατεύθυνση", compass ? `${compass} (${Math.round(Number(p.bearing))}°)` : "άγνωστη");
  if (p.next_stop) row("Επόμενη στάση", p.next_stop);
  if (p.eta_min !== undefined && p.eta_min !== null && p.eta_min !== "" && Number.isFinite(Number(p.eta_min))) {
    row("Άφιξη σε", `${Math.max(0, Math.round(Number(p.eta_min)))} λεπτά`);
  }
  const updated = formatTimeEl(p.updated_at);
  const prov = provenancePillHtml(source);
  const provRow =
    prov || updated
      ? `<div class="work-popup__prov">${prov}${updated ? `<span class="prov-updated">Ενημέρωση ${escapeHtml(updated)}</span>` : ""}</div>`
      : "";
  return (
    `<div class="transit-popup transit-popup--bus">` +
    `<div class="transit-popup__head">${lineBadgeHtml(line || "?", color)}` +
    `<strong class="transit-popup__title">${modeLabel} ${escapeHtml(line)}</strong></div>` +
    provRow +
    `<ul class="transit-popup__list">${rows.join("")}</ul>` +
    `</div>`
  );
}

function showBusPopup(map, lngLat, props) {
  const PopupCtor = globalThis.maplibregl?.Popup;
  if (!map || !lngLat || typeof PopupCtor !== "function") return null;
  const prev = busPopupByMap.get(map);
  if (prev && typeof prev.remove === "function") prev.remove();
  const source = snapshotByMap.get(map)?.source ?? "";
  const popup = new PopupCtor({ className: "glass work-popup transit-bus-popup", offset: 14 })
    .setLngLat(lngLat)
    .setHTML(renderBusPopupHtml(props, source))
    .addTo(map);
  busPopupByMap.set(map, popup);
  return popup;
}

function bindBusPopup(map) {
  if (!map || busPopupBoundMaps.has(map) || typeof map.on !== "function") {
    return;
  }
  busPopupBoundMaps.add(map);
  const onBusClick = (event) => {
    const feature = event?.features?.[0];
    if (!feature) return;
    const coords = feature.geometry?.coordinates;
    const lngLat = Array.isArray(coords) && coords.length >= 2 ? coords : event?.lngLat;
    showBusPopup(map, lngLat, feature.properties || {});
  };
  // Clicking the line number label ("608", "Χ95") opens the same popup as the marker (Wave 1 review).
  for (const layerId of [BUSES_LAYER_ID, BUSES_LABELS_LAYER_ID]) {
    map.on("mouseenter", layerId, () => setCursor(map, "pointer"));
    map.on("mouseleave", layerId, () => setCursor(map, ""));
    map.on("click", layerId, onBusClick);
  }
}

// Open the bus popup for a vehicle from the last snapshot (used by the transit menu after flying to it).
export function openBusPopup(map, busIdOrFeature) {
  let feature = busIdOrFeature && typeof busIdOrFeature === "object" ? busIdOrFeature : null;
  if (!feature) {
    const wanted = String(busIdOrFeature ?? "");
    const buses = toFeatureCollection(snapshotByMap.get(map)?.buses).features;
    feature = buses.find((f) => getBusFeatureId(f) === wanted) ?? null;
  }
  const coords = feature?.geometry?.coordinates;
  if (!isValidPointCoords(coords)) return null;
  return showBusPopup(map, coords, feature.properties || {});
}

// ------------------------------------------------------------------ bus animation

// Stable key for a bus between polls: OASA vehicle_id first, then properties.id, then feature.id.
function getBusFeatureId(feature) {
  if (!feature || typeof feature !== "object") {
    return null;
  }
  const raw = feature.properties?.vehicle_id ?? feature.properties?.id ?? feature.id;
  if (raw === undefined || raw === null || raw === "") {
    return null;
  }
  return String(raw);
}

export { getBusFeatureId };

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

// ------------------------------------------------------------------ data loading

function emptyFeatureCollection() {
  return { type: "FeatureCollection", features: [] };
}

function toFeatureCollection(value) {
  if (value && value.type === "FeatureCollection" && Array.isArray(value.features)) {
    return value;
  }
  return emptyFeatureCollection();
}

function responsePayload(res) {
  return res && res.data && typeof res.data === "object" ? res.data : res;
}

function toTransitBundle(res) {
  const payload = responsePayload(res);
  return {
    lines: mapFeatures(payload?.lines, normalizeLine),
    stations: mapFeatures(payload?.stations, normalizeStation),
    buses: mapFeatures(payload?.buses, normalizeBus),
  };
}

// Colour for rail lines and station strokes. The input coalesce keeps "id" (A6 contract); both Greek
// (U+039C "Μ", U+0391 "Α") and Latin refs map to the same colour. Match labels must be unique.
function lineColorExpression() {
  return [
    "match",
    [
      "coalesce",
      ["get", "primary_line"],
      ["get", "line"],
      ["get", "id"],
      ["get", "ref"],
      ["get", "route_short_name"],
      "",
    ],
    ["M1", "Μ1", "1", "Γραμμή 1"],
    ATHENS_LINE_COLORS.M1,
    ["M2", "Μ2", "2", "Γραμμή 2"],
    ATHENS_LINE_COLORS.M2,
    ["M3", "Μ3", "3", "Γραμμή 3"],
    ATHENS_LINE_COLORS.M3,
    [
      "PROASTIAKOS",
      "Suburban",
      "suburban",
      "Proastiakos",
      "Προαστιακός",
      "A1",
      "A2",
      "A3",
      "A4",
      "Α1",
      "Α2",
      "Α3",
      "Α4",
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

function busColorExpression() {
  return ["match", ["get", "mode"], "trolley", TROLLEY_COLOR, BUS_COLOR];
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

function dispatchUpdated(state, snapshot) {
  const bus = state?.bus;
  if (!bus || typeof bus.dispatchEvent !== "function" || typeof globalThis.CustomEvent !== "function") {
    return;
  }
  try {
    bus.dispatchEvent(new CustomEvent("transit:updated", { detail: snapshot }));
  } catch {
    // A listener error must never break the 20 s polling loop.
  }
}

function recordSnapshot(map, res, bundle, { rail, buses }) {
  const prev = snapshotByMap.get(map) ?? {};
  const payload = responsePayload(res);
  const snapshot = {
    lines: rail ? bundle.lines : prev.lines ?? bundle.lines,
    stations: rail ? bundle.stations : prev.stations ?? bundle.stations,
    buses: buses ? bundle.buses : prev.buses ?? emptyFeatureCollection(),
    routes: routesFromResponse(payload, bundle),
    // backend_source (api.js) carries the backend's own label, e.g. "snapshot" -> CACHED, not LIVE.
    source: res?.backend_source || res?.source || payload?.source || prev.source || "",
    updated_at: payload?.updated_at ?? prev.updated_at ?? null,
  };
  snapshotByMap.set(map, snapshot);
  return snapshot;
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
    // Whole network, no viewport bbox: Athens has 7 rail lines, ~81 stations and 8 configured OASA routes,
    // so the payload is small, and a viewport bbox hid stations / buses the menu flies to (Wave 1 review).
    const res = await api.transit();
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
      const busRoutesSrc = map.getSource(BUS_ROUTES_SOURCE_ID);
      if (busRoutesSrc && typeof busRoutesSrc.setData === "function") {
        busRoutesSrc.setData(res?.bus_routes ?? emptyFeatureCollection());
      }
    }
    let busesApplied = false;
    if (updateBuses) {
      if (!busesActiveByMap.get(map) || (busPollGenByMap.get(map) ?? 0) !== busGen) {
        // Stale or switched-off poll: only rail data (if requested) is kept.
        if (updateRail) dispatchUpdated(state, recordSnapshot(map, res, bundle, { rail: true, buses: false }));
        return bundle;
      }
      updateBusesData(map, bundle.buses);
      busesApplied = true;
    }
    dispatchUpdated(state, recordSnapshot(map, res, bundle, { rail: updateRail, buses: busesApplied }));
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
  const snap = snapshotByMap.get(map);
  if (snap) {
    // The menu must not list buses that are no longer being tracked.
    snapshotByMap.set(map, { ...snap, buses: emptyFeatureCollection() });
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

// Last transit bundle seen on this map: { lines, stations, buses, routes, source, updated_at } or null.
export function getLastTransitSnapshot(map) {
  return (map && snapshotByMap.get(map)) || null;
}

// Manual refresh for the menu's Refresh button: reloads whichever transit sub-layers are on.
// Makes no api.transit call while both are off (A2 contract: no transit traffic while off).
export async function triggerTransitRefresh(map, api, state = null) {
  const railOn = Boolean(state?.visible?.[RAIL_ID]);
  const busesOn = Boolean(state?.visible?.[BUSES_ID]) && Boolean(busesActiveByMap.get(map));
  if (!map || (!railOn && !busesOn)) {
    return getLastTransitSnapshot(map);
  }
  await loadTransitData(map, api, { updateRail: railOn, updateBuses: busesOn, state });
  return getLastTransitSnapshot(map);
}

// ------------------------------------------------------------------ per-line filters

function toKeyList(value) {
  if (value === null || value === undefined) return null;
  const arr = value instanceof Set ? [...value] : Array.isArray(value) ? value : [value];
  return arr.map((x) => String(x ?? "")).filter((x) => x !== "");
}

function railLineFilter(keys) {
  return keys === null ? null : ["in", ["coalesce", ["get", "line_key"], ""], ["literal", keys]];
}

function stationFilter(keys) {
  if (keys === null) return null;
  if (keys.length === 0) return ["==", 1, 0];
  // line_keys is "|M2|A1|": a substring test per selected line keeps interchange stations visible.
  return ["any", ...keys.map((k) => ["in", `|${k}|`, ["coalesce", ["get", "line_keys"], ""]])];
}

function busFilter(keys) {
  if (keys === null) return null;
  // Menu items are OASA route codes (one per direction); plain line codes ("040") are accepted too.
  return [
    "any",
    ["in", ["to-string", ["coalesce", ["get", "route_code"], ""]], ["literal", keys]],
    ["in", ["to-string", ["coalesce", ["get", "line"], ""]], ["literal", keys]],
  ];
}

function filterForLayer(layerId, filter) {
  if (!filter) return null;
  if (layerId === RAIL_LINES_LAYER_ID) return railLineFilter(filter.railKeys);
  if (layerId === RAIL_STATIONS_LAYER_ID || layerId === RAIL_LABELS_LAYER_ID) return stationFilter(filter.railKeys);
  if (layerId === BUSES_LAYER_ID || layerId === BUSES_LABELS_LAYER_ID || layerId === BUS_ROUTES_LAYER_ID) return busFilter(filter.busKeys);
  return null;
}

function applyFilters(map) {
  if (!map || typeof map.setFilter !== "function") return;
  const filter = filterByMap.get(map) ?? null;
  for (const layerId of layerIds) {
    if (typeof map.getLayer === "function" && !map.getLayer(layerId)) continue;
    map.setFilter(layerId, filterForLayer(layerId, filter));
  }
}

// Show only the given Metro/Suburban refs ("Μ1", "A3"...) and OASA route codes / line codes.
// null or undefined for a group means "show all" in that group; [] hides the whole group.
export function setTransitFilter(map, { railLines, busLines } = {}) {
  if (!map) return null;
  const rail = toKeyList(railLines);
  const filter = {
    railKeys: rail === null ? null : rail.map(canonicalLine),
    busKeys: toKeyList(busLines),
    railLines: rail,
  };
  filterByMap.set(map, filter);
  applyFilters(map);
  return { railLines: filter.railLines, busLines: filter.busKeys };
}

export function getTransitFilter(map) {
  const f = (map && filterByMap.get(map)) || null;
  return { railLines: f?.railLines ?? null, busLines: f?.busKeys ?? null };
}

// ------------------------------------------------------------------ registration

function addLayerWithFilter(map, layer) {
  const filter = filterForLayer(layer.id, filterByMap.get(map) ?? null);
  map.addLayer(filter ? { ...layer, filter } : layer);
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
    if (!map.getSource(BUS_ROUTES_SOURCE_ID)) {
      map.addSource(BUS_ROUTES_SOURCE_ID, {
        type: "geojson",
        data: emptyFeatureCollection(),
      });
    }
  }

  if (typeof map.getLayer === "function") {
    if (!map.getLayer(RAIL_LINES_LAYER_ID)) {
      addLayerWithFilter(map, {
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
      addLayerWithFilter(map, {
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

    if (!map.getLayer(RAIL_LABELS_LAYER_ID)) {
      addLayerWithFilter(map, {
        id: RAIL_LABELS_LAYER_ID,
        type: "symbol",
        source: STATIONS_SOURCE_ID,
        minzoom: RAIL_LABELS_MINZOOM,
        layout: {
          visibility: railOn ? "visible" : "none",
          "text-field": ["coalesce", ["get", "name"], ""],
          "text-font": LABEL_FONT,
          "text-size": 12,
          "text-anchor": "top",
          "text-offset": [0, 0.9],
          "text-optional": true,
          "text-max-width": 9,
        },
        paint: {
          // Dark ink with a white halo stays readable on both Light and Dark base maps.
          "text-color": "#0f172a",
          "text-halo-color": "#ffffff",
          "text-halo-width": 1.6,
          "text-halo-blur": 0.2,
        },
      });
    }

    if (!map.getLayer(BUS_ROUTES_LAYER_ID)) {
      addLayerWithFilter(map, {
        id: BUS_ROUTES_LAYER_ID,
        type: "line",
        source: BUS_ROUTES_SOURCE_ID,
        layout: {
          visibility: busesOn ? "visible" : "none",
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": busColorExpression(),
          "line-width": 3.5,
          "line-opacity": 0.72,
          "line-dasharray": [2, 1.5],
        },
      });
    }

    if (!map.getLayer(BUSES_LAYER_ID)) {
      addLayerWithFilter(map, {
        id: BUSES_LAYER_ID,
        type: "circle",
        source: BUSES_SOURCE_ID,
        layout: {
          visibility: busesOn ? "visible" : "none",
        },
        paint: {
          "circle-radius": BUS_RADIUS,
          "circle-color": busColorExpression(),
          "circle-stroke-color": BUS_STROKE_COLOR,
          "circle-stroke-width": BUS_STROKE_WIDTH,
        },
      });
    }

    if (!map.getLayer(BUSES_LABELS_LAYER_ID)) {
      addLayerWithFilter(map, {
        id: BUSES_LABELS_LAYER_ID,
        type: "symbol",
        source: BUSES_SOURCE_ID,
        layout: {
          visibility: busesOn ? "visible" : "none",
          "text-field": ["to-string", ["coalesce", ["get", "line"], ""]],
          "text-font": LABEL_FONT,
          "text-size": 12,
          "text-anchor": "left",
          "text-offset": [1.05, 0],
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          // White bold line code with a halo in the marker colour: AA contrast on any base map.
          "text-color": "#ffffff",
          "text-halo-color": busColorExpression(),
          "text-halo-width": 2.4,
        },
      });
    }
  }

  bindStationPopup(map);
  bindBusPopup(map);

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
