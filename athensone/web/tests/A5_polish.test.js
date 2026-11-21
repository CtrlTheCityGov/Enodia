// A5 Polish tests: smooth bus movement, reasons highlight, EventTarget bus, WCAG #theme-toggle,
// and routing.js SecurityError / stale response guards (TASKS_A.md "### A5", SPEC.md F5, F6, Phase 3).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bootstrap } from "../js/main.js";
import * as transitLayer from "../js/layers/transit.js";
import * as routingMod from "../js/ui/routing.js";
import * as workpopup from "../js/ui/workpopup.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIR = path.resolve(__dirname, "..");

async function withGlobals(overrides, fn) {
  const previous = new Map();
  for (const key of Object.keys(overrides)) {
    previous.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
    const desc = Object.getOwnPropertyDescriptor(overrides, key);
    Object.defineProperty(globalThis, key, {
      ...desc,
      configurable: true,
    });
  }
  try {
    return await fn();
  } finally {
    for (const [key, desc] of previous.entries()) {
      if (desc === undefined) {
        delete globalThis[key];
      } else {
        Object.defineProperty(globalThis, key, desc);
      }
    }
  }
}

function camelToKebab(name) {
  return name.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`);
}

function matchesSimpleSelector(el, selector) {
  let rest = selector.trim();
  if (!rest) return false;

  const tagMatch = rest.match(/^[a-zA-Z0-9_-]+/);
  if (tagMatch) {
    if (el.tagName.toLowerCase() !== tagMatch[0].toLowerCase()) return false;
    rest = rest.slice(tagMatch[0].length);
  }

  while (rest.length > 0) {
    if (rest[0] === "#") {
      const m = rest.match(/^#([a-zA-Z0-9_-]+)/);
      if (!m || el.id !== m[1]) return false;
      rest = rest.slice(m[0].length);
    } else if (rest[0] === ".") {
      const m = rest.match(/^\.([a-zA-Z0-9_-]+)/);
      if (!m || !el.classList.contains(m[1])) return false;
      rest = rest.slice(m[0].length);
    } else if (rest[0] === "[") {
      const m = rest.match(/^\[([a-zA-Z0-9_-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\]]*)))?\]/);
      if (!m) return false;
      const attrName = m[1];
      const expected = m[2] ?? m[3] ?? m[4];
      const actual = el.getAttribute(attrName);
      if (expected === undefined) {
        if (actual === null) return false;
      } else if (actual !== expected) {
        return false;
      }
      rest = rest.slice(m[0].length);
    } else {
      return false;
    }
  }
  return true;
}

function createFakeElement(tagName, ownerDocument) {
  const attrs = new Map();
  const listeners = new Map();
  const children = [];
  let classSet = new Set();
  let text = "";
  let html = "";

  const dataset = new Proxy(
    {},
    {
      get(_target, prop) {
        if (typeof prop !== "string") return undefined;
        return attrs.get(`data-${camelToKebab(prop)}`);
      },
      set(_target, prop, value) {
        if (typeof prop === "string") {
          attrs.set(`data-${camelToKebab(prop)}`, String(value));
        }
        return true;
      },
    },
  );

  const el = {
    tagName: String(tagName).toUpperCase(),
    ownerDocument,
    parentNode: null,
    parentElement: null,
    children,
    childNodes: children,
    style: {},
    dataset,
    type: "",
    value: "",
    disabled: false,
    get id() {
      return attrs.get("id") ?? "";
    },
    set id(val) {
      attrs.set("id", String(val));
    },
    get className() {
      return [...classSet].join(" ");
    },
    set className(val) {
      classSet = new Set(String(val).split(/\s+/).filter(Boolean));
    },
    classList: {
      add(...names) {
        for (const n of names) {
          if (n) classSet.add(n);
        }
      },
      remove(...names) {
        for (const n of names) {
          classSet.delete(n);
        }
      },
      toggle(name, force) {
        if (force === true) {
          classSet.add(name);
          return true;
        }
        if (force === false) {
          classSet.delete(name);
          return false;
        }
        if (classSet.has(name)) {
          classSet.delete(name);
          return false;
        }
        classSet.add(name);
        return true;
      },
      contains(name) {
        return classSet.has(name);
      },
    },
    get textContent() {
      if (children.length === 0) return text;
      return text + children.map((c) => c.textContent).join("");
    },
    set textContent(val) {
      children.length = 0;
      text = val == null ? "" : String(val);
    },
    get innerHTML() {
      return html;
    },
    set innerHTML(val) {
      html = String(val);
      if (html === "") {
        children.length = 0;
        text = "";
      }
    },
    get offsetHeight() {
      return 240;
    },
    get clientHeight() {
      return 240;
    },
    getBoundingClientRect() {
      return { width: 360, height: 240, top: 0, left: 0, right: 360, bottom: 240 };
    },
    setAttribute(name, val) {
      const key = String(name).toLowerCase();
      if (key === "class") {
        el.className = String(val);
      } else {
        attrs.set(key, String(val));
      }
    },
    getAttribute(name) {
      const key = String(name).toLowerCase();
      if (key === "class") return el.className || null;
      return attrs.has(key) ? attrs.get(key) : null;
    },
    hasAttribute(name) {
      return attrs.has(String(name).toLowerCase());
    },
    removeAttribute(name) {
      attrs.delete(String(name).toLowerCase());
    },
    appendChild(child) {
      if (child && typeof child === "object") {
        child.parentNode = el;
        child.parentElement = el;
      }
      children.push(child);
      return child;
    },
    append(...nodes) {
      for (const n of nodes) {
        if (typeof n === "string") {
          text += n;
        } else if (n) {
          el.appendChild(n);
        }
      }
    },
    replaceChildren(...nodes) {
      children.length = 0;
      text = "";
      el.append(...nodes);
    },
    remove() {
      if (el.parentNode) {
        const idx = el.parentNode.children.indexOf(el);
        if (idx !== -1) el.parentNode.children.splice(idx, 1);
        el.parentNode = null;
      }
    },
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    removeEventListener(type, fn) {
      if (!listeners.has(type)) return;
      listeners.set(
        type,
        listeners.get(type).filter((cb) => cb !== fn),
      );
    },
    dispatchEvent(evt) {
      const eventObj = {
        preventDefault() {},
        stopPropagation() {},
        ...evt,
        target: evt?.target ?? el,
        currentTarget: el,
      };
      for (const fn of [...(listeners.get(eventObj.type) ?? [])]) {
        fn(eventObj);
      }
      return true;
    },
    click() {
      el.dispatchEvent({ type: "click" });
    },
    querySelectorAll(selector) {
      const selectors = selector.split(",").map((s) => s.trim()).filter(Boolean);
      const matches = [];
      function walk(node) {
        for (const child of node.children) {
          if (typeof child === "string") continue;
          if (selectors.some((sel) => matchesSimpleSelector(child, sel))) {
            matches.push(child);
          }
          walk(child);
        }
      }
      walk(el);
      return matches;
    },
    querySelector(selector) {
      return el.querySelectorAll(selector)[0] ?? null;
    },
  };

  return el;
}

function createFakeDocument(withHudElements = false) {
  const byId = new Map();
  const doc = {
    documentElement: { dataset: { theme: "light" } },
    createElement(tag) {
      return createFakeElement(tag, doc);
    },
    createTextNode(str) {
      return String(str);
    },
    getElementById(id) {
      return byId.get(id) ?? null;
    },
  };

  if (withHudElements) {
    const ids = [
      ["map", "div"],
      ["hud-tabs", "div"],
      ["tab-map", "button"],
      ["tab-works", "button"],
      ["theme-toggle", "button"],
      ["hud-layerbar", "nav"],
      ["hud-points", "div"],
      ["hud-report", "div"],
      ["hud-routing", "div"],
      ["hud-stoa", "div"],
      ["hud-offline", "div"],
    ];
    for (const [id, tag] of ids) {
      const el = createFakeElement(tag, doc);
      el.id = id;
      byId.set(id, el);
    }
  }

  return doc;
}

function createFakeMap() {
  const listeners = new Map();
  const onceListeners = new Map();
  const layerListeners = new Map();
  const layers = new Map();
  const sources = new Map();
  const layoutProps = new Map();
  const paintProps = new Map();
  const flyToCalls = [];
  const fitBoundsCalls = [];
  const setDataCounts = new Map();

  const fakeMap = {
    flyToCalls,
    fitBoundsCalls,
    setDataCounts,
    on(event, layerOrFn, maybeFn) {
      if (typeof layerOrFn === "string" && typeof maybeFn === "function") {
        const key = `${event}:${layerOrFn}`;
        if (!layerListeners.has(key)) layerListeners.set(key, []);
        layerListeners.get(key).push(maybeFn);
      } else if (typeof layerOrFn === "function") {
        if (!listeners.has(event)) listeners.set(event, []);
        listeners.get(event).push(layerOrFn);
      }
      return fakeMap;
    },
    once(event, fn) {
      if (!onceListeners.has(event)) onceListeners.set(event, []);
      onceListeners.get(event).push(fn);
      return fakeMap;
    },
    off(event, layerOrFn, maybeFn) {
      if (typeof layerOrFn === "string" && typeof maybeFn === "function") {
        const key = `${event}:${layerOrFn}`;
        if (layerListeners.has(key)) {
          layerListeners.set(key, layerListeners.get(key).filter((cb) => cb !== maybeFn));
        }
      } else if (typeof layerOrFn === "function" && listeners.has(event)) {
        listeners.set(event, listeners.get(event).filter((cb) => cb !== layerOrFn));
      }
      return fakeMap;
    },
    _emit(event, payload = {}) {
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
    _emitLayer(event, layerId, payload = {}) {
      const key = `${event}:${layerId}`;
      for (const fn of [...(layerListeners.get(key) ?? [])]) {
        fn(payload);
      }
    },
    getStyle() {
      return { version: 8, sources: { openmaptiles: { type: "vector" } }, layers: [] };
    },
    setStyle() {
      layers.clear();
      sources.clear();
      return fakeMap;
    },
    isStyleLoaded() {
      return false;
    },
    getLayer(id) {
      return layers.get(id);
    },
    addLayer(layer) {
      layers.set(layer.id, {
        ...layer,
        layout: layer.layout ? { ...layer.layout } : {},
        paint: layer.paint ? { ...layer.paint } : {},
      });
      return fakeMap;
    },
    removeLayer(id) {
      layers.delete(id);
      return fakeMap;
    },
    getSource(id) {
      return sources.get(id);
    },
    addSource(id, source) {
      const src = {
        ...source,
        setData(data) {
          src.data = data;
          setDataCounts.set(id, (setDataCounts.get(id) ?? 0) + 1);
        },
      };
      sources.set(id, src);
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
      return layoutProps.get(`${layerId}:${name}`) ?? layers.get(layerId)?.layout?.[name];
    },
    setPaintProperty(layerId, name, value) {
      paintProps.set(`${layerId}:${name}`, value);
      const layer = layers.get(layerId);
      if (layer) {
        layer.paint = { ...layer.paint, [name]: value };
      }
      return fakeMap;
    },
    getPaintProperty(layerId, name) {
      return paintProps.get(`${layerId}:${name}`) ?? layers.get(layerId)?.paint?.[name];
    },
    getBounds() {
      return {
        getWest: () => 23.7,
        getSouth: () => 37.95,
        getEast: () => 23.77,
        getNorth: () => 38.01,
      };
    },
    getCanvas() {
      return { style: {} };
    },
    flyTo(opts) {
      flyToCalls.push(opts);
      return fakeMap;
    },
    fitBounds(bounds, opts) {
      fitBoundsCalls.push({ bounds, opts });
      return fakeMap;
    },
    remove() {},
  };

  return fakeMap;
}

// Verify interpolateBuses interpolates matching bus IDs linearly at t = 0.5 and passes new buses unchanged.
test("test_bus_interpolation_midpoint", () => {
  assert.equal(
    typeof transitLayer.interpolateBuses,
    "function",
    "layers/transit.js must export interpolateBuses(prevFC, nextFC, t)",
  );

  const prevFC = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [23.72, 37.97] },
        properties: { id: "bus-1", line: "040" },
      },
      {
        type: "Feature",
        id: "bus-2",
        geometry: { type: "Point", coordinates: [23.74, 37.98] },
        properties: { line: "A2" },
      },
    ],
  };

  const nextFC = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [23.74, 37.99] },
        properties: { id: "bus-1", line: "040" },
      },
      {
        type: "Feature",
        id: "bus-2",
        geometry: { type: "Point", coordinates: [23.76, 38.0] },
        properties: { line: "A2" },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [23.735, 37.975] },
        properties: { id: "bus-new", line: "227" },
      },
    ],
  };

  const result = transitLayer.interpolateBuses(prevFC, nextFC, 0.5);
  assert.equal(result?.type, "FeatureCollection");
  assert.equal(result?.features?.length, 3);

  const bus1 = result.features.find((f) => f.properties?.id === "bus-1");
  const bus2 = result.features.find((f) => f.id === "bus-2" || f.properties?.id === "bus-2");
  const busNew = result.features.find((f) => f.properties?.id === "bus-new");

  assert.ok(bus1, "matching bus by properties.id must be present");
  assert.ok(Math.abs(bus1.geometry.coordinates[0] - 23.73) < 1e-9);
  assert.ok(Math.abs(bus1.geometry.coordinates[1] - 37.98) < 1e-9);

  assert.ok(bus2, "matching bus by feature.id must be present");
  assert.ok(Math.abs(bus2.geometry.coordinates[0] - 23.75) < 1e-9);
  assert.ok(Math.abs(bus2.geometry.coordinates[1] - 37.99) < 1e-9);

  assert.ok(busNew, "newly appearing bus must be included");
  assert.deepEqual(busNew.geometry.coordinates, [23.735, 37.975]);
});

// Verify toggling buses off cancels any in-flight rAF animation and stops further setData calls.
test("test_bus_animation_stops_on_toggle_off", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });

  let now = 0;
  let nextRafId = 1;
  let rafQueue = [];
  const rafRequested = [];
  const cancelRafCalls = [];

  function fakeRaf(cb) {
    const id = nextRafId++;
    rafRequested.push(id);
    rafQueue.push({ id, cb });
    return id;
  }

  function fakeCancelRaf(id) {
    cancelRafCalls.push(id);
    rafQueue = rafQueue.filter((item) => item.id !== id);
  }

  function stepRaf(ms) {
    now = ms;
    const batch = rafQueue;
    rafQueue = [];
    for (const item of batch) {
      item.cb(now);
    }
  }

  let pollIndex = 0;
  const snapshots = [
    {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [23.72, 37.97] },
          properties: { id: "bus-1" },
        },
      ],
    },
    {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [23.74, 37.99] },
          properties: { id: "bus-1" },
        },
      ],
    },
  ];

  const fakeMap = createFakeMap();
  const fakeApi = {
    async transit() {
      const buses = snapshots[Math.min(pollIndex, snapshots.length - 1)];
      pollIndex += 1;
      return {
        lines: { type: "FeatureCollection", features: [] },
        stations: { type: "FeatureCollection", features: [] },
        buses,
      };
    },
  };
  const state = { visible: { [transitLayer.BUSES_ID]: false } };

  await withGlobals(
    {
      requestAnimationFrame: fakeRaf,
      cancelAnimationFrame: fakeCancelRaf,
      performance: { now: () => now },
    },
    async () => {
      try {
        await transitLayer.register(fakeMap, fakeApi, state);
        transitLayer.setBusesEnabled(fakeMap, fakeApi, true, state);
        await Promise.resolve();
        await Promise.resolve();

        // Advance 20 s to receive the second bus snapshot and start rAF interpolation.
        t.mock.timers.tick(transitLayer.BUS_POLL_INTERVAL_MS);
        await Promise.resolve();
        await Promise.resolve();

        assert.ok(rafRequested.length > 0, "bus position update must schedule requestAnimationFrame");
        stepRaf(50);

        const setDataBeforeOff = fakeMap.setDataCounts.get("transit-buses-source") ?? 0;

        transitLayer.setBusesEnabled(fakeMap, fakeApi, false, state);
        assert.ok(
          cancelRafCalls.length > 0,
          "toggling buses off must call cancelAnimationFrame for in-flight animation",
        );

        // Even if timers advance or a stale frame runs, no further bus setData updates occur.
        stepRaf(500);
        t.mock.timers.tick(transitLayer.BUS_POLL_INTERVAL_MS);
        await Promise.resolve();
        await Promise.resolve();

        const setDataAfterOff = fakeMap.setDataCounts.get("transit-buses-source") ?? 0;
        assert.equal(
          setDataAfterOff,
          setDataBeforeOff,
          "no further setData updates may occur after buses are toggled off",
        );
      } finally {
        transitLayer.stopBusPolling(fakeMap);
        t.mock.timers.reset();
      }
    },
  );
});

// Verify highlightReasons adds/populates route-reasons-highlight with matched features and clears on [].
test("test_reasons_highlight_renders_matching_features", () => {
  assert.equal(
    typeof routingMod.highlightReasons,
    "function",
    "ui/routing.js must export highlightReasons(map, reasons, lookup)",
  );

  const fakeMap = createFakeMap();
  const lookup = {
    works: {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          id: "w1",
          properties: { id: "w1", title: "Ανάπλαση Ερμού" },
          geometry: { type: "LineString", coordinates: [[23.73, 37.97], [23.74, 37.98]] },
        },
        {
          type: "Feature",
          id: "w2",
          properties: { id: "w2", title: "Άλλο έργο" },
          geometry: { type: "LineString", coordinates: [[23.71, 37.96], [23.72, 37.97]] },
        },
      ],
    },
    env: {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          id: "e1",
          properties: { id: "e1", temp_c: 29 },
          geometry: { type: "Point", coordinates: [23.735, 37.976] },
        },
      ],
    },
  };

  const reasons = [
    { text: "αποφεύγει έργο Ερμού", layer: "works", feature_id: "w1" },
    { text: "−2°C σκιά", layer: "env", feature_id: "e1" },
  ];

  routingMod.highlightReasons(fakeMap, reasons, lookup);

  const layer = fakeMap.getLayer("route-reasons-highlight");
  assert.ok(layer, "highlightReasons must add the route-reasons-highlight layer");
  const src = fakeMap.getSource(layer.source);
  assert.ok(src && src.data?.type === "FeatureCollection", "highlight layer must use a GeoJSON source");
  assert.equal(src.data.features.length, 2, "must populate exactly the 2 matched reason features");

  const ids = src.data.features.map((f) => f.properties?.id ?? f.id);
  assert.ok(ids.includes("w1"), "matched works feature w1 must be highlighted");
  assert.ok(ids.includes("e1"), "matched env feature e1 must be highlighted");
  assert.ok(!ids.includes("w2"), "unmatched feature w2 must not be highlighted");

  routingMod.highlightReasons(fakeMap, [], lookup);
  assert.equal(
    src.data.features.length,
    0,
    "passing empty reasons [] must clear highlighted features to 0",
  );
});

// Verify dispatching map:flyto on result.bus moves the map to { center: [lon, lat], zoom: 17, pitch: 60 }.
test("test_bus_flyto_moves_map_to_spec_camera", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const fakeDoc = createFakeDocument(true);
  const fakeMap = createFakeMap();

  await withGlobals(
    {
      document: fakeDoc,
      maplibregl: {
        Map: class FakeMapLibreMap {
          constructor() {
            return fakeMap;
          }
        },
      },
    },
    async () => {
      try {
        const result = await bootstrap(fakeDoc, {
          optional: {
            "./api.js": null,
            "./ui/points.js": null,
            "./ui/report.js": null,
            "./ui/stoa.js": null,
            "./ui/workstab.js": null,
          },
        });

        assert.ok(result?.bus instanceof EventTarget, "bootstrap() must return bus as an EventTarget");

        const lon = 23.7257;
        const lat = 37.9764;
        result.bus.dispatchEvent(
          new CustomEvent("map:flyto", { detail: { lon, lat, label: "Οδός Ερμού" } }),
        );

        assert.equal(fakeMap.flyToCalls.length, 1, "map:flyto must call map.flyTo once");
        assert.deepEqual(fakeMap.flyToCalls[0].center, [lon, lat]);
        assert.equal(fakeMap.flyToCalls[0].zoom, 17);
        assert.equal(fakeMap.flyToCalls[0].pitch, 60);
      } finally {
        t.mock.timers.reset();
      }
    },
  );
});

// Verify bootstrap() mounts each loaded Dev B UI module with { map, api, root, bus }.
test("test_bus_mounts_dev_b_ui_modules", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const fakeDoc = createFakeDocument(true);
  const fakeMap = createFakeMap();
  const fakeApi = {
    async offlineBase() {
      return { type: "FeatureCollection", features: [] };
    },
  };

  const mounted = {
    points: [],
    report: [],
    stoa: [],
    workstab: [],
  };

  await withGlobals(
    {
      document: fakeDoc,
      maplibregl: {
        Map: class FakeMapLibreMap {
          constructor() {
            return fakeMap;
          }
        },
      },
    },
    async () => {
      try {
        const result = await bootstrap(fakeDoc, {
          optional: {
            "./api.js": fakeApi,
            "./ui/points.js": { mount: (ctx) => mounted.points.push(ctx) },
            "./ui/report.js": { mount: (ctx) => mounted.report.push(ctx) },
            "./ui/stoa.js": { mount: (ctx) => mounted.stoa.push(ctx) },
            "./ui/workstab.js": { mount: (ctx) => mounted.workstab.push(ctx) },
          },
        });

        assert.ok(result?.bus instanceof EventTarget, "bootstrap() must create an EventTarget bus");

        for (const name of ["points", "report", "stoa", "workstab"]) {
          assert.equal(mounted[name].length, 1, `${name}.mount() must be called once`);
          const ctx = mounted[name][0];
          assert.equal(ctx.map, fakeMap, `${name}.mount() must receive map`);
          assert.equal(ctx.api, fakeApi, `${name}.mount() must receive api`);
          assert.equal(ctx.root, fakeDoc, `${name}.mount() must receive root`);
          assert.equal(ctx.bus, result.bus, `${name}.mount() must receive shared bus`);
          assert.ok(ctx.bus instanceof EventTarget, `${name}.mount() ctx.bus must be EventTarget`);
        }
      } finally {
        t.mock.timers.reset();
      }
    },
  );
});

// Verify clicking «Ανέφερε πρόοδο» in workpopup dispatches report:open with detail.work_id on bus.
test("test_workpopup_dispatches_report_open_on_bus", () => {
  const fakeDoc = createFakeDocument();
  const fakeMap = createFakeMap();
  const bus = new EventTarget();
  const events = [];
  bus.addEventListener("report:open", (e) => events.push(e));

  let reportBtn = null;
  let lastHtml = "";

  class FakePopup {
    setLngLat() {
      return this;
    }
    setHTML(html) {
      lastHtml = html;
      if (html.includes("work-popup__report-btn")) {
        reportBtn = fakeDoc.createElement("button");
        reportBtn.className = "work-popup__report-btn";
      }
      return this;
    }
    addTo() {
      return this;
    }
    getElement() {
      return {
        querySelector(sel) {
          return sel === ".work-popup__report-btn" ? reportBtn : null;
        },
      };
    }
    remove() {}
  }

  workpopup.initWorkPopup(fakeMap, {
    bus,
    maplibregl: { Popup: FakePopup },
  });

  fakeMap._emitLayer("click", "works-line", {
    lngLat: { lng: 23.7348, lat: 37.9755 },
    features: [
      {
        properties: {
          id: "work-42",
          title: "Ανάπλαση Ερμού",
          status: "in_progress",
          contractor: "ΤΕΡΝΑ Α.Ε.",
        },
      },
    ],
  });

  assert.ok(
    lastHtml.includes("Ανέφερε πρόοδο") && reportBtn !== null,
    "workpopup must render «Ανέφερε πρόοδο» when bus is provided",
  );

  reportBtn.click();
  assert.equal(events.length, 1, "clicking report button must dispatch report:open on bus");
  assert.equal(events[0].type, "report:open");
  assert.equal(events[0].detail?.work_id, "work-42");
});

// Verify #theme-toggle in citizen.html satisfies WCAG 2.5.3 (no aria-label omitting visible Greek text).
test("test_theme_toggle_wcag_label_in_name", () => {
  const html = fs
    .readFileSync(path.join(WEB_DIR, "citizen.html"), "utf8")
    .replace(/<!--[\s\S]*?-->/g, "");

  const match = html.match(/<button\b([^>]*\bid\s*=\s*["']theme-toggle["'][^>]*)>([\s\S]*?)<\/button>/i);
  assert.ok(match, "citizen.html must contain a #theme-toggle button");

  const attrs = match[1];
  const visibleText = match[2].replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
  assert.ok(visibleText.length > 0, "#theme-toggle must have visible Greek button text");

  const ariaLabelMatch = attrs.match(/\baria-label\s*=\s*(?:"([^"]*)"|'([^']*)')/i);
  if (ariaLabelMatch) {
    const ariaLabel = (ariaLabelMatch[1] ?? ariaLabelMatch[2] ?? "").replace(/\s+/g, " ").trim();
    assert.ok(
      ariaLabel.toLocaleLowerCase("el").includes(visibleText.toLocaleLowerCase("el")),
      `WCAG 2.5.3: #theme-toggle aria-label "${ariaLabel}" must include visible text "${visibleText}"`,
    );
  }
});

// Verify routing.js catches localStorage SecurityError and ignores stale out-of-order async responses.
test("test_routing_ignores_stale_async_response_and_storage_security_error", async () => {
  const fakeDoc = createFakeDocument();
  const container = fakeDoc.createElement("div");
  const fakeMap = createFakeMap();

  const pendingResolvers = [];
  const fakeApi = {
    async routing() {
      return new Promise((resolve) => {
        pendingResolvers.push(resolve);
      });
    },
  };

  await withGlobals(
    {
      document: fakeDoc,
      get localStorage() {
        const err = new Error("Access to localStorage is denied");
        err.name = "SecurityError";
        throw err;
      },
    },
    async () => {
      let controller;
      assert.doesNotThrow(() => {
        controller = routingMod.initRouting(container, fakeMap, fakeApi);
      }, "initRouting must not throw when localStorage getter throws SecurityError");

      const coolBtn = container.querySelector('[data-profile="cool"]');
      assert.ok(coolBtn, "cool profile button must render");
      assert.doesNotThrow(() => {
        coolBtn.click();
      }, "clicking profile button must not throw when localStorage getter throws SecurityError");

      const fromInput = container.querySelector("#routing-from");
      const toInput = container.querySelector("#routing-to");
      fromInput.value = "Σύνταγμα";
      toInput.value = "Μοναστηράκι";

      const req1Promise = controller.requestRoute();
      const req2Promise = controller.requestRoute();
      assert.equal(pendingResolvers.length, 2, "both routing requests must be in flight");

      const route2 = {
        source: "live",
        distance_m: 800,
        duration_s: 600,
        reasons: [{ text: "Νεότερη διαδρομή 2", layer: "works", feature_id: "w2" }],
        geometry: {
          type: "LineString",
          coordinates: [
            [23.7348, 37.9755],
            [23.731, 37.976],
          ],
        },
      };
      const route1 = {
        source: "live",
        distance_m: 2500,
        duration_s: 1800,
        reasons: [{ text: "Παλιά διαδρομή 1", layer: "works", feature_id: "w1" }],
        geometry: {
          type: "LineString",
          coordinates: [
            [23.71, 37.95],
            [23.72, 37.96],
          ],
        },
      };

      // Fast request #2 resolves before slow request #1.
      pendingResolvers[1](route2);
      await req2Promise;

      pendingResolvers[0](route1);
      await req1Promise;

      const routeSrc = fakeMap.getSource("route");
      assert.ok(routeSrc?.data?.geometry, "route #2 must remain drawn on the map");
      assert.deepEqual(
        routeSrc.data.geometry.coordinates,
        route2.geometry.coordinates,
        "stale route #1 must not overwrite newer route #2",
      );

      const summary = container.querySelector(".routing-summary");
      assert.ok(summary.textContent.includes("Νεότερη διαδρομή 2"));
      assert.ok(!summary.textContent.includes("Παλιά διαδρομή 1"));
    },
  );
});
