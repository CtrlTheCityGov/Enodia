// Map core skeleton module (SPEC.md "Engine και στυλ", TASKS_A.md A0/A1).
// Does not touch document or maplibregl at import time so Node can import it safely.

const overlays = [];

export function registerOverlay(fn) {
  if (typeof fn === "function") {
    overlays.push(fn);
  }
}

export function addOverlays(map, state) {
  for (const fn of overlays) {
    fn(map, state);
  }
}

export function setTheme(_map, _theme, _state) {
  // Implemented in A1.
}

export function createMap(_container, _state) {
  // Implemented in A1.
  return null;
}
