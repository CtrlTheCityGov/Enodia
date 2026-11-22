// Official City POIs layer «Υπηρεσίες Δήμου» (TASKS_A.md A10, DECISIONS.md A-40; data: api.pois(), B14).
// Never touches document or maplibregl at import time so Node can import it safely.

// Layer id from TASKS_A.md A10 (certainty: verified).
export const id = "pois";

// Greek chip label from TASKS_A.md A10 (certainty: verified).
export const label = "Δήμος";

// MapLibre source and layer identifiers (source: TASKS_A.md A10 for the layer id; source id is a design default).
const SOURCE_ID = "pois-source";
const POINTS_LAYER_ID = "pois-points";

// MapLibre layer ids added by this module (TASKS_A.md A10, certainty: verified).
export const layerIds = [POINTS_LAYER_ID];

// Marker colours per category; the card only asks that the two known categories differ from the default
// (source: TASKS_A.md A10, values are a design default, certainty: unverified for contrast on every basemap).
const FRIENDSHIP_CLUB_COLOR = "#7c3aed";
const LIBRARY_COLOR = "#2563eb";
const POIS_DEFAULT_COLOR = "#475569";
const POIS_POINT_RADIUS = 7;
const POIS_STROKE_COLOR = "#ffffff";
const POIS_STROKE_WIDTH = 2;

// Greek category labels (source: TASKS_A.md A10; "friendship_club" = Λέσχες Φιλίας, the former ΚΑΠΗ:
// rename unverified per the card). Unknown categories show their raw id.
const CATEGORY_LABELS = Object.freeze({
  friendship_club: "Λέσχη Φιλίας",
  library: "Βιβλιοθήκη",
});

// Greek UI strings (source: TASKS_A.md A10 and CLAUDE.md "Unknown values show as «άγνωστο»", certainty: verified).
const UNKNOWN_TEXT = "άγνωστο";
const OPEN_TEXT = "Ανοιχτό τώρα";
const CLOSED_TEXT = "Κλειστό τώρα";
const HOURS_UNKNOWN_TEXT = "Ωράριο: άγνωστο";
const OFFICIAL_BADGE = "επίσημο";
const MOCK_BADGE = "δοκιμαστικό";

// Popup CSS classes reusing the SPEC .glass surface (certainty: design default).
const POPUP_CLASS_NAME = "glass pois-popup";

// Click listeners are bound once per map: map.on() listeners outlive setStyle(), while register()
// runs again on every style.load (CLAUDE.md Gotchas, certainty: verified MapLibre behaviour).
const clickBoundMaps = new WeakSet();

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function hasText(value) {
  return value != null && String(value).trim() !== "";
}

function openNowText(openNow) {
  if (openNow === true) {
    return OPEN_TEXT;
  }
  if (openNow === false) {
    return CLOSED_TEXT;
  }
  return HOURS_UNKNOWN_TEXT;
}

// Pure: builds the popup HTML for one POI's properties. Every value from the data is escaped.
export function popupHtml(props = {}) {
  const p = props ?? {};
  const name = hasText(p.name) ? p.name : UNKNOWN_TEXT;
  const category = CATEGORY_LABELS[p.category] ?? (hasText(p.category) ? p.category : UNKNOWN_TEXT);
  const address = hasText(p.address) ? p.address : UNKNOWN_TEXT;
  const mockBadge = p.source === "mock" ? ` <span class="pois-popup__badge pois-popup__badge--mock">${MOCK_BADGE}</span>` : "";

  return [
    `<article class="pois-popup__body">`,
    `<h3 class="pois-popup__title">${escapeHtml(name)}</h3>`,
    `<p class="pois-popup__meta">${escapeHtml(category)}`,
    ` <span class="pois-popup__badge">${OFFICIAL_BADGE}</span>${mockBadge}</p>`,
    `<p class="pois-popup__address">${escapeHtml(address)}</p>`,
    `<p class="pois-popup__open">${escapeHtml(openNowText(p.open_now))}</p>`,
    `</article>`,
  ].join("");
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

async function loadPoisData(api, state) {
  if (!api || typeof api.pois !== "function") {
    return emptyFeatureCollection();
  }
  try {
    const res = await api.pois();
    if (res?.source && res.source !== "live" && typeof state?.onOffline === "function") {
      state.onOffline();
    }
    return toFeatureCollection(res);
  } catch {
    return emptyFeatureCollection();
  }
}

function bindClickPopup(map) {
  if (typeof map.on !== "function" || clickBoundMaps.has(map)) {
    return;
  }
  clickBoundMaps.add(map);

  let activePopup = null;
  map.on("click", POINTS_LAYER_ID, (event) => {
    const feature = event?.features?.[0];
    const PopupCtor = globalThis.maplibregl?.Popup;
    if (!feature || !event?.lngLat || typeof PopupCtor !== "function") {
      return;
    }
    if (activePopup && typeof activePopup.remove === "function") {
      activePopup.remove();
    }
    activePopup = new PopupCtor({ className: POPUP_CLASS_NAME });
    activePopup.setLngLat(event.lngLat).setHTML(popupHtml(feature.properties ?? {})).addTo(map);
  });
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
        "circle-radius": POIS_POINT_RADIUS,
        "circle-color": [
          "match",
          ["coalesce", ["get", "category"], ""],
          "friendship_club",
          FRIENDSHIP_CLUB_COLOR,
          "library",
          LIBRARY_COLOR,
          POIS_DEFAULT_COLOR,
        ],
        "circle-stroke-color": POIS_STROKE_COLOR,
        "circle-stroke-width": POIS_STROKE_WIDTH,
      },
    });
  }

  bindClickPopup(map);

  const data = await loadPoisData(api, state);
  const src = typeof map.getSource === "function" ? map.getSource(SOURCE_ID) : null;
  if (src && typeof src.setData === "function") {
    src.setData(data);
  }

  return { id, layerIds };
}
