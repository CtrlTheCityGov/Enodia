// Entry point for the AthensOne Citizen Map (SPEC.md "Αρχιτεκτονική").
// Imports Dev A modules statically and Dev B optional modules dynamically in a try/catch
// so A0 loads without waiting for Dev B and imports safely in Node.

import { createMap } from "./map.js";
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

async function tryImport(specifier) {
  try {
    return await import(specifier);
  } catch {
    return null;
  }
}

export async function bootstrap(root = typeof document !== "undefined" ? document : null) {
  if (!root) {
    return null;
  }

  const optional = {};
  for (const specifier of OPTIONAL_DEV_B_MODULES) {
    optional[specifier] = await tryImport(specifier);
  }

  const api = optional["./api.js"] ?? null;
  const mapContainer = root.getElementById("map");
  const state = { visible: {}, theme: "light" };
  const map = mapContainer ? createMap(mapContainer, state) : null;

  const layerBarEl = root.getElementById("hud-layerbar");
  if (layerBarEl) {
    initLayerBar(layerBarEl, state);
  }

  if (map) {
    initWorkPopup(map, { reportModule: optional["./ui/report.js"] });
  }

  const routingEl = root.getElementById("hud-routing");
  if (routingEl) {
    initRouting(routingEl, map, api);
  }

  return { map, api, state, layers: LAYERS, optional };
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
