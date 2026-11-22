// A2 Six layers + pill bar tests (TASKS_A.md "### A2", SPEC.md F2 & "HUD (glassmorphism)").
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as layerbar from "../js/ui/layerbar.js";
import * as envLayer from "../js/layers/env.js";
import * as worksLayer from "../js/layers/works.js";
import * as transitLayer from "../js/layers/transit.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIR = path.resolve(__dirname, "..");
const JS_DIR = path.join(WEB_DIR, "js");

// Expected chip labels in exact SPEC order (SPEC.md "HUD (glassmorphism)", TASKS_A.md A2).
const EXPECTED_CHIP_LABELS = [
  "Θερμοκρασία/AQI",
  "Προσβασιμότητα/Ράμπες",
  "Έργα",
  "Τηλεματική ΟΑΣΑ",
  "Μετρό/Προαστιακός",
  "Εφημερεύοντα",
  "Δήμος", // A10 / A-40: seventh chip, official City POIs (not in SPEC's six)
];

function createFeatureCollection(features = []) {
  return { type: "FeatureCollection", features };
}

function createFakeApi(overrides = {}) {
  return {
    async env() {
      return createFeatureCollection([
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [23.7348, 37.9755] },
          properties: { temp_c: 33.5, aqi: 68, pm25: 19, updated_at: "2026-11-21T12:00:00Z" },
        },
      ]);
    },
    async access() {
      return createFeatureCollection();
    },
    async works() {
      return createFeatureCollection([
        {
          type: "Feature",
          geometry: { type: "LineString", coordinates: [[23.73, 37.97], [23.74, 37.98]] },
          properties: { id: "w1", title: "Ανάπλαση Ερμού", status: "in_progress" },
        },
        {
          type: "Feature",
          geometry: { type: "LineString", coordinates: [[23.725, 37.978], [23.732, 37.982]] },
          properties: { id: "w2", title: "Επισκευή Σταδίου", status: "planned" },
        },
      ]);
    },
    async transit() {
      return {
        lines: createFeatureCollection(),
        stations: createFeatureCollection(),
        buses: createFeatureCollection(),
      };
    },
    async health() {
      return createFeatureCollection();
    },
    async reports() {
      return createFeatureCollection();
    },
    ...overrides,
  };
}

function createFakeMap() {
  const layers = new Map();
  const sources = new Map();
  const layoutProps = new Map();
  const paintProps = new Map();
  const listeners = new Map();

  const fakeMap = {
    on(event, fn) {
      if (!listeners.has(event)) listeners.set(event, []);
      listeners.get(event).push(fn);
      return fakeMap;
    },
    off(event, fn) {
      if (listeners.has(event)) {
        listeners.set(event, listeners.get(event).filter((cb) => cb !== fn));
      }
      return fakeMap;
    },
    getLayer(id) {
      return layers.get(id);
    },
    addLayer(layer) {
      const cloned = {
        ...layer,
        layout: layer.layout ? { ...layer.layout } : {},
        paint: layer.paint ? { ...layer.paint } : {},
      };
      layers.set(layer.id, cloned);
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
  };

  return fakeMap;
}

function createFakeElement(tagName, ownerDocument) {
  const attrs = new Map();
  const listeners = new Map();
  const classes = new Set();
  const children = [];
  let text = "";

  const dataset = new Proxy(
    {},
    {
      get(_target, prop) {
        if (typeof prop !== "string") return undefined;
        const attrName = `data-${prop.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}`;
        return attrs.get(attrName);
      },
      set(_target, prop, value) {
        if (typeof prop !== "string") return false;
        const attrName = `data-${prop.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}`;
        attrs.set(attrName, String(value));
        return true;
      },
    },
  );

  function collectText(node) {
    if (typeof node === "string") return node;
    if (node.children.length === 0) return node._text;
    return node._text + node.children.map(collectText).join("");
  }

  function matchesSelector(node, sel) {
    if (sel.startsWith(".")) return node.classList.contains(sel.slice(1));
    if (sel.startsWith("#")) return node.id === sel.slice(1);
    const attrMatch = sel.match(/^\[([^\]=]+)(?:="([^"]*)")?\]$/);
    if (attrMatch) {
      const [, key, val] = attrMatch;
      return val === undefined ? node.hasAttribute(key) : node.getAttribute(key) === val;
    }
    return node.tagName.toLowerCase() === sel.toLowerCase();
  }

  function findAll(node, sel, out = []) {
    for (const child of node.children) {
      if (typeof child === "string") continue;
      if (matchesSelector(child, sel)) out.push(child);
      findAll(child, sel, out);
    }
    return out;
  }

  const el = {
    tagName: String(tagName).toUpperCase(),
    ownerDocument,
    children,
    childNodes: children,
    parentNode: null,
    parentElement: null,
    dataset,
    type: "",
    _text: "",
    get id() {
      return attrs.get("id") ?? "";
    },
    set id(v) {
      attrs.set("id", String(v));
    },
    get className() {
      return [...classes].join(" ");
    },
    set className(v) {
      classes.clear();
      for (const part of String(v).split(/\s+/).filter(Boolean)) {
        classes.add(part);
      }
    },
    classList: {
      add(...tokens) {
        for (const t of tokens) classes.add(t);
      },
      remove(...tokens) {
        for (const t of tokens) classes.delete(t);
      },
      toggle(token, force) {
        if (force === true) {
          classes.add(token);
          return true;
        }
        if (force === false) {
          classes.delete(token);
          return false;
        }
        if (classes.has(token)) {
          classes.delete(token);
          return false;
        }
        classes.add(token);
        return true;
      },
      contains(token) {
        return classes.has(token);
      },
    },
    get textContent() {
      return collectText(el);
    },
    set textContent(v) {
      children.length = 0;
      el._text = v == null ? "" : String(v);
    },
    get innerHTML() {
      return text;
    },
    set innerHTML(v) {
      text = String(v);
      if (text === "") {
        children.length = 0;
        el._text = "";
      }
    },
    setAttribute(name, value) {
      attrs.set(String(name), String(value));
    },
    getAttribute(name) {
      return attrs.get(String(name)) ?? null;
    },
    hasAttribute(name) {
      return attrs.has(String(name));
    },
    removeAttribute(name) {
      attrs.delete(String(name));
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
          el._text += n;
        } else {
          el.appendChild(n);
        }
      }
    },
    replaceChildren(...nodes) {
      children.length = 0;
      el._text = "";
      el.append(...nodes);
    },
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    removeEventListener(type, fn) {
      if (listeners.has(type)) {
        listeners.set(type, listeners.get(type).filter((cb) => cb !== fn));
      }
    },
    dispatchEvent(event) {
      const evt = {
        preventDefault() {},
        stopPropagation() {},
        ...event,
        target: event?.target ?? el,
        currentTarget: el,
      };
      for (const fn of [...(listeners.get(evt.type) ?? [])]) {
        fn(evt);
      }
      return true;
    },
    click() {
      el.dispatchEvent({ type: "click" });
    },
    querySelectorAll(sel) {
      return findAll(el, sel);
    },
    querySelector(sel) {
      return findAll(el, sel)[0] ?? null;
    },
  };

  return el;
}

function createFakeDocument() {
  const doc = {
    createElement(tag) {
      return createFakeElement(tag, doc);
    },
    createTextNode(str) {
      return String(str);
    },
    getElementById() {
      return null;
    },
  };
  return doc;
}

function findChipButton(container, id, labelText) {
  const buttons = container.querySelectorAll("button");
  return (
    buttons.find(
      (btn) =>
        btn.dataset.layer === id ||
        btn.dataset.chip === id ||
        btn.dataset.id === id ||
        btn.textContent.includes(labelText),
    ) ?? null
  );
}

function parseColorRgb(color) {
  if (typeof color !== "string") return null;
  const c = color.trim().toLowerCase();
  if (c === "orange") return [255, 165, 0];
  if (c === "blue") return [0, 0, 255];
  const hex6 = c.match(/^#([0-9a-f]{6})$/);
  if (hex6) {
    const n = parseInt(hex6[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const hex3 = c.match(/^#([0-9a-f]{3})$/);
  if (hex3) {
    return hex3[1].split("").map((ch) => parseInt(ch + ch, 16));
  }
  const rgb = c.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
  if (rgb) {
    return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  }
  return null;
}

function isOrangeColor(color) {
  const rgb = parseColorRgb(color);
  if (!rgb) return false;
  const [r, g, b] = rgb;
  return r >= 180 && r > g && g > b;
}

function isBlueColor(color) {
  const rgb = parseColorRgb(color);
  if (!rgb) return false;
  const [r, g, b] = rgb;
  return b >= 150 && b > r && b >= g;
}

function stripJsComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\r\n]*/g, "");
}

function collectJsFiles(dir) {
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...collectJsFiles(full));
    } else if (entry.isFile() && entry.name.endsWith(".js")) {
      results.push(full);
    }
  }
  return results;
}

// Verify layerbar.CHIPS exposes the six layer chips with ids and Greek labels in SPEC order.
test("test_six_chips_in_spec_order", () => {
  const chips = layerbar.CHIPS;
  assert.ok(Array.isArray(chips), "layerbar.CHIPS must be an array");
  assert.equal(chips.length, 7, "layerbar.CHIPS must contain exactly 7 chips");

  assert.deepEqual(
    chips.map((c) => c?.label),
    EXPECTED_CHIP_LABELS,
    "chip labels must match SPEC order",
  );

  const ids = chips.map((c) => c?.id);
  for (const id of ids) {
    assert.ok(typeof id === "string" && id.length > 0, "every chip must have a non-empty string id");
  }
  assert.equal(new Set(ids).size, 7, "all seven chip ids must be unique");
  assert.equal(ids[0], "env");
  assert.equal(ids[1], "access");
  assert.equal(ids[2], "works");
  assert.equal(ids[5], "health");
  assert.ok(!ids.includes("reports"), "reports is always on and must not have a chip");
});

// Verify toggling the works chip sets visibility to "visible" on every layer id in works.layerIds.
test("test_toggle_sets_visibility_on_all_layer_ids", async () => {
  const prevDoc = globalThis.document;
  const fakeDoc = createFakeDocument();
  globalThis.document = fakeDoc;

  try {
    const fakeMap = createFakeMap();
    const fakeApi = createFakeApi();
    const state = { visible: { works: false } };
    const container = fakeDoc.createElement("nav");

    await worksLayer.register(fakeMap, fakeApi);
    assert.ok(
      Array.isArray(worksLayer.layerIds) && worksLayer.layerIds.length >= 2,
      "works.layerIds must include both the line and glow layer ids",
    );
    assert.ok(worksLayer.layerIds.includes("works-line"), "works.layerIds must include works-line");
    assert.ok(worksLayer.layerIds.includes("works-glow"), "works.layerIds must include works-glow");

    layerbar.initLayerBar(container, state, { map: fakeMap, api: fakeApi });
    const worksChip = findChipButton(container, "works", "Έργα");
    assert.ok(worksChip, "layerbar must render a button for the works chip");

    worksChip.click();
    for (const layerId of worksLayer.layerIds) {
      assert.equal(
        fakeMap.getLayoutProperty(layerId, "visibility"),
        "visible",
        `toggling works on must set ${layerId} visibility to visible`,
      );
    }

    worksChip.click();
    for (const layerId of worksLayer.layerIds) {
      assert.equal(
        fakeMap.getLayoutProperty(layerId, "visibility"),
        "none",
        `toggling works off must set ${layerId} visibility to none`,
      );
    }
  } finally {
    if (prevDoc === undefined) {
      delete globalThis.document;
    } else {
      globalThis.document = prevDoc;
    }
  }
});

// Verify clicking a DOM chip twice toggles state.visible.works true then false and updates aria-pressed.
test("test_toggle_updates_state_and_aria", () => {
  const prevDoc = globalThis.document;
  const fakeDoc = createFakeDocument();
  globalThis.document = fakeDoc;

  try {
    const fakeMap = createFakeMap();
    const fakeApi = createFakeApi();
    const state = { visible: { works: false } };
    const container = fakeDoc.createElement("nav");

    layerbar.initLayerBar(container, state, { map: fakeMap, api: fakeApi });
    const worksChip = findChipButton(container, "works", "Έργα");
    assert.ok(worksChip, "layerbar must render a button for the works chip");
    assert.equal(worksChip.getAttribute("aria-pressed"), "false");

    worksChip.click();
    assert.equal(state.visible.works, true);
    assert.equal(worksChip.getAttribute("aria-pressed"), "true");

    worksChip.click();
    assert.equal(state.visible.works, false);
    assert.equal(worksChip.getAttribute("aria-pressed"), "false");
  } finally {
    if (prevDoc === undefined) {
      delete globalThis.document;
    } else {
      globalThis.document = prevDoc;
    }
  }
});

// Verify the works-line layer styles line-color with a match expression: orange for in_progress, blue for planned.
test("test_works_colour_by_status", async () => {
  const fakeMap = createFakeMap();
  const fakeApi = createFakeApi();

  await worksLayer.register(fakeMap, fakeApi);
  const lineLayer = fakeMap.getLayer("works-line");
  assert.ok(lineLayer, "works.register must add the works-line layer");
  assert.equal(lineLayer.type, "line");

  const lineColor = lineLayer.paint?.["line-color"];
  assert.ok(
    Array.isArray(lineColor) && lineColor[0] === "match",
    "works-line paint['line-color'] must be a MapLibre match expression",
  );
  assert.ok(
    JSON.stringify(lineColor[1]).includes("status"),
    "works-line match expression must read the status property",
  );

  const inProgressIdx = lineColor.findIndex((item, idx) => idx >= 2 && idx % 2 === 0 && item === "in_progress");
  const plannedIdx = lineColor.findIndex((item, idx) => idx >= 2 && idx % 2 === 0 && item === "planned");
  assert.ok(inProgressIdx >= 2, "match expression must handle 'in_progress'");
  assert.ok(plannedIdx >= 2, "match expression must handle 'planned'");

  const inProgressColor = lineColor[inProgressIdx + 1];
  const plannedColor = lineColor[plannedIdx + 1];
  assert.ok(
    isOrangeColor(inProgressColor),
    `expected orange color for in_progress, got ${inProgressColor}`,
  );
  assert.ok(
    isBlueColor(plannedColor),
    `expected blue color for planned, got ${plannedColor}`,
  );
  assert.notEqual(inProgressColor, plannedColor);
});

// Verify works adds a second line layer (works-glow) with paint['line-blur'] > 0.
test("test_works_glow_layer_has_line_blur", async () => {
  const fakeMap = createFakeMap();
  const fakeApi = createFakeApi();

  await worksLayer.register(fakeMap, fakeApi);
  const lineLayer = fakeMap.getLayer("works-line");
  const glowLayer = fakeMap.getLayer("works-glow");

  assert.ok(lineLayer && lineLayer.type === "line", "works-line must be a line layer");
  assert.ok(glowLayer && glowLayer.type === "line", "works-glow must be a second line layer");
  assert.notEqual(glowLayer.id, lineLayer.id);

  const lineBlur = glowLayer.paint?.["line-blur"];
  assert.ok(
    typeof lineBlur === "number" && lineBlur > 0,
    `works-glow paint['line-blur'] must be > 0, got ${lineBlur}`,
  );
});

// Verify env heatmap layer switches heatmap-weight between temp_c (temp mode) and aqi (aqi mode).
test("test_env_heatmap_weight_uses_temp_or_aqi", async () => {
  const fakeMap = createFakeMap();
  const fakeApi = createFakeApi();

  await envLayer.register(fakeMap, fakeApi, { mode: "temp" });
  const heatmapId = envLayer.layerIds.find((id) => fakeMap.getLayer(id)?.type === "heatmap");
  assert.ok(heatmapId, "env.register must add a heatmap layer listed in env.layerIds");

  const tempWeight = fakeMap.getPaintProperty(heatmapId, "heatmap-weight");
  assert.ok(
    JSON.stringify(tempWeight).includes("temp_c"),
    "in temp mode, heatmap-weight must read temp_c",
  );
  assert.ok(
    !JSON.stringify(tempWeight).includes("aqi"),
    "in temp mode, heatmap-weight must not read aqi",
  );

  assert.equal(typeof envLayer.setMode, "function", "env layer must export setMode(map, mode)");
  envLayer.setMode(fakeMap, "aqi");
  const aqiWeight = fakeMap.getPaintProperty(heatmapId, "heatmap-weight");
  assert.ok(
    JSON.stringify(aqiWeight).includes("aqi"),
    "in aqi mode, heatmap-weight must read aqi",
  );
  assert.ok(
    !JSON.stringify(aqiWeight).includes("temp_c"),
    "in aqi mode, heatmap-weight must not read temp_c",
  );

  envLayer.setMode(fakeMap, "temp");
  const restoredTempWeight = fakeMap.getPaintProperty(heatmapId, "heatmap-weight");
  assert.ok(
    JSON.stringify(restoredTempWeight).includes("temp_c"),
    "switching back to temp mode must restore temp_c heatmap-weight",
  );
});

// Verify transit bus polling calls api.transit 0 times while off and every 20 s only while on.
test("test_bus_polling_only_when_on", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const prevDoc = globalThis.document;
  const fakeDoc = createFakeDocument();
  globalThis.document = fakeDoc;

  try {
    let transitCalls = 0;
    const fakeMap = createFakeMap();
    const fakeApi = createFakeApi({
      async transit() {
        transitCalls += 1;
        return {
          lines: createFeatureCollection(),
          stations: createFeatureCollection(),
          buses: createFeatureCollection(),
        };
      },
    });
    const state = { visible: {} };
    const container = fakeDoc.createElement("nav");

    await transitLayer.register(fakeMap, fakeApi, state);
    layerbar.initLayerBar(container, state, { map: fakeMap, api: fakeApi });

    // While bus telematics is off, advancing 60 s must make 0 api.transit calls.
    t.mock.timers.tick(60_000);
    await Promise.resolve();
    assert.equal(transitCalls, 0, "api.transit must not be called while transit is off");

    const busChip = findChipButton(container, "transit-buses", "Τηλεματική ΟΑΣΑ");
    assert.ok(busChip, "layerbar must render a button for Τηλεματική ΟΑΣΑ");

    busChip.click();
    await Promise.resolve();
    const callsAfterEnable = transitCalls;
    assert.ok(callsAfterEnable <= 1, "enabling buses may perform at most one immediate fetch");

    t.mock.timers.tick(19_999);
    await Promise.resolve();
    assert.equal(transitCalls, callsAfterEnable, "must not poll before 20 s");

    t.mock.timers.tick(1);
    await Promise.resolve();
    assert.equal(transitCalls, callsAfterEnable + 1, "must poll at 20 s");

    t.mock.timers.tick(20_000);
    await Promise.resolve();
    assert.equal(transitCalls, callsAfterEnable + 2, "must poll at 40 s");

    t.mock.timers.tick(20_000);
    await Promise.resolve();
    assert.equal(transitCalls, callsAfterEnable + 3, "must poll at 60 s");

    // Toggling off must stop the 20 s polling interval.
    busChip.click();
    t.mock.timers.tick(60_000);
    await Promise.resolve();
    assert.equal(
      transitCalls,
      callsAfterEnable + 3,
      "api.transit must stop polling once buses are toggled off",
    );
  } finally {
    t.mock.timers.reset();
    if (prevDoc === undefined) {
      delete globalThis.document;
    } else {
      globalThis.document = prevDoc;
    }
  }
});

// Verify no Dev A source file outside api.js calls fetch(.
test("test_layers_get_data_only_through_api", () => {
  const devBRelativeFiles = new Set([
    "api.js",
    path.join("ui", "points.js"),
    path.join("ui", "report.js"),
    path.join("ui", "stoa.js"),
    path.join("ui", "workstab.js"),
  ]);

  const jsFiles = collectJsFiles(JS_DIR);
  const devAFiles = jsFiles.filter((filePath) => {
    const rel = path.relative(JS_DIR, filePath);
    return !devBRelativeFiles.has(rel);
  });

  assert.ok(devAFiles.length > 0, "must inspect Dev A JS files");

  for (const filePath of devAFiles) {
    const raw = fs.readFileSync(filePath, "utf8");
    const codeOnly = stripJsComments(raw);
    assert.ok(
      !/\bfetch\s*\(/.test(codeOnly),
      `${path.relative(WEB_DIR, filePath)} must not call fetch( directly; use api.js`,
    );
  }
});
