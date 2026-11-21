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

export async function bootstrap(root = typeof document !== "undefined" ? document : null) {
  if (!root || typeof root.getElementById !== "function") {
    return null;
  }

  const optional = {};
  for (const specifier of OPTIONAL_DEV_B_MODULES) {
    optional[specifier] = await tryImport(specifier);
  }

  const api = optional["./api.js"] ?? null;
  const offlineBadgeEl = root.getElementById("hud-offline");
  const initialTheme = root.documentElement?.dataset?.theme === "dark" ? "dark" : "light";

  function showOfflineBadge() {
    if (offlineBadgeEl?.classList) {
      offlineBadgeEl.classList.remove("hidden");
    }
  }

  const state = {
    visible: {},
    theme: initialTheme,
    activeTab: "map",
    offline: false,
    offlineGeo: null,
    onOffline: () => {
      showOfflineBadge();
    },
  };

  const mapContainer = root.getElementById("map");
  const map = mapContainer ? createMap(mapContainer, state) : null;

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
    initWorkPopup(map, { reportModule: optional["./ui/report.js"] });
  }

  /* --- A4 --- */
  const routingEl = root.getElementById("hud-routing");
  const routing = routingEl
    ? initRouting(routingEl, map, api, { onNonLiveSource: showOfflineBadge })
    : null;
  /* --- /A4 --- */

  return {
    map,
    api,
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
