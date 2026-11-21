// A1 Map core tests (TASKS_A.md "### A1", SPEC.md "Engine και στυλ" & "Offline fallback" 1-2).
import test from "node:test";
import assert from "node:assert/strict";
import * as mapMod from "../js/map.js";

const FIORD_STYLE_URL = "https://tiles.openfreemap.org/styles/fiord";

function createFakeMap(options = {}) {
  const listeners = new Map();
  const onceListeners = new Map();
  const layers = new Map();
  const sources = new Map();
  const layoutProps = new Map();
  const setStyleCalls = [];

  let styleLoaded = false;
  let currentStyle =
    options.style && typeof options.style === "object"
      ? options.style
      : { version: 8, sources: { openmaptiles: { type: "vector" } }, layers: [] };

  const fakeMap = {
    options,
    setStyleCalls,
    on(event, fn) {
      if (!listeners.has(event)) listeners.set(event, []);
      listeners.get(event).push(fn);
      return fakeMap;
    },
    once(event, fn) {
      if (!onceListeners.has(event)) onceListeners.set(event, []);
      onceListeners.get(event).push(fn);
      return fakeMap;
    },
    off(event, fn) {
      if (listeners.has(event)) {
        listeners.set(
          event,
          listeners.get(event).filter((cb) => cb !== fn),
        );
      }
      if (onceListeners.has(event)) {
        onceListeners.set(
          event,
          onceListeners.get(event).filter((cb) => cb !== fn),
        );
      }
      return fakeMap;
    },
    getStyle() {
      return currentStyle;
    },
    setStyle(style) {
      setStyleCalls.push(style);
      layers.clear();
      sources.clear();
      layoutProps.clear();
      styleLoaded = false;
      currentStyle =
        style && typeof style === "object"
          ? style
          : { version: 8, sources: { openmaptiles: { type: "vector" } }, layers: [] };
      return fakeMap;
    },
    getLayer(id) {
      return layers.get(id);
    },
    addLayer(layer) {
      layers.set(layer.id, layer);
      return fakeMap;
    },
    removeLayer(id) {
      layers.delete(id);
      return fakeMap;
    },
    getSource(id) {
      return sources.get(id) ?? currentStyle.sources?.[id];
    },
    addSource(id, source) {
      sources.set(id, source);
      return fakeMap;
    },
    removeSource(id) {
      sources.delete(id);
      return fakeMap;
    },
    setLayoutProperty(layerId, name, value) {
      layoutProps.set(`${layerId}:${name}`, value);
      const layer = layers.get(layerId);
      if (layer) {
        layer.layout = { ...layer.layout, [name]: value };
      }
      return fakeMap;
    },
    getLayoutProperty(layerId, name) {
      return layoutProps.get(`${layerId}:${name}`);
    },
    isStyleLoaded() {
      return styleLoaded;
    },
    loaded() {
      return styleLoaded;
    },
    remove() {},
    _emit(event, payload = {}) {
      if (event === "style.load") {
        styleLoaded = true;
      }
      for (const fn of [...(listeners.get(event) ?? [])]) {
        fn(payload);
      }
      const once = onceListeners.get(event);
      if (once && once.length > 0) {
        onceListeners.set(event, []);
        for (const fn of once) {
          fn(payload);
        }
      }
    },
  };

  return fakeMap;
}

function assertOfflineStyle(style) {
  assert.ok(style && typeof style === "object", "offline style must be an object");
  assert.equal(style.version, 8);
  assert.ok(Array.isArray(style.layers), "offline style must have a layers array");
  assert.ok(
    style.layers.some((layer) => layer.type === "background"),
    "offline style must include a background layer",
  );
  const sourceValues = Object.values(style.sources ?? {});
  for (const src of sourceValues) {
    assert.equal(src.type, "geojson", "offline style must not contain tile sources");
    assert.equal(src.tiles, undefined);
    assert.equal(src.url, undefined);
  }
}

// Verify CAMERA matches SPEC initial Syntagma center, zoom, pitch, bearing, and maxPitch.
test("test_camera_matches_spec", () => {
  const { CAMERA } = mapMod;
  assert.ok(CAMERA && typeof CAMERA === "object", "CAMERA export must exist");
  assert.deepEqual(CAMERA.center, [23.7348, 37.9755]);
  assert.equal(CAMERA.zoom, 15);
  assert.equal(CAMERA.pitch, 55);
  assert.equal(CAMERA.bearing, -15);
  assert.equal(CAMERA.maxPitch, 70);
});

// Verify needs3dBuildings returns true when a style has no fill-extrusion layer.
test("test_needs_3d_when_no_fill_extrusion", () => {
  const styleWithout3d = {
    version: 8,
    layers: [
      { id: "background", type: "background" },
      { id: "roads", type: "line" },
    ],
  };
  assert.equal(mapMod.needs3dBuildings(styleWithout3d), true);
});

// Verify needs3dBuildings returns false when a style already includes a fill-extrusion layer.
test("test_no_3d_when_style_has_fill_extrusion", () => {
  const styleWith3d = {
    version: 8,
    layers: [
      { id: "background", type: "background" },
      { id: "building-3d", type: "fill-extrusion" },
    ],
  };
  assert.equal(mapMod.needs3dBuildings(styleWith3d), false);
});

// Verify buildingsLayer returns the 3d-buildings fill-extrusion layer matching SPEC.
test("test_buildings_layer_spec", () => {
  const layer = mapMod.buildingsLayer();
  assert.ok(layer && typeof layer === "object", "buildingsLayer() must return a layer object");
  assert.equal(layer.id, "3d-buildings");
  assert.equal(layer.type, "fill-extrusion");
  assert.equal(layer.source, "openmaptiles");
  assert.equal(layer["source-layer"], "building");
  assert.equal(layer.minzoom, 14);
  assert.ok(layer.paint && typeof layer.paint === "object");
  assert.ok(
    JSON.stringify(layer.paint["fill-extrusion-height"]).includes("render_height"),
    "fill-extrusion-height must reference render_height",
  );
  assert.ok(
    JSON.stringify(layer.paint["fill-extrusion-base"]).includes("render_min_height"),
    "fill-extrusion-base must reference render_min_height",
  );
});

// Verify addOverlays runs registered overlays and applies state.visible toggle visibility.
test("test_add_overlays_restores_toggle_state", () => {
  const fakeMap = createFakeMap();
  const state = { visible: { works: true, env: false } };
  let active = true;

  mapMod.registerOverlay((m) => {
    if (!active) return;
    m.addLayer({ id: "works", type: "line" });
    m.addLayer({ id: "env", type: "heatmap" });
  });

  try {
    mapMod.addOverlays(fakeMap, state);
    assert.equal(fakeMap.getLayoutProperty("works", "visibility"), "visible");
    assert.equal(fakeMap.getLayoutProperty("env", "visibility"), "none");
  } finally {
    active = false;
  }
});

// Verify setTheme switches to Fiord and re-adds all overlays with toggle state intact on style.load.
test("test_set_theme_keeps_overlays", () => {
  const fakeMap = createFakeMap();
  const state = { theme: "light", visible: { works: true, env: false } };
  let active = true;
  let worksCalls = 0;
  let envCalls = 0;

  mapMod.registerOverlay((m) => {
    if (!active) return;
    worksCalls += 1;
    m.addLayer({ id: "works", type: "line" });
  });
  mapMod.registerOverlay((m) => {
    if (!active) return;
    envCalls += 1;
    m.addLayer({ id: "env", type: "heatmap" });
  });

  try {
    mapMod.addOverlays(fakeMap, state);
    assert.equal(worksCalls, 1);
    assert.equal(envCalls, 1);

    mapMod.setTheme(fakeMap, "dark", state);
    assert.equal(fakeMap.setStyleCalls.length, 1);
    assert.equal(fakeMap.setStyleCalls[0], FIORD_STYLE_URL);

    fakeMap._emit("style.load");

    assert.equal(worksCalls, 2);
    assert.equal(envCalls, 2);
    assert.ok(fakeMap.getLayer("works"), "works overlay must be re-added after style.load");
    assert.ok(fakeMap.getLayer("env"), "env overlay must be re-added after style.load");
    assert.deepEqual(state.visible, { works: true, env: false });
    assert.equal(fakeMap.getLayoutProperty("works", "visibility"), "visible");
    assert.equal(fakeMap.getLayoutProperty("env", "visibility"), "none");
  } finally {
    active = false;
  }
});

// Verify offlineStyle returns a v8 style with a background layer and no remote tile sources.
test("test_offline_style_is_v8_background_only_base", () => {
  const geo = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { kind: "boundary" },
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [23.7, 37.95],
              [23.77, 37.95],
              [23.77, 38.02],
              [23.7, 38.02],
              [23.7, 37.95],
            ],
          ],
        },
      },
    ],
  };

  const style = mapMod.offlineStyle(geo);
  assertOfflineStyle(style);
});

// Verify createMap switches to the offline style if style.load does not fire within 6 s.
test("test_style_timeout_switches_offline", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const prevMaplibre = globalThis.maplibregl;
  let createdMap = null;

  globalThis.maplibregl = {
    Map: class FakeMapLibreMap {
      constructor(options) {
        createdMap = createFakeMap(options);
        return createdMap;
      }
    },
  };

  try {
    const map = mapMod.createMap({ id: "map" }, { visible: {}, theme: "light" });
    assert.ok(map, "createMap must return the map instance");
    assert.equal(createdMap.setStyleCalls.length, 0);

    t.mock.timers.tick(5999);
    assert.equal(createdMap.setStyleCalls.length, 0, "must not switch offline before 6 s");

    t.mock.timers.tick(1);
    assert.equal(createdMap.setStyleCalls.length, 1);
    assertOfflineStyle(createdMap.setStyleCalls[0]);
  } finally {
    t.mock.timers.reset();
    if (prevMaplibre === undefined) {
      delete globalThis.maplibregl;
    } else {
      globalThis.maplibregl = prevMaplibre;
    }
  }
});

// Verify createMap switches to the offline style once when the map emits an error event.
test("test_style_error_switches_offline", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const prevMaplibre = globalThis.maplibregl;
  let createdMap = null;

  globalThis.maplibregl = {
    Map: class FakeMapLibreMap {
      constructor(options) {
        createdMap = createFakeMap(options);
        return createdMap;
      }
    },
  };

  try {
    const map = mapMod.createMap({ id: "map" }, { visible: {}, theme: "light" });
    assert.ok(map, "createMap must return the map instance");

    createdMap._emit("error", { error: new Error("style load failed") });
    assert.equal(createdMap.setStyleCalls.length, 1);
    assertOfflineStyle(createdMap.setStyleCalls[0]);

    // Subsequent errors or the 6 s timer must not trigger another offline switch.
    createdMap._emit("error", { error: new Error("tile error") });
    t.mock.timers.tick(6000);
    assert.equal(createdMap.setStyleCalls.length, 1);
  } finally {
    t.mock.timers.reset();
    if (prevMaplibre === undefined) {
      delete globalThis.maplibregl;
    } else {
      globalThis.maplibregl = prevMaplibre;
    }
  }
});
