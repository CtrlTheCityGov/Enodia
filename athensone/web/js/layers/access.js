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

async function loadAccessData(api) {
  if (!api || typeof api.access !== "function") {
    return emptyFeatureCollection();
  }
  try {
    const res = await api.access();
    // Static pre-downloaded OSM accessibility data (SPEC.md "Εξωτερικές πηγές", TASKS_A.md A6):
    // source === "mock" is expected by design and must not trigger the offline badge.
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

  const data = await loadAccessData(api);
  const src = typeof map.getSource === "function" ? map.getSource(SOURCE_ID) : null;
  if (src && typeof src.setData === "function") {
    src.setData(data);
  }

  bindAccessPopup(map);

  return { id, layerIds };
}

const KIND_LABELS = Object.freeze({
  kerb_lowered: "Χαμηλωμένο κράσπεδο",
  ramp: "Ράμπα πρόσβασης",
  tactile_paving: "Απτικός οδηγός όδευσης",
  wheelchair: "Προσβάσιμος χώρος (ΑμεΑ)",
  toilets_wheelchair: "Προσβάσιμη τουαλέτα (ΑμεΑ)",
});

const accessPopupBound = new WeakSet();

function escapeHtmlAccess(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function bindAccessPopup(map) {
  if (typeof map.on !== "function" || accessPopupBound.has(map)) {
    return;
  }
  accessPopupBound.add(map);
  let activePopup = null;
  map.on("click", POINTS_LAYER_ID, (event) => {
    const props = event?.features?.[0]?.properties ?? {};
    const PopupCtor = globalThis.maplibregl?.Popup;
    if (!event?.lngLat || typeof PopupCtor !== "function") {
      return;
    }
    if (activePopup && typeof activePopup.remove === "function") {
      activePopup.remove();
    }
    const kindLabel = props.amenity === "toilets"
      ? KIND_LABELS.toilets_wheelchair
      : (KIND_LABELS[props.kind] || "Σημείο προσβασιμότητας");
    const name = props.name && String(props.name).trim() ? String(props.name).trim() : kindLabel;
    const wc = props.wheelchair === "yes" ? "Πλήρης πρόσβαση ΑμεΑ" : props.wheelchair === "limited" ? "Περιορισμένη πρόσβαση" : "";
    const html = `<article class="pois-popup__body"><h3 class="pois-popup__title">${escapeHtmlAccess(name)}</h3><p class="pois-popup__meta">${escapeHtmlAccess(kindLabel)}</p>${wc ? `<p class="pois-popup__open">${escapeHtmlAccess(wc)}</p>` : ""}</article>`;
    activePopup = new PopupCtor({ className: "glass pois-popup" });
    activePopup.setLngLat(event.lngLat).setHTML(html).addTo(map);
  });
}
