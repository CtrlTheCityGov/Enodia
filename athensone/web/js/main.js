// Entry point for the AthensOne Citizen Map (SPEC.md "Αρχιτεκτονική").
// Imports Dev A modules statically and Dev B optional modules dynamically in a try/catch
// so Dev A loads without waiting for Dev B and imports safely in Node.

import { createMap, setTheme } from "./map.js";
/* --- A2 --- */
import { addOverlays, registerOverlay } from "./map.js";
/* --- /A2 --- */
import * as envLayer from "./layers/env.js";
import * as accessLayer from "./layers/access.js";
import * as worksLayer from "./layers/works.js";
import * as transitLayer from "./layers/transit.js";
import * as healthLayer from "./layers/health.js";
import * as reportsLayer from "./layers/reports.js";
import { initLayerBar } from "./ui/layerbar.js";
import { initWorkPopup } from "./ui/workpopup.js";
import { initRouting } from "./ui/routing.js";

// Dev B optional modules listed in SPEC.md "Αρχιτεκτονική" and TASKS_A.md "### A0" (certainty: verified).
export const OPTIONAL_DEV_B_MODULES = [
  "./api.js",
  "./ui/points.js",
  "./ui/report.js",
  "./ui/stoa.js",
  "./ui/workstab.js",
];

// All six map layer modules owned by Dev A (source: SPEC.md "Αρχιτεκτονική", certainty: verified).
export const LAYERS = [
  envLayer,
  accessLayer,
  worksLayer,
  transitLayer,
  healthLayer,
  reportsLayer,
];

// Greek UI labels for the Light/Dark theme toggle button (SPEC.md F9, certainty: design default).
const THEME_LABEL_TO_DARK = "Σκοτεινό";
const THEME_LABEL_TO_LIGHT = "Φωτεινό";

// Stoa AI citation flyTo camera and temporary highlight settings (zoom/pitch from SPEC.md "HUD (glassmorphism)"; highlight duration design default).
const FLYTO_ZOOM = 17;
const FLYTO_PITCH = 60;
const FLYTO_DURATION_MS = 1100;
const FLYTO_HIGHLIGHT_SOURCE_ID = "flyto-highlight-source";
const FLYTO_HIGHLIGHT_LAYER_ID = "flyto-highlight";
const FLYTO_HIGHLIGHT_DURATION_MS = 6000;
const TOAST_DEFAULT_DURATION_MS = 3000;

// Dev B UI modules and their HUD mount slots (source: SPEC.md "Αρχιτεκτονική" & TASKS_A.md A5 / A-35; certainty: verified).
const DEV_B_UI_MOUNTS = [
  { specifier: "./ui/points.js", containerIds: ["hud-points"] },
  { specifier: "./ui/report.js", containerIds: ["hud-report"] },
  { specifier: "./ui/stoa.js", containerIds: ["hud-stoa"] },
  { specifier: "./ui/workstab.js", containerIds: ["hud-workstab", "hud-tabs"] },
];

function isMissingModuleError(err) {
  if (!err) {
    return false;
  }
  if (err.code === "ERR_MODULE_NOT_FOUND" || err.code === "ENOENT") {
    return true;
  }
  // Browsers reject missing dynamic ES module imports with a TypeError (certainty: standard browser behavior).
  if (
    err instanceof TypeError &&
    /dynamically imported module|module script failed/i.test(err.message ?? "")
  ) {
    return true;
  }
  return false;
}

async function tryImport(specifier) {
  try {
    return await import(specifier);
  } catch (err) {
    if (!isMissingModuleError(err)) {
      console.error(`Failed to load optional module ${specifier}:`, err);
    }
    return null;
  }
}

/* --- A2 --- */
let a2BoundApi = null;
let a2OverlaysRegistered = false;

function registerA2Overlays(api) {
  a2BoundApi = api ?? null;
  if (a2OverlaysRegistered) {
    return;
  }
  a2OverlaysRegistered = true;

  registerOverlay((m, st) => {
    envLayer.register(m, a2BoundApi, st);
    return { id: envLayer.id, layerIds: envLayer.layerIds };
  });
  registerOverlay((m, st) => {
    accessLayer.register(m, a2BoundApi, st);
    return { id: accessLayer.id, layerIds: accessLayer.layerIds };
  });
  registerOverlay((m, st) => {
    worksLayer.register(m, a2BoundApi, st);
    return { id: worksLayer.id, layerIds: worksLayer.layerIds };
  });
  registerOverlay((m, st) => {
    transitLayer.register(m, a2BoundApi, st);
    return { id: transitLayer.BUSES_ID, layerIds: transitLayer.busLayerIds };
  });
  registerOverlay(() => ({
    id: transitLayer.RAIL_ID,
    layerIds: transitLayer.railLayerIds,
  }));
  registerOverlay((m, st) => {
    healthLayer.register(m, a2BoundApi, st);
    return { id: healthLayer.id, layerIds: healthLayer.layerIds };
  });
  registerOverlay((m, st) => {
    reportsLayer.register(m, a2BoundApi, st);
    return { id: reportsLayer.id, layerIds: reportsLayer.layerIds };
  });
}
/* --- /A2 --- */

async function loadOfflineBase(api) {
  const loader =
    typeof api?.offlineBase === "function"
      ? () => api.offlineBase()
      : typeof api?.base === "function"
        ? () => api.base()
        : null;
  if (!loader) {
    return null;
  }
  try {
    const res = await loader();
    if (res && res.type === "FeatureCollection") {
      return res;
    }
    if (res && res.data && res.data.type === "FeatureCollection") {
      return res.data;
    }
    return null;
  } catch {
    return null;
  }
}

function showFlyToHighlight(map, lon, lat, label, stateRef) {
  if (!map || typeof map.getSource !== "function") {
    return;
  }
  const featureCollection = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { label: typeof label === "string" ? label : "" },
        geometry: { type: "Point", coordinates: [lon, lat] },
      },
    ],
  };

  const existing = map.getSource(FLYTO_HIGHLIGHT_SOURCE_ID);
  if (existing && typeof existing.setData === "function") {
    existing.setData(featureCollection);
  } else if (typeof map.addSource === "function") {
    map.addSource(FLYTO_HIGHLIGHT_SOURCE_ID, {
      type: "geojson",
      data: featureCollection,
    });
  }

  const hasLayer =
    typeof map.getLayer === "function" ? Boolean(map.getLayer(FLYTO_HIGHLIGHT_LAYER_ID)) : false;
  if (!hasLayer && typeof map.addLayer === "function") {
    map.addLayer({
      id: FLYTO_HIGHLIGHT_LAYER_ID,
      type: "circle",
      source: FLYTO_HIGHLIGHT_SOURCE_ID,
      paint: {
        "circle-radius": 14,
        "circle-color": "#facc15",
        "circle-opacity": 0.45,
        "circle-stroke-color": "#d97706",
        "circle-stroke-width": 3,
      },
    });
  }

  if (stateRef.timerId !== null) {
    clearTimeout(stateRef.timerId);
  }
  stateRef.timerId = setTimeout(() => {
    stateRef.timerId = null;
    const src = typeof map.getSource === "function" ? map.getSource(FLYTO_HIGHLIGHT_SOURCE_ID) : null;
    if (src && typeof src.setData === "function") {
      src.setData({ type: "FeatureCollection", features: [] });
    }
  }, FLYTO_HIGHLIGHT_DURATION_MS);
}

export async function bootstrap(
  root = typeof document !== "undefined" ? document : null,
  options = {},
) {
  if (!root || typeof root.getElementById !== "function") {
    return null;
  }

  const bus = options?.bus ?? new EventTarget();
  const optionalOverrides =
    options?.optional && typeof options.optional === "object" ? options.optional : null;
  const optional = {};
  for (const specifier of OPTIONAL_DEV_B_MODULES) {
    if (optionalOverrides && Object.hasOwn(optionalOverrides, specifier)) {
      optional[specifier] = optionalOverrides[specifier];
    } else {
      optional[specifier] = await tryImport(specifier);
    }
  }

  const api = optional["./api.js"] ?? null;
  const offlineBadgeEl = root.getElementById("hud-offline");
  const initialTheme = root.documentElement?.dataset?.theme === "dark" ? "dark" : "light";

  function showOfflineBadge() {
    if (offlineBadgeEl?.classList) {
      offlineBadgeEl.classList.remove("hidden");
    }
  }

  const offlineGeo = await loadOfflineBase(api);

  const state = {
    visible: {},
    theme: initialTheme,
    activeTab: "map",
    offline: false,
    offlineGeo,
    onOffline: () => {
      showOfflineBadge();
    },
  };

  /* --- A6 --- */
  function syncOfflineBadge() {
    if (!offlineBadgeEl?.classList) {
      return;
    }
    const isOffline = Boolean(
      state.offline || (typeof api?.isOffline === "function" && api.isOffline()),
    );
    offlineBadgeEl.classList.toggle("hidden", !isOffline);
  }

  if (api?.status && typeof api.status.addEventListener === "function") {
    api.status.addEventListener("source", syncOfflineBadge);
    syncOfflineBadge();
  }
  /* --- /A6 --- */

  const mapContainer = root.getElementById("map");
  const map = mapContainer ? createMap(mapContainer, state) : null;

  const flyToHighlightState = { timerId: null };
  const toastEl = root.getElementById("hud-toast");
  let toastTimer = null;

  function showToast(detail) {
    if (!toastEl || !detail) {
      return;
    }
    const text = typeof detail === "string" ? detail : String(detail.message ?? detail.text ?? "").trim();
    if (!text) {
      return;
    }
    const duration =
      Number.isFinite(detail?.durationMs) && detail.durationMs > 0
        ? detail.durationMs
        : TOAST_DEFAULT_DURATION_MS;

    if (toastTimer !== null) {
      clearTimeout(toastTimer);
      toastTimer = null;
    }

    const doc = toastEl.ownerDocument ?? root;
    const pill = typeof doc.createElement === "function" ? doc.createElement("div") : null;
    if (pill) {
      pill.className = "glass glass-pill hud-toast__pill";
      if (detail?.photo_url_blurred) {
        const img = doc.createElement("img");
        img.className = "hud-toast__thumb";
        img.src = detail.photo_url_blurred;
        img.alt = "Θολωμένη φωτογραφία αναφοράς";
        pill.appendChild(img);
      }
      const span = doc.createElement("span");
      span.className = "hud-toast__text";
      span.textContent = text;
      pill.appendChild(span);
      if (detail?.link?.href && String(detail.link.href).startsWith("/")) {
        const a = doc.createElement("a");
        a.className = "hud-toast__link";
        a.href = detail.link.href;
        a.textContent = detail.link.label || "Άνοιγμα";
        pill.appendChild(a);
      }
      if (typeof toastEl.replaceChildren === "function") {
        toastEl.replaceChildren(pill);
      } else {
        toastEl.textContent = text;
      }
    } else {
      toastEl.textContent = text;
    }

    toastEl.classList?.remove("is-leaving");
    toastEl.classList?.add("is-visible");

    toastTimer = setTimeout(() => {
      toastEl.classList?.add("is-leaving");
      toastEl.classList?.remove("is-visible");
      toastTimer = setTimeout(() => {
        toastTimer = null;
        toastEl.classList?.remove("is-leaving");
        if (typeof toastEl.replaceChildren === "function") {
          toastEl.replaceChildren();
        } else {
          toastEl.textContent = "";
        }
      }, 240);
    }, duration);
  }

  if (typeof bus.addEventListener === "function") {
    bus.addEventListener("map:flyto", (event) => {
      const detail = event?.detail;
      if (
        detail?.lon == null ||
        detail?.lat == null ||
        detail.lon === "" ||
        detail.lat === ""
      ) {
        return;
      }
      const lon = Number(detail.lon);
      const lat = Number(detail.lat);
      if (!map || !Number.isFinite(lon) || !Number.isFinite(lat)) {
        return;
      }
      if (typeof map.flyTo === "function") {
        map.flyTo({
          center: [lon, lat],
          zoom: FLYTO_ZOOM,
          pitch: FLYTO_PITCH,
          duration: FLYTO_DURATION_MS,
          essential: true,
        });
      }
      showFlyToHighlight(map, lon, lat, detail?.label, flyToHighlightState);
    });

    /* --- A6 / Upgrade #4 / A-LOOP-1 --- */
    let lastReportStatuses = null;
    function extractReportStatuses(fc) {
      const statuses = new Map();
      const features = Array.isArray(fc?.features) ? fc.features : [];
      for (let i = 0; i < features.length; i += 1) {
        const f = features[i];
        const key = f?.properties?.id ?? f?.id ?? `idx-${i}`;
        const status = f?.properties?.status ?? "submitted";
        statuses.set(String(key), String(status));
      }
      return statuses;
    }
    function reportStatusesChanged(prev, next) {
      if (!prev) return false;
      if (prev.size !== next.size) return true;
      for (const [k, v] of next) {
        if (prev.get(k) !== v) return true;
      }
      return false;
    }
    async function refreshReportsAndSync() {
      if (!map) return null;
      if (!lastReportStatuses && typeof map.getSource === "function") {
        const srcData = map.getSource(reportsLayer.SOURCE_ID)?.data;
        if (srcData && Array.isArray(srcData.features) && srcData.features.length > 0) {
          lastReportStatuses = extractReportStatuses(srcData);
        }
      }
      const fc = await reportsLayer.refresh(map, api, state);
      const nextStatuses = extractReportStatuses(fc);
      const changed = reportStatusesChanged(lastReportStatuses, nextStatuses);
      lastReportStatuses = nextStatuses;
      if (changed && typeof bus.dispatchEvent === "function") {
        bus.dispatchEvent(new CustomEvent("reports:changed", { detail: { count: nextStatuses.size } }));
      }
      return fc;
    }

    // Immediately land & pulse the newly reported pin on the map, then merge with backend refresh.
    bus.addEventListener("report:created", (event) => {
      if (!map) {
        return;
      }
      if (event?.detail) {
        reportsLayer.addReportPin(map, event.detail);
      }
      refreshReportsAndSync();
    });

    // Refresh live citizen report pins immediately after a newly submitted Waze report awards points (TASKS_A.md A6).
    bus.addEventListener("points:earned", () => {
      if (map) {
        refreshReportsAndSync();
      }
    });
    bus.addEventListener("toast:show", (event) => {
      showToast(event?.detail);
    });
    if (typeof globalThis.addEventListener === "function") {
      globalThis.addEventListener("focus", () => {
        if (map) refreshReportsAndSync();
      });
    }
    if (root && typeof root.addEventListener === "function") {
      root.addEventListener("visibilitychange", () => {
        if (map && root.visibilityState === "visible") {
          refreshReportsAndSync();
        }
      });
    }
    /* --- /A6 --- */
  }

  const themeBtn = root.getElementById("theme-toggle");
  function applyTheme(nextTheme) {
    const normalized = nextTheme === "dark" ? "dark" : "light";
    state.theme = normalized;
    if (root.documentElement?.dataset) {
      root.documentElement.dataset.theme = normalized;
    }
    if (themeBtn) {
      const isDark = normalized === "dark";
      themeBtn.setAttribute("aria-pressed", String(isDark));
      themeBtn.textContent = isDark ? THEME_LABEL_TO_LIGHT : THEME_LABEL_TO_DARK;
    }
    if (map) {
      setTheme(map, normalized, state);
    }
  }

  if (themeBtn) {
    const isDark = state.theme === "dark";
    themeBtn.setAttribute("aria-pressed", String(isDark));
    themeBtn.textContent = isDark ? THEME_LABEL_TO_LIGHT : THEME_LABEL_TO_DARK;
    if (typeof themeBtn.addEventListener === "function") {
      themeBtn.addEventListener("click", () => {
        applyTheme(state.theme === "dark" ? "light" : "dark");
      });
    }
  }

  const tabsContainer = root.getElementById("hud-tabs");
  const tabMapBtn = root.getElementById("tab-map");
  const tabWorksBtn = root.getElementById("tab-works");

  function selectTab(tab) {
    const nextTab = tab === "works" ? "works" : "map";
    state.activeTab = nextTab;
    if (tabsContainer?.dataset) {
      tabsContainer.dataset.activeTab = nextTab;
    }
    if (tabMapBtn) {
      tabMapBtn.setAttribute("aria-selected", String(nextTab === "map"));
      tabMapBtn.classList?.toggle("is-active", nextTab === "map");
    }
    if (tabWorksBtn) {
      tabWorksBtn.setAttribute("aria-selected", String(nextTab === "works"));
      tabWorksBtn.classList?.toggle("is-active", nextTab === "works");
    }
    if (typeof state.onTabChange === "function") {
      state.onTabChange(nextTab);
    }
    if (typeof bus.dispatchEvent === "function") {
      bus.dispatchEvent(new CustomEvent("tab:change", { detail: { tab: nextTab } }));
    }
  }

  if (tabMapBtn && typeof tabMapBtn.addEventListener === "function") {
    tabMapBtn.addEventListener("click", () => selectTab("map"));
  }
  if (tabWorksBtn && typeof tabWorksBtn.addEventListener === "function") {
    tabWorksBtn.addEventListener("click", () => selectTab("works"));
  }

  /* --- A2 --- */
  registerA2Overlays(api);
  if (map && typeof map.isStyleLoaded === "function" && map.isStyleLoaded()) {
    addOverlays(map, state);
  }
  const layerBarEl = root.getElementById("hud-layerbar");
  if (layerBarEl) {
    initLayerBar(layerBarEl, state, { map, api });
  }
  /* --- /A2 --- */

  if (map) {
    initWorkPopup(map, { reportModule: optional["./ui/report.js"], bus });
  }

  /* --- A4 --- */
  const routingEl = root.getElementById("hud-routing");
  const routing = routingEl
    ? initRouting(routingEl, map, api, { onNonLiveSource: showOfflineBadge, bus })
    : null;
  /* --- /A4 --- */

  /* --- A5 --- */
  for (const { specifier, containerIds } of DEV_B_UI_MOUNTS) {
    const mod = optional[specifier];
    if (typeof mod?.mount !== "function") {
      continue;
    }
    let mountEl = null;
    for (const id of containerIds) {
      mountEl = root.getElementById(id);
      if (mountEl) {
        break;
      }
    }
    try {
      mod.mount({ map, api, root, container: mountEl, bus });
    } catch (err) {
      console.error(`Failed to mount optional module ${specifier}:`, err);
    }
  }
  /* --- /A5 --- */

  return {
    map,
    api,
    bus,
    state,
    layers: LAYERS,
    optional,
    routing,
    setTheme: applyTheme,
    selectTab,
  };
}

// Run bootstrap only in a browser environment; importing main.js in Node does not touch DOM or maplibregl.
if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      bootstrap(document);
    });
  } else {
    bootstrap(document);
  }
}
