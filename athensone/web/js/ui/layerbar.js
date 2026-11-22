// Layer toggle pill bar UI: six chips in exact SPEC order with aria-pressed, keyboard navigation,
// plus a sleek 2D/3D buildings view toggle pill (SPEC.md "HUD (glassmorphism)", TASKS_A.md A2).
// Never touches document or maplibregl at import time so Node can import it safely.

import { set3DMode } from "../map.js";
import * as envLayer from "../layers/env.js";
import * as accessLayer from "../layers/access.js";
import * as worksLayer from "../layers/works.js";
import * as transitLayer from "../layers/transit.js";
import * as healthLayer from "../layers/health.js";
import * as poisLayer from "../layers/pois.js";

// Six toggleable layer chips in exact SPEC order (source: SPEC.md "HUD (glassmorphism)", TASKS_A.md A2, certainty: verified),
// plus a seventh «Δήμος» chip added last (TASKS_A.md A10, DECISIONS.md A-40: an addition to the SPEC's six).
// Citizen reports (layers/reports.js) are always on and intentionally excluded from CHIPS.
export const CHIPS = Object.freeze([
  Object.freeze({
    id: envLayer.id,
    label: envLayer.label,
    layerIds: envLayer.layerIds,
  }),
  Object.freeze({
    id: accessLayer.id,
    label: accessLayer.label,
    layerIds: accessLayer.layerIds,
  }),
  Object.freeze({
    id: worksLayer.id,
    label: worksLayer.label,
    layerIds: worksLayer.layerIds,
  }),
  Object.freeze({
    id: transitLayer.BUSES_ID,
    label: transitLayer.BUSES_LABEL,
    layerIds: transitLayer.busLayerIds,
  }),
  Object.freeze({
    id: transitLayer.RAIL_ID,
    label: transitLayer.RAIL_LABEL,
    layerIds: transitLayer.railLayerIds,
  }),
  Object.freeze({
    id: healthLayer.id,
    label: healthLayer.label,
    layerIds: healthLayer.layerIds,
  }),
  Object.freeze({
    id: poisLayer.id,
    label: poisLayer.label,
    layerIds: poisLayer.layerIds,
  }),
]);

function applyLayerVisibility(map, layerIds, isVisible) {
  if (!map || typeof map.setLayoutProperty !== "function") {
    return;
  }
  const visibility = isVisible ? "visible" : "none";
  for (const layerId of layerIds) {
    if (typeof map.getLayer !== "function" || map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "visibility", visibility);
    }
  }
}

export function setChipState(chip, isVisible, state, options = {}) {
  const next = Boolean(isVisible);
  const { map = null, api = null, onToggle = null } = options;

  if (state && typeof state === "object") {
    if (!state.visible || typeof state.visible !== "object") {
      state.visible = {};
    }
    state.visible[chip.id] = next;
  }

  if (chip.id === transitLayer.BUSES_ID) {
    transitLayer.setBusesEnabled(map, api, next, state);
  } else if (chip.id === transitLayer.RAIL_ID) {
    transitLayer.setRailEnabled(map, api, next, state);
  } else {
    applyLayerVisibility(map, chip.layerIds, next);
  }

  if (typeof onToggle === "function") {
    onToggle(chip.id, next);
  }

  return next;
}

export function initLayerBar(container, state = {}, options = {}) {
  if (!container) {
    return null;
  }

  const doc = container.ownerDocument ?? (typeof document !== "undefined" ? document : null);
  if (!doc || typeof doc.createElement !== "function") {
    return null;
  }

  if (state && typeof state === "object") {
    if (!state.visible || typeof state.visible !== "object") {
      state.visible = {};
    }
    if (state.is3D === undefined) {
      state.is3D = true;
    }
  }

  container.classList?.add("glass", "glass-pill", "layerbar");
  container.replaceChildren();

  const buttons = [];
  const focusables = [];

  function syncButton(btn, chip) {
    const isOn = Boolean(state?.visible?.[chip.id]);
    btn.setAttribute("aria-pressed", String(isOn));
    btn.classList?.toggle("is-active", isOn);
  }

  function wireArrowNavigation(btn) {
    btn.addEventListener("keydown", (event) => {
      const idx = focusables.indexOf(btn);
      if (idx < 0) return;
      const key = event?.key;
      let targetIndex = -1;
      if (key === "ArrowRight") {
        targetIndex = (idx + 1) % focusables.length;
      } else if (key === "ArrowLeft") {
        targetIndex = (idx - 1 + focusables.length) % focusables.length;
      } else if (key === "Home") {
        targetIndex = 0;
      } else if (key === "End") {
        targetIndex = focusables.length - 1;
      }
      if (targetIndex >= 0 && typeof focusables[targetIndex]?.focus === "function") {
        event.preventDefault?.();
        focusables[targetIndex].focus();
      }
    });
  }

  for (let i = 0; i < CHIPS.length; i += 1) {
    const chip = CHIPS[i];
    const btn = doc.createElement("button");
    btn.type = "button";
    btn.className = "layer-chip";
    btn.dataset.layer = chip.id;
    btn.textContent = chip.label;
    syncButton(btn, chip);

    btn.addEventListener("click", () => {
      const next = !Boolean(state?.visible?.[chip.id]);
      setChipState(chip, next, state, options);
      syncButton(btn, chip);
    });

    wireArrowNavigation(btn);
    buttons.push(btn);
    focusables.push(btn);
    container.appendChild(btn);
  }

  // Sleek 2D / 3D buildings pill toggle integrated into the map controls bar (UI/UX upgrade #1).
  const divider = doc.createElement("span");
  divider.className = "layerbar-divider";
  divider.setAttribute("aria-hidden", "true");
  container.appendChild(divider);

  const view3DBtn = doc.createElement("button");
  view3DBtn.type = "button";
  view3DBtn.id = "toggle-3d";
  view3DBtn.className = "view-mode-btn";
  view3DBtn.dataset.viewMode = state?.is3D === false ? "2d" : "3d";

  function sync3DButton() {
    const is3D = state?.is3D !== false;
    view3DBtn.dataset.viewMode = is3D ? "3d" : "2d";
    view3DBtn.textContent = is3D ? "3D" : "2D";
    view3DBtn.setAttribute("aria-pressed", String(is3D));
    view3DBtn.setAttribute("title", is3D ? "Προβολή 3D (πατήστε για 2D)" : "Προβολή 2D (πατήστε για 3D)");
    view3DBtn.classList?.toggle("is-active", is3D);
  }

  sync3DButton();
  view3DBtn.addEventListener("click", () => {
    const next3D = state?.is3D === false;
    set3DMode(options?.map ?? null, next3D, state);
    sync3DButton();
  });
  wireArrowNavigation(view3DBtn);
  focusables.push(view3DBtn);
  container.appendChild(view3DBtn);

  return {
    buttons,
    view3DBtn,
    sync() {
      for (let i = 0; i < CHIPS.length; i += 1) {
        syncButton(buttons[i], CHIPS[i]);
      }
      sync3DButton();
    },
  };
}
