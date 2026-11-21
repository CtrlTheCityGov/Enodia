// A6 Integration polish & Dev B HUD styles tests (TASKS_A.md "### A6", SPEC.md HUD, F3, F4, A-14).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bootstrap } from "../js/main.js";
import * as accessLayer from "../js/layers/access.js";
import * as reportsLayer from "../js/layers/reports.js";
import * as transitLayer from "../js/layers/transit.js";
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
    byId.get("hud-offline").classList.add("glass", "glass-pill", "hidden");
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

  const fakeMap = {
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
    remove() {},
  };

  return fakeMap;
}

function parseCssRules(cssText, out = []) {
  const clean = cssText.replace(/\/\*[\s\S]*?\*\//g, "");
  let i = 0;
  while (i < clean.length) {
    while (i < clean.length && /\s/.test(clean[i])) i += 1;
    if (i >= clean.length) break;

    let headerEnd = i;
    while (headerEnd < clean.length && clean[headerEnd] !== "{" && clean[headerEnd] !== ";") {
      headerEnd += 1;
    }
    if (headerEnd >= clean.length) break;

    const header = clean.slice(i, headerEnd).trim();
    if (clean[headerEnd] === ";") {
      i = headerEnd + 1;
      continue;
    }

    let depth = 1;
    let bodyEnd = headerEnd + 1;
    while (bodyEnd < clean.length && depth > 0) {
      if (clean[bodyEnd] === "{") depth += 1;
      else if (clean[bodyEnd] === "}") depth -= 1;
      bodyEnd += 1;
    }

    const body = clean.slice(headerEnd + 1, bodyEnd - 1);
    if (/^@(media|supports)\b/i.test(header)) {
      parseCssRules(body, out);
    } else if (!header.startsWith("@")) {
      out.push({ selector: header, body });
    }
    i = bodyEnd;
  }
  return out;
}

// Verify hud.css defines Dev B panel layouts, [hidden] guard, and 600ms points animations.
test("test_hud_css_styles_all_dev_b_panels_and_animations", () => {
  const css = fs.readFileSync(path.join(WEB_DIR, "css", "hud.css"), "utf8");
  const rules = parseCssRules(css);

  function bodyFor(selectorRegex) {
    return rules
      .filter((r) => selectorRegex.test(r.selector))
      .map((r) => r.body)
      .join("\n");
  }

  const hiddenBody = bodyFor(/\[hidden\]/);
  assert.match(
    hiddenBody,
    /display\s*:\s*none\s*!important/i,
    "hud.css must define [hidden] { display: none !important; }",
  );

  const pulseBody = bodyFor(/\.points-pill\.pulse(?![a-zA-Z0-9_-])/);
  assert.ok(pulseBody.length > 0, "hud.css must define a rule for .points-pill.pulse");
  assert.match(pulseBody, /\b(?:600ms|0\.6s)\b/i, ".points-pill.pulse must animate over 600ms");

  const floatBody = bodyFor(/\.points-float(?![a-zA-Z0-9_-])/);
  assert.ok(floatBody.length > 0, "hud.css must define a rule for .points-float");
  assert.match(floatBody, /\b(?:600ms|0\.6s)\b/i, ".points-float must animate over 600ms");

  for (const [label, regex] of [
    [".report-fab", /\.report-fab(?![a-zA-Z0-9_-])/],
    [".report-menu", /\.report-menu(?![a-zA-Z0-9_-])/],
    [".report-panel", /\.report-panel(?![a-zA-Z0-9_-])/],
    [".stoa-bubble", /\.stoa-bubble(?![a-zA-Z0-9_-])/],
  ]) {
    assert.ok(bodyFor(regex).length > 0, `hud.css must define styles for ${label}`);
  }

  const stoaPanelBody = bodyFor(/\.stoa-panel(?![a-zA-Z0-9_-])/);
  assert.ok(stoaPanelBody.length > 0, "hud.css must define styles for .stoa-panel");
  assert.match(stoaPanelBody, /position\s*:\s*absolute\b/i, ".stoa-panel must use position: absolute");

  const worksTabPanelBody = bodyFor(/\.workstab-panel(?![a-zA-Z0-9_-])/);
  assert.ok(worksTabPanelBody.length > 0, "hud.css must define styles for .workstab-panel");
  assert.match(
    worksTabPanelBody,
    /position\s*:\s*absolute\b/i,
    ".workstab-panel must use position: absolute",
  );
});

// Verify reports layer matches "congestion" in circle-color and exports refresh() to update reports-source.
test("test_reports_layer_matches_congestion_and_refreshes", async () => {
  const fakeMap = createFakeMap();
  let currentReports = {
    type: "FeatureCollection",
    source: "live",
    features: [
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [23.734, 37.975] },
        properties: { id: "r1", category: "obstacle" },
      },
    ],
  };

  const fakeApi = {
    async reports() {
      return currentReports;
    },
  };

  await reportsLayer.register(fakeMap, fakeApi, { visible: {} });

  const pinsLayer = fakeMap.getLayer("reports-pins");
  assert.ok(pinsLayer, "reports.register must add reports-pins layer");
  const circleColor = pinsLayer.paint?.["circle-color"];
  assert.ok(Array.isArray(circleColor) && circleColor[0] === "match", "circle-color must be a match expression");
  assert.ok(
    JSON.stringify(circleColor).includes('"congestion"'),
    'reports circle-color match expression must include "congestion"',
  );

  assert.equal(typeof reportsLayer.refresh, "function", "layers/reports.js must export refresh(map, api, state)");

  currentReports = {
    type: "FeatureCollection",
    source: "live",
    features: [
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [23.738, 37.979] },
        properties: { id: "r2", category: "congestion" },
      },
    ],
  };

  await reportsLayer.refresh(fakeMap, fakeApi, { visible: {} });
  const src = fakeMap.getSource("reports-source");
  assert.ok(src, "reports-source must exist");
  assert.equal(src.data?.features?.length, 1);
  assert.equal(src.data.features[0]?.properties?.id, "r2");
  assert.equal(src.data.features[0]?.properties?.category, "congestion");
});

// Verify static pre-downloaded access mock data does not trigger state.onOffline().
test("test_access_mock_source_does_not_trigger_offline_badge", async () => {
  const fakeMap = createFakeMap();
  let offlineCalls = 0;

  const apiReturningMock = {
    async access() {
      return {
        type: "FeatureCollection",
        source: "mock",
        features: [
          {
            type: "Feature",
            geometry: { type: "Point", coordinates: [23.7348, 37.9755] },
            properties: { wheelchair: "yes" },
          },
        ],
      };
    },
  };

  const state = {
    visible: { access: true },
    onOffline() {
      offlineCalls += 1;
    },
  };

  await accessLayer.register(fakeMap, apiReturningMock, state);

  assert.equal(
    offlineCalls,
    0,
    "static pre-downloaded access data with source='mock' must not call state.onOffline",
  );
  const src = fakeMap.getSource("access-source");
  assert.equal(src?.data?.features?.length, 1, "access-source must still be populated");
});

// Verify bootstrap() syncs #hud-offline visibility with api.status "source" events and api.isOffline().
test("test_main_syncs_offline_badge_with_api_status", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const fakeDoc = createFakeDocument(true);
  const fakeMap = createFakeMap();
  const statusTarget = new EventTarget();
  let apiOffline = false;

  const fakeApi = {
    status: statusTarget,
    isOffline() {
      return apiOffline;
    },
    async offlineBase() {
      return { type: "FeatureCollection", features: [] };
    },
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
            "./ui/points.js": null,
            "./ui/report.js": null,
            "./ui/stoa.js": null,
            "./ui/workstab.js": null,
          },
        });

        // Keep map itself online so only api.isOffline() drives #hud-offline here.
        fakeMap._emit("style.load");
        assert.equal(result.state.offline, false);

        const badge = fakeDoc.getElementById("hud-offline");
        assert.equal(badge.classList.contains("hidden"), true, "#hud-offline starts hidden while online");

        apiOffline = true;
        statusTarget.dispatchEvent(new CustomEvent("source", { detail: { source: "mock" } }));
        assert.equal(
          badge.classList.contains("hidden"),
          false,
          "#hud-offline must unhide when api.isOffline() becomes true",
        );

        apiOffline = false;
        statusTarget.dispatchEvent(new CustomEvent("source", { detail: { source: "live" } }));
        assert.equal(
          badge.classList.contains("hidden"),
          true,
          "#hud-offline must re-hide when api.isOffline() returns false while map is online",
        );
      } finally {
        t.mock.timers.reset();
      }
    },
  );
});

// Verify popupHtml suppresses the Diavgeia link for SEED works and shows SEED badge text.
test("test_workpopup_suppresses_diavgeia_link_for_seed_work", () => {
  const html = workpopup.popupHtml(
    {
      id: "work-seed-1",
      title: "Ανάπλαση Πανεπιστημίου",
      status: "in_progress",
      contractor: "Δοκιμαστικός Ανάδοχος Α.Ε.",
      amount_contract_eur: 250000,
      amount_paid_eur: 100000,
      ada: "SEED-ΑΔΑ-001",
      seed: true,
    },
    "2026-07-02",
  );

  assert.equal(typeof html, "string");
  assert.ok(
    !/diavgeia\.gov\.gr/i.test(html),
    "SEED work popup must not contain an external diavgeia.gov.gr link",
  );
  assert.ok(html.includes("SEED-ΑΔΑ-001"), "SEED work popup must still render the plain ΑΔΑ text");
  assert.ok(html.includes("SEED"), "SEED work popup must display a SEED badge");
});

// Verify clicking «Ανέφερε πρόοδο» dispatches report:open with both work_id and clicked lngLat.
test("test_workpopup_report_open_includes_click_lnglat", () => {
  const fakeDoc = createFakeDocument();
  const fakeMap = createFakeMap();
  const bus = new EventTarget();
  const events = [];
  bus.addEventListener("report:open", (e) => events.push(e));

  let reportBtn = null;

  class FakePopup {
    setLngLat() {
      return this;
    }
    setHTML(html) {
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

  const clickLngLat = { lng: 23.73, lat: 37.97 };
  fakeMap._emitLayer("click", "works-line", {
    lngLat: clickLngLat,
    features: [
      {
        properties: {
          id: "work-77",
          title: "Εργασίες Ακαδημίας",
          status: "in_progress",
          contractor: "ΤΕΡΝΑ Α.Ε.",
        },
      },
    ],
  });

  assert.ok(reportBtn, "report button must be rendered when bus is provided");
  reportBtn.click();

  assert.equal(events.length, 1, "clicking report button must dispatch report:open");
  assert.equal(events[0].detail?.work_id, "work-77");
  assert.deepEqual(
    events[0].detail?.lngLat,
    clickLngLat,
    "report:open detail must include clicked lngLat",
  );
});

// Verify transit ignores a slow stale bus poll resolving after a newer poll and styles PROASTIAKOS rail lines.
test("test_transit_ignores_stale_bus_poll_and_matches_proastiakos", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const fakeMap = createFakeMap();
  const pendingResolvers = [];

  const fakeApi = {
    async transit() {
      return new Promise((resolve) => {
        pendingResolvers.push(resolve);
      });
    },
  };

  try {
    const state = { visible: { [transitLayer.BUSES_ID]: true, [transitLayer.RAIL_ID]: false } };
    await transitLayer.register(fakeMap, fakeApi, state);

    const railLinesLayer = fakeMap.getLayer("transit-rail-lines");
    assert.ok(railLinesLayer, "transit.register must add transit-rail-lines");
    const lineColor = railLinesLayer.paint?.["line-color"];
    assert.ok(
      Array.isArray(lineColor) && lineColor[0] === "match",
      "transit-rail-lines line-color must be a match expression",
    );
    assert.ok(
      JSON.stringify(lineColor[1]).includes('"id"'),
      'transit lineColorExpression must check feature property "id"',
    );
    assert.ok(
      JSON.stringify(lineColor).includes('"PROASTIAKOS"'),
      'transit lineColorExpression must match "PROASTIAKOS"',
    );

    assert.equal(pendingResolvers.length, 1, "initial bus poll #1 must be in flight");

    // Trigger poll #2 while poll #1 is still pending.
    t.mock.timers.tick(transitLayer.BUS_POLL_INTERVAL_MS);
    assert.equal(pendingResolvers.length, 2, "overlapping bus poll #2 must start at 20 s");

    const fastPoll2 = {
      lines: { type: "FeatureCollection", features: [] },
      stations: { type: "FeatureCollection", features: [] },
      buses: {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            geometry: { type: "Point", coordinates: [23.75, 37.99] },
            properties: { id: "bus-1", line: "040" },
          },
        ],
      },
    };
    const slowPoll1 = {
      lines: { type: "FeatureCollection", features: [] },
      stations: { type: "FeatureCollection", features: [] },
      buses: {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            geometry: { type: "Point", coordinates: [23.71, 37.95] },
            properties: { id: "bus-1", line: "040" },
          },
        ],
      },
    };

    // Fast poll #2 resolves first, then slow stale poll #1 resolves afterwards.
    pendingResolvers[1](fastPoll2);
    await Promise.resolve();
    await Promise.resolve();

    pendingResolvers[0](slowPoll1);
    await Promise.resolve();
    await Promise.resolve();

    const busesSrc = fakeMap.getSource("transit-buses-source");
    assert.equal(busesSrc?.data?.features?.length, 1);
    assert.deepEqual(
      busesSrc.data.features[0].geometry.coordinates,
      [23.75, 37.99],
      "stale poll #1 must not overwrite newer poll #2 bus coordinates",
    );
  } finally {
    transitLayer.stopBusPolling(fakeMap);
    t.mock.timers.reset();
  }
});
