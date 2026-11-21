// Municipal works layer skeleton (SPEC.md F2/F4, TASKS_A.md A0/A2/A3).
// Does not touch document or maplibregl at import time.

// Layer id from TASKS_A.md A2 (certainty: verified).
export const id = "works";

// Greek chip label from TASKS_A.md A2 / SPEC.md "HUD (glassmorphism)" (certainty: verified).
export const label = "Έργα";

// MapLibre layer ids added by this module (populated in A2).
export const layerIds = [];

export function register(_map, _api) {
  // Implemented in A2.
}

// --- A3 ---
// Coordination constant for the clickable works line layer shared with A3 workpopup
// (source: A3 task coordination with A2, certainty: verified).
export const WORKS_LINE_LAYER_ID = "works-line";
// --- /A3 ---
