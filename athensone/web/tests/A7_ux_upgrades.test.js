// A7 UI/UX upgrades regression tests:
// 1. 2D / 3D buildings toggle
// 2. 3D buildings in Dark & Light mode across style.load
// 3. macOS-style spring / fold animations & glassmorphism CSS
// 4. Persistent newly submitted report pins + refresh merge
// 5. Auto-close report modal + toast notification on submit
// 6. Real GPS turn-by-turn navigation helpers + instant Waze "Report Here"
// 7. Route glow halo layer & UI/UX polish invariants
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as mapMod from "../js/map.js";
import * as layerbar from "../js/ui/layerbar.js";
import * as reportsLayer from "../js/layers/reports.js";
import * as routing from "../js/ui/routing.js";
import * as stoa from "../js/ui/stoa.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIR = path.resolve(__dirname, "..");

function createFakeMap({ styleLayers = [] } = {}) {
  const sources = new Map();
  const layers = new Map();
  const layoutProps = new Map();
  const paintProps = new Map();
  const easeCalls = [];
  const style = {
    version: 8,
    sources: { openmaptiles: { type: "vector" } },
    layers: [...styleLayers],
  };
  for (const l of styleLayers) {
    if (l?.id) layers.set(l.id, l);
  }

  return {
    sources,
    layers,
    layoutProps,
    paintProps,
    easeCalls,
    getStyle() {
      return style;
    },
    getSource(id) {
      return sources.get(id) ?? style.sources[id];
    },
    addSource(id, def) {
      const src = {
        ...def,
        data: def.data,
        setData(next) {
          src.data = next;
        },
      };
      sources.set(id, src);
      return this;
    },
    getLayer(id) {
      return layers.get(id);
    },
    addLayer(layer) {
      layers.set(layer.id, layer);
      style.layers.push(layer);
      return this;
    },
    setLayoutProperty(layerId, prop, value) {
      layoutProps.set(`${layerId}:${prop}`, value);
      return this;
    },
    setPaintProperty(layerId, prop, value) {
      paintProps.set(`${layerId}:${prop}`, value);
      return this;
    },
    easeTo(opts) {
      easeCalls.push(opts);
      return this;
    },
    on() {
      return this;
    },
    getBounds() {
      return {
        getWest: () => 23.7,
        getSouth: () => 37.96,
        getEast: () => 23.76,
        getNorth: () => 38.0,
      };
    },
  };
}

test("test_3d_buildings_light_and_dark_themes_and_2d_toggle", () => {
  const darkLayer = mapMod.buildingsLayer("dark", "openmaptiles");
  const lightLayer = mapMod.buildingsLayer("light", "openmaptiles");

  assert.equal(darkLayer.id, mapMod.BUILDINGS_LAYER_ID);
  assert.equal(darkLayer.type, "fill-extrusion");
  assert.equal(darkLayer["source-layer"], "building");
  assert.equal(darkLayer.paint["fill-extrusion-opacity"], 0.85);
  assert.notDeepEqual(darkLayer.paint["fill-extrusion-color"], lightLayer.paint["fill-extrusion-color"]);

  const fakeMap = createFakeMap();
  const state = { theme: "dark", is3D: true };
  mapMod.addOverlays(fakeMap, state);

  assert.ok(fakeMap.getLayer(mapMod.BUILDINGS_LAYER_ID), "Dark mode injects 3d-buildings layer");
  assert.equal(fakeMap.layoutProps.get(`${mapMod.BUILDINGS_LAYER_ID}:visibility`), "visible");

  mapMod.set3DMode(fakeMap, false, state);
  assert.equal(state.is3D, false);
  assert.equal(fakeMap.layoutProps.get(`${mapMod.BUILDINGS_LAYER_ID}:visibility`), "none");
  assert.deepEqual(fakeMap.easeCalls.at(-1), mapMod.CAMERA_2D);

  mapMod.set3DMode(fakeMap, true, state);
  assert.equal(state.is3D, true);
  assert.equal(fakeMap.layoutProps.get(`${mapMod.BUILDINGS_LAYER_ID}:visibility`), "visible");
  assert.deepEqual(fakeMap.easeCalls.at(-1), mapMod.CAMERA_3D);
});

test("test_set_theme_light_3d_to_dark_keeps_3d_buildings_with_diff_false", () => {
  const listeners = new Map();
  const onceListeners = new Map();
  const layers = new Map();
  const layoutProps = new Map();
  const setStyleArgs = [];

  // Start in Liberty (light) which has a native building-3d layer.
  let currentStyle = {
    version: 8,
    sources: { openmaptiles: { type: "vector" } },
    layers: [{ id: "building-3d", type: "fill-extrusion" }],
  };
  layers.set("building-3d", currentStyle.layers[0]);

  const fakeMap = {
    on(ev, fn) {
      listeners.set(ev, [...(listeners.get(ev) ?? []), fn]);
      return this;
    },
    once(ev, fn) {
      onceListeners.set(ev, [...(onceListeners.get(ev) ?? []), fn]);
      return this;
    },
    getStyle: () => currentStyle,
    getSource: (id) => currentStyle.sources[id],
    getLayer: (id) => layers.get(id),
    addLayer(layer) {
      layers.set(layer.id, layer);
      currentStyle.layers.push(layer);
      return this;
    },
    setLayoutProperty(id, prop, val) {
      layoutProps.set(`${id}:${prop}`, val);
      return this;
    },
    setStyle(url, opts) {
      setStyleArgs.push([url, opts]);
      // Simulate Fiord (dark): no fill-extrusion layer in base style.
      layers.clear();
      layoutProps.clear();
      currentStyle = {
        version: 8,
        sources: { openmaptiles: { type: "vector" } },
        layers: [{ id: "building", type: "fill" }],
      };
      layers.set("building", currentStyle.layers[0]);
      return this;
    },
  };

  const state = { theme: "light", is3D: true, visible: {} };
  mapMod.setTheme(fakeMap, "dark", state);

  assert.equal(setStyleArgs.length, 1);
  assert.equal(setStyleArgs[0][0], mapMod.STYLES.dark);
  assert.deepEqual(setStyleArgs[0][1], { diff: false });

  for (const fn of onceListeners.get("style.load") ?? []) fn();
  assert.equal(state.is3D, true);
  assert.ok(fakeMap.getLayer(mapMod.BUILDINGS_LAYER_ID), "Dark mode must immediately inject 3d-buildings");
  assert.equal(layoutProps.get(`${mapMod.BUILDINGS_LAYER_ID}:visibility`), "visible");
});

test("test_layerbar_adds_2d_3d_toggle_without_altering_six_chips", () => {
  assert.equal(layerbar.CHIPS.length, 7);

  const created = [];
  const doc = {
    createElement(tag) {
      const attrs = new Map();
      const listeners = new Map();
      const classes = new Set();
      const node = {
        tagName: tag.toUpperCase(),
        dataset: {},
        textContent: "",
        classList: {
          add: (...c) => c.forEach((x) => classes.add(x)),
          toggle: (c, force) => (force ? classes.add(c) : classes.delete(c)),
          contains: (c) => classes.has(c),
        },
        setAttribute: (k, v) => attrs.set(k, String(v)),
        getAttribute: (k) => attrs.get(k) ?? null,
        addEventListener: (ev, fn) => listeners.set(ev, fn),
        click: () => listeners.get("click")?.(),
      };
      created.push(node);
      return node;
    },
  };
  const children = [];
  const container = {
    ownerDocument: doc,
    classList: { add() {} },
    replaceChildren: () => {
      children.length = 0;
    },
    appendChild: (c) => children.push(c),
  };

  const fakeMap = createFakeMap();
  const state = { visible: {}, is3D: true };
  const bar = layerbar.initLayerBar(container, state, { map: fakeMap });

  assert.equal(bar.buttons.length, 7);
  assert.equal(bar.view3DBtn.id, "toggle-3d");
  assert.equal(bar.view3DBtn.textContent, "3D");

  bar.view3DBtn.click();
  assert.equal(state.is3D, false);
  assert.equal(bar.view3DBtn.textContent, "2D");
  assert.deepEqual(fakeMap.easeCalls.at(-1), mapMod.CAMERA_2D);
});

test("test_add_report_pin_persists_across_refresh_and_forces_visibility", async () => {
  const fakeMap = createFakeMap();
  const api = {
    async reports() {
      return {
        type: "FeatureCollection",
        source: "live",
        features: [
          {
            type: "Feature",
            id: "seed-1",
            geometry: { type: "Point", coordinates: [23.73, 37.98] },
            properties: { id: "seed-1", category: "obstacle", note: "Seed" },
          },
        ],
      };
    },
  };

  await reportsLayer.register(fakeMap, api, {});
  const added = reportsLayer.addReportPin(fakeMap, {
    id: "rep-99",
    category: "congestion",
    lon: 23.735,
    lat: 37.975,
  });

  assert.ok(added);
  assert.equal(fakeMap.layoutProps.get(`${reportsLayer.PINS_LAYER_ID}:visibility`), "visible");

  let srcData = fakeMap.getSource(reportsLayer.SOURCE_ID).data;
  assert.equal(srcData.features.length, 2);
  assert.ok(srcData.features.some((f) => f.properties.id === "rep-99"));

  // Refresh returning only seed-1 must still retain rep-99 via local merge
  await reportsLayer.refresh(fakeMap, api, {});
  srcData = fakeMap.getSource(reportsLayer.SOURCE_ID).data;
  assert.equal(srcData.features.length, 2);
  assert.ok(srcData.features.some((f) => f.properties.id === "rep-99"));
});

test("test_navigation_geometry_helpers_and_quick_hazards", () => {
  assert.equal(routing.QUICK_NAV_HAZARDS.length, 4);
  assert.ok(routing.QUICK_NAV_HAZARDS.some((h) => h.label.includes("Συμφόρηση")));

  // Due east from Syntagma -> ~90 degrees
  const eastBearing = routing.computeBearing([23.73, 37.975], [23.74, 37.975]);
  assert.ok(eastBearing > 85 && eastBearing < 95, `Expected ~90 deg, got ${eastBearing}`);

  // Due north -> ~0 or 360 degrees
  const northBearing = routing.computeBearing([23.73, 37.975], [23.73, 37.985]);
  assert.ok(northBearing < 5 || northBearing > 355, `Expected ~0 deg, got ${northBearing}`);

  const coords = [
    [23.730, 37.975],
    [23.735, 37.975],
    [23.735, 37.980],
  ];
  const start = routing.sampleRouteAtDistance(coords, 0);
  assert.equal(start.arrived, false);
  assert.ok(start.remainingM > 800);
  assert.equal(start.turn.icon, "↰");

  const end = routing.sampleRouteAtDistance(coords, 5000);
  assert.equal(end.arrived, true);
  assert.equal(end.lon, coords[2][0]);
  assert.equal(end.lat, coords[2][1]);
});

test("test_hud_css_and_citizen_html_include_ux_upgrade_hooks", () => {
  const html = fs.readFileSync(path.join(WEB_DIR, "citizen.html"), "utf8");
  const css = fs.readFileSync(path.join(WEB_DIR, "css/hud.css"), "utf8");

  assert.match(html, /id="hud-toast"/);
  assert.match(css, /--glass-blur:\s*20px/);
  assert.match(css, /--glass-saturate:\s*180%/);
  assert.match(css, /cubic-bezier\(0\.16,\s*1,\s*0\.3,\s*1\)/);
  assert.match(css, /cubic-bezier\(0\.32,\s*0\.72,\s*0,\s*1\)/);
  assert.match(css, /\.view-mode-btn\b/);
  assert.match(css, /\.hud-toast\b/);
  assert.match(css, /\.nav-hud\b/);
  assert.match(css, /\.nav-quick-report\b/);
  assert.match(css, /\.routing-why\b/);
  assert.match(css, /\.routing-why__ai-btn\b/);
});

test("test_route_insight_and_stoa_route_analysis_layers_a_b_c", () => {
  assert.equal(Object.keys(routing.PROFILE_PALETTES).length, 3);
  assert.notEqual(routing.PROFILE_PALETTES.wheelchair.start, routing.PROFILE_PALETTES.cool.start);

  const sampleRoute = {
    distance_m: 920,
    duration_s: 720,
    reasons: [{ text: "αποφεύγει έργο σε εξέλιξη (Ερμού)", layer: "works", feature_id: "W-1" }],
    comparison: {
      profile: "wheelchair",
      same_as_baseline: false,
      baseline: {
        geometry: { type: "LineString", coordinates: [[23.734, 37.975], [23.726, 37.976]] },
        distance_m: 840,
        duration_s: 660,
        shade_pct: 28,
        busy_pct: 58,
      },
      best: { shade_pct: 62, busy_pct: 14, steps_excluded: true },
      deltas: { distance_m: 80, duration_s: 60, shade_pct: 34, busy_pct: -44 },
      env: { aqi: 28, temp_c: 21.5, uv_index: 3 },
      avoided_works: [
        { id: "W-1", street: "Ερμού", title: "Ανάπλαση", ada: "Ψ123-ΑΒΓ", lon: 23.73, lat: 37.976 },
      ],
      avoided_reports: [{ id: "R-7", category: "obstacle", lon: 23.731, lat: 37.976 }],
      on_route_works: 0,
      on_route_reports: 0,
    },
  };

  const wc = routing.buildRouteInsight(sampleRoute, "wheelchair");
  assert.equal(wc.showGhostLegend, true);
  assert.equal(wc.avoidedItems.length, 2);
  assert.equal(wc.metrics.length, 3);
  assert.match(wc.detourText, /\+1′/);

  const cool = routing.buildRouteInsight(sampleRoute, "cool");
  assert.equal(cool.metrics[0].value, "62%");
  assert.match(cool.metrics[0].delta, /\+34%/);

  const stroller = routing.buildRouteInsight(sampleRoute, "stroller");
  assert.equal(stroller.metrics[0].value, "14%");
  assert.match(stroller.metrics[0].delta, /-44%/);

  // Layer C: Stoa AI route analysis generates strictly data-grounded Greek explanation + clickable citations
  const analysis = stoa.buildRouteAnalysisAnswer({
    profile: "wheelchair",
    profileLabel: "Αμαξίδιο",
    fromLabel: "Σύνταγμα",
    toLabel: "Μοναστηράκι",
    route: sampleRoute,
  });
  assert.match(analysis.answer_md, /Ερμού/);
  assert.match(analysis.answer_md, /Ψ123-ΑΒΓ/);
  assert.match(analysis.answer_md, /62%/);
  assert.equal(analysis.citations.length, 2);
  assert.equal(analysis.citations[0].lon, 23.73);
});
