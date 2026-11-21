// Layer toggle pill bar UI: six chips in exact SPEC order with aria-pressed and keyboard navigation
// (SPEC.md "HUD (glassmorphism)", TASKS_A.md A2).
// Never touches document or maplibregl at import time so Node can import it safely.

import * as envLayer from "../layers/env.js";
import * as accessLayer from "../layers/access.js";
import * as worksLayer from "../layers/works.js";
import * as transitLayer from "../layers/transit.js";
import * as healthLayer from "../layers/health.js";

// Six toggleable layer chips in exact SPEC order (source: SPEC.md "HUD (glassmorphism)", TASKS_A.md A2, certainty: verified).
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

  if (state && typeof state === "object" && (!state.visible || typeof state.visible !== "object")) {
    state.visible = {};
  }

  container.classList?.add("glass", "glass-pill", "layerbar");
  container.replaceChildren();

  const buttons = [];

  function syncButton(btn, chip) {
    const isOn = Boolean(state?.visible?.[chip.id]);
    btn.setAttribute("aria-pressed", String(isOn));
    btn.classList?.toggle("is-active", isOn);
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

    btn.addEventListener("keydown", (event) => {
      const key = event?.key;
      let targetIndex = -1;
      if (key === "ArrowRight") {
        targetIndex = (i + 1) % buttons.length;
      } else if (key === "ArrowLeft") {
        targetIndex = (i - 1 + buttons.length) % buttons.length;
      } else if (key === "Home") {
        targetIndex = 0;
      } else if (key === "End") {
        targetIndex = buttons.length - 1;
      }
      if (targetIndex >= 0 && typeof buttons[targetIndex]?.focus === "function") {
        event.preventDefault?.();
        buttons[targetIndex].focus();
      }
    });

    buttons.push(btn);
    container.appendChild(btn);
  }

  return {
    buttons,
    sync() {
      for (let i = 0; i < CHIPS.length; i += 1) {
        syncButton(buttons[i], CHIPS[i]);
      }
    },
  };
}
