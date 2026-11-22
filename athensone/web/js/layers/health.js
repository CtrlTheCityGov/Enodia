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

// Last api.health() provenance per map, for the popup's LIVE / CACHED / DEMO pill.
const sourceByMap = new WeakMap();
const popupBoundMaps = new WeakSet();

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// "hospital" / "νοσοκομείο" -> hospital; "pharmacy" / "φαρμακείο" -> pharmacy; anything else -> other.
export function healthKind(kind) {
  const k = String(kind ?? "").trim().toLowerCase();
  if (k === "hospital" || k === "νοσοκομείο") return "hospital";
  if (k === "pharmacy" || k === "φαρμακείο") return "pharmacy";
  return "other";
}

function provenancePill(source) {
  const raw = String(source ?? "").trim().toLowerCase();
  if (raw === "live") return `<span class="prov-pill prov-pill--live">LIVE</span>`;
  if (raw === "cache" || raw === "cached" || raw === "snapshot") return `<span class="prov-pill prov-pill--cached">CACHED</span>`;
  if (raw === "mock" || raw === "demo" || raw === "seed") return `<span class="prov-pill prov-pill--demo">DEMO</span>`;
  return "";
}

// GeoJSON sources hand array properties back as JSON strings on click (MapLibre behaviour).
function toList(value) {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (typeof value === "string" && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed.map(String).filter(Boolean);
    } catch {
      // plain text, e.g. "Παθολογική, Χειρουργική"
    }
    return [value.trim()];
  }
  return [];
}

// Popup HTML for one on-duty pharmacy / hospital. Missing phone/address show «άγνωστο» (never invented).
export function renderHealthPopupHtml(props = {}, source = "") {
  const p = props || {};
  const kind = healthKind(p.kind);
  const badge =
    kind === "hospital"
      ? `<span class="health-popup__badge health-popup__badge--hospital">🏥 Εφημερεύον Νοσοκομείο</span>`
      : kind === "pharmacy"
        ? `<span class="health-popup__badge health-popup__badge--pharmacy">💊 Εφημερεύον Φαρμακείο</span>`
        : `<span class="health-popup__badge">Μονάδα υγείας</span>`;
  const rows = [];
  const row = (k, v) =>
    rows.push(`<li class="health-popup__row"><span>${escapeHtml(k)}</span><strong>${escapeHtml(v)}</strong></li>`);
  row("Διεύθυνση", p.address || "άγνωστο");
  const phone = String(p.phone ?? "").trim();
  if (phone && phone !== "άγνωστο" && /^[+\d][\d\s().-]{4,}$/.test(phone)) {
    // Only digits/+/spaces reach the tel: link, so no attribute injection is possible.
    rows.push(
      `<li class="health-popup__row"><span>Τηλέφωνο</span><a class="health-popup__tel" href="tel:${escapeHtml(phone.replace(/[^\d+]/g, ""))}">${escapeHtml(phone)}</a></li>`,
    );
  } else {
    row("Τηλέφωνο", "άγνωστο");
  }
  if (p.hours) row("Ωράριο", p.hours);
  const specialties = toList(p.specialties ?? p.specialty);
  const specHtml = specialties.length
    ? `<div class="health-popup__specs">${specialties.map((s) => `<span class="health-popup__spec">${escapeHtml(s)}</span>`).join("")}</div>`
    : "";
  const prov = provenancePill(source);
  return (
    `<div class="health-popup">` +
    `<strong class="health-popup__title">${escapeHtml(p.name || "Μονάδα υγείας")}</strong>` +
    `<div class="health-popup__head">${badge}${prov}</div>` +
    `<ul class="health-popup__list">${rows.join("")}</ul>` +
    specHtml +
    `</div>`
  );
}

function setCursor(map, value) {
  const canvas = typeof map.getCanvas === "function" ? map.getCanvas() : null;
  if (canvas?.style) canvas.style.cursor = value;
}

function bindHealthPopup(map) {
  if (!map || popupBoundMaps.has(map) || typeof map.on !== "function") {
    return;
  }
  popupBoundMaps.add(map);
  map.on("mouseenter", POINTS_LAYER_ID, () => setCursor(map, "pointer"));
  map.on("mouseleave", POINTS_LAYER_ID, () => setCursor(map, ""));
  map.on("click", POINTS_LAYER_ID, (event) => {
    const feature = event?.features?.[0];
    const PopupCtor = globalThis.maplibregl?.Popup;
    if (!feature || typeof PopupCtor !== "function") return;
    const coords = feature.geometry?.coordinates;
    const lngLat = Array.isArray(coords) && coords.length >= 2 ? coords : event?.lngLat;
    if (!lngLat) return;
    new PopupCtor({ className: "glass work-popup health-popup-wrap", offset: 10 })
      .setLngLat(lngLat)
      .setHTML(renderHealthPopupHtml(feature.properties || {}, sourceByMap.get(map) ?? ""))
      .addTo(map);
  });
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

async function loadHealthData(api, state, map = null) {
  if (!api || typeof api.health !== "function") {
    return emptyFeatureCollection();
  }
  try {
    const res = await api.health();
    if (map) sourceByMap.set(map, res?.backend_source || res?.source || "");
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

  bindHealthPopup(map);

  const data = await loadHealthData(api, state, map);
  const src = typeof map.getSource === "function" ? map.getSource(SOURCE_ID) : null;
  if (src && typeof src.setData === "function") {
    src.setData(data);
  }

  return { id, layerIds };
}
