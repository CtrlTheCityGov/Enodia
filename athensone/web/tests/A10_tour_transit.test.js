// A10 (Wave 3): first-visit tour, transit layer helpers + menu, health popup. node:test, offline, fake DOM/map.
import test from "node:test";
import assert from "node:assert/strict";

import {
  TOUR_STORAGE_KEY,
  TOUR_STEPS,
  shouldShowTour,
  computeTourPlacement,
  initTour,
} from "../js/ui/tour.js";
import * as transit from "../js/layers/transit.js";
import { initTransitMenu } from "../js/ui/transitmenu.js";
import { renderHealthPopupHtml } from "../js/layers/health.js";

// ------------------------------------------------------------------ tiny fake DOM
function makeDoc({ width = 1280, height = 800 } = {}) {
  const docListeners = [];
  const queryMap = new Map();
  const doc = {
    activeElement: null,
    defaultView: { innerWidth: width, innerHeight: height, addEventListener() {}, removeEventListener() {} },
    createElement: (tag) => makeEl(tag, doc),
    addEventListener(type, fn, capture) { docListeners.push({ type, fn, capture: Boolean(capture) }); },
    removeEventListener(type, fn, capture) {
      const i = docListeners.findIndex((l) => l.type === type && l.fn === fn && l.capture === Boolean(capture));
      if (i >= 0) docListeners.splice(i, 1);
    },
    // Capture listeners first, like the browser.
    dispatch(type, event) {
      for (const l of [...docListeners].sort((a, b) => Number(b.capture) - Number(a.capture))) {
        if (l.type === type) l.fn(event);
      }
    },
    listenerCount: () => docListeners.length,
    querySelector: (sel) => queryMap.get(sel) ?? null,
    register(sel, el) { queryMap.set(sel, el); },
  };
  doc.body = makeEl("body", doc);
  doc.documentElement = makeEl("html", doc);
  return doc;
}

function makeEl(tag, doc) {
  const listeners = new Map();
  const attrs = new Map();
  const classes = new Set();
  let text = "";
  const el = {
    tagName: String(tag).toUpperCase(),
    ownerDocument: doc,
    children: [],
    parentNode: null,
    style: {},
    dataset: {},
    hidden: false,
    disabled: false,
    checked: false,
    type: "",
    id: "",
    innerHTML: "",
    offsetWidth: 320,
    offsetHeight: 200,
    _rect: null,
    get className() { return [...classes].join(" "); },
    set className(v) { classes.clear(); String(v).split(/\s+/).filter(Boolean).forEach((c) => classes.add(c)); },
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
      toggle(c, force) {
        const on = force === undefined ? !classes.has(c) : Boolean(force);
        if (on) classes.add(c); else classes.delete(c);
        return on;
      },
    },
    get textContent() { return text + el.children.map((c) => c.textContent).join(""); },
    set textContent(v) { text = v == null ? "" : String(v); el.children = []; },
    setAttribute(k, v) { attrs.set(k, String(v)); if (k === "id") el.id = String(v); },
    getAttribute: (k) => (attrs.has(k) ? attrs.get(k) : null),
    removeAttribute: (k) => attrs.delete(k),
    appendChild(c) { c.parentNode = el; el.children.push(c); return c; },
    append(...cs) { for (const c of cs) el.appendChild(c); },
    replaceChildren(...cs) { el.children = []; text = ""; for (const c of cs) el.appendChild(c); },
    remove() {
      if (el.parentNode) {
        el.parentNode.children = el.parentNode.children.filter((c) => c !== el);
        el.parentNode = null;
      }
    },
    contains(node) {
      for (let n = node; n; n = n.parentNode) if (n === el) return true;
      return false;
    },
    closest(sel) {
      const cls = sel.startsWith(".") ? sel.slice(1) : null;
      for (let n = el; n; n = n.parentNode) if (cls && n.classList?.contains(cls)) return n;
      return null;
    },
    focus() { doc.activeElement = el; },
    getBoundingClientRect: () => el._rect ?? { top: 0, left: 0, width: 0, height: 0 },
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    removeEventListener(type, fn) {
      const l = listeners.get(type);
      if (l) listeners.set(type, l.filter((f) => f !== fn));
    },
    fire(type, event = {}) { for (const fn of listeners.get(type) || []) fn({ target: el, ...event }); },
    click() { el.fire("click"); },
  };
  return el;
}

function walk(root, pred, out = []) {
  for (const c of root.children || []) {
    if (pred(c)) out.push(c);
    walk(c, pred, out);
  }
  return out;
}
const byClass = (root, cls) => walk(root, (n) => n.classList?.contains(cls));

function fakeStorage(init = {}) {
  const data = new Map(Object.entries(init));
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
  };
}

// ------------------------------------------------------------------ tour: pure helpers
test("tour: six frozen steps, each with a real HUD target", () => {
  assert.equal(TOUR_STEPS.length, 6);
  assert.ok(Object.isFrozen(TOUR_STEPS) && Object.isFrozen(TOUR_STEPS[0]));
  assert.equal(TOUR_STEPS[3].target, "#hud-report .report-fab, #hud-report");
  assert.equal(TOUR_STEPS[5].target, "#hud-stoa .stoa-bubble, #hud-stoa");
});

test("tour: shouldShowTour is true only on a fresh visit without ?notour=1", () => {
  assert.equal(shouldShowTour(fakeStorage(), ""), true);
  assert.equal(shouldShowTour(null, ""), true);
  assert.equal(shouldShowTour(fakeStorage({ [TOUR_STORAGE_KEY]: "1" }), ""), false);
  assert.equal(shouldShowTour(fakeStorage(), "?notour=1"), false);
  assert.equal(shouldShowTour(fakeStorage(), "?a=2&notour=1"), false);
  const throwing = { getItem() { throw new Error("blocked"); } };
  assert.equal(shouldShowTour(throwing, ""), true);
});

const VP = { width: 1000, height: 800 };
const CARD = { width: 300, height: 200 };

test("tour placement: below a top target, arrow on the card's top edge", () => {
  const p = computeTourPlacement({ top: 20, left: 100, width: 200, height: 40 }, CARD, VP);
  assert.equal(p.placement, "bottom");
  assert.equal(p.arrowSide, "top");
  assert.equal(p.top, 78); // 60 + 18 px gap
  assert.equal(p.left, 50); // centred on the target (200 - 150)
  assert.equal(p.arrowOffset, 150); // points at the target centre
});

test("tour placement: above a bottom target", () => {
  const p = computeTourPlacement({ top: 700, left: 400, width: 100, height: 40 }, CARD, VP);
  assert.equal(p.placement, "top");
  assert.equal(p.arrowSide, "bottom");
  assert.equal(p.top, 482); // 700 - 18 - 200
});

test("tour placement: right of a full-height left target, left of a full-height right target", () => {
  const r = computeTourPlacement({ top: 0, left: 12, width: 100, height: 800 }, CARD, VP);
  assert.equal(r.placement, "right");
  assert.equal(r.arrowSide, "left");
  assert.equal(r.left, 130);
  assert.equal(r.top, 300);
  assert.equal(r.arrowOffset, 100);
  const l = computeTourPlacement({ top: 0, left: 880, width: 100, height: 800 }, CARD, VP);
  assert.equal(l.placement, "left");
  assert.equal(l.arrowSide, "right");
  assert.equal(l.left, 562);
});

test("tour placement: centred with no arrow when there is no usable target", () => {
  for (const rect of [null, { top: 0, left: 0, width: 0, height: 0 }, { top: -500, left: -500, width: 10, height: 10 }]) {
    const p = computeTourPlacement(rect, CARD, VP);
    assert.equal(p.placement, "center");
    assert.equal(p.arrowSide, null);
    assert.equal(p.top, 300);
    assert.equal(p.left, 350);
  }
});

test("tour placement: a card wider than a 390 px phone stays inside the 12 px margin", () => {
  const p = computeTourPlacement({ top: 10, left: 300, width: 80, height: 30 }, { width: 2000, height: 220 }, { width: 390, height: 844 });
  assert.ok(p.left >= 12, `left ${p.left}`);
  assert.ok(p.top >= 12 && p.top + 220 <= 844 - 12);
  assert.ok(p.arrowOffset >= 22);
});

// ------------------------------------------------------------------ tour: behaviour
function tourEnv() {
  const doc = makeDoc();
  const tabs = makeEl("div", doc);
  tabs._rect = { top: 12, left: 12, width: 300, height: 44 };
  doc.register("#hud-tabs", tabs);
  const fab = makeEl("button", doc);
  fab.className = "glass report-fab";
  fab._rect = { top: 730, left: 12, width: 56, height: 56 };
  doc.register("#hud-report .report-fab", fab);
  const storage = fakeStorage();
  const bus = new EventTarget();
  const tour = initTour({ root: doc, bus, storage, autoStart: false });
  return { doc, fab, storage, bus, tour };
}

test("tour: start mounts the layer on body, next/prev walk the six steps, last step closes and marks seen", () => {
  const { doc, storage, tour } = tourEnv();
  assert.equal(tour.isOpen(), false);
  assert.equal(doc.body.children.length, 0, "nothing is mounted before start()");
  assert.equal(tour.start(0), true);
  assert.equal(tour.isOpen(), true);
  const layer = byClass(doc.body, "enodia-tour-layer")[0];
  assert.ok(layer, ".enodia-tour-layer mounted on body");
  const step = () => byClass(layer, "enodia-tour-card__step")[0].textContent;
  const title = () => byClass(layer, "enodia-tour-card__title")[0].textContent;
  assert.equal(step(), "Βήμα 1 / 6");
  assert.equal(title(), TOUR_STEPS[0].title);
  const spot = byClass(layer, "enodia-tour-spotlight")[0];
  assert.equal(spot.style.top, "6px"); // 12 - 6 px padding
  assert.equal(spot.style.width, "312px");

  tour.next();
  assert.equal(step(), "Βήμα 2 / 6");
  tour.prev();
  assert.equal(step(), "Βήμα 1 / 6");
  tour.prev(); // no-op at the first step
  assert.equal(step(), "Βήμα 1 / 6");

  tour.start(5);
  const primary = byClass(layer, "enodia-tour-btn--primary")[0];
  assert.equal(primary.textContent, "Ξεκινήστε!");
  assert.equal(storage.getItem(TOUR_STORAGE_KEY), null);
  tour.next();
  assert.equal(tour.isOpen(), false);
  assert.equal(storage.getItem(TOUR_STORAGE_KEY), "1");
  assert.equal(doc.body.children.length, 0, "layer removed on close");
  assert.equal(doc.listenerCount(), 0, "document listeners detached on close");
});

test("tour: report step spotlights the '+' FAB, not its slot", () => {
  const { doc, tour } = tourEnv();
  tour.start(3);
  const spot = byClass(doc.body, "enodia-tour-spotlight")[0];
  assert.equal(spot.style.top, "724px"); // FAB top 730 - 6
  assert.equal(spot.style.width, "68px");
  tour.close(false);
});

test("tour: ArrowRight advances, Escape closes and marks seen", () => {
  const { doc, storage, tour } = tourEnv();
  tour.start(0);
  doc.dispatch("keydown", { key: "ArrowRight", preventDefault() {} }); // focus is on the card's primary button
  assert.equal(byClass(doc.body, "enodia-tour-card__step")[0].textContent, "Βήμα 2 / 6");
  doc.dispatch("keydown", { key: "Escape" });
  assert.equal(tour.isOpen(), false);
  assert.equal(storage.getItem(TOUR_STORAGE_KEY), "1");
});

test("tour: clicking the '+' FAB closes the tour without swallowing the click", () => {
  const { doc, fab, storage, tour } = tourEnv();
  tour.start(1);
  let prevented = false;
  doc.dispatch("click", { target: fab, preventDefault() { prevented = true; }, stopPropagation() { prevented = true; } });
  assert.equal(tour.isOpen(), false);
  assert.equal(storage.getItem(TOUR_STORAGE_KEY), "1");
  assert.equal(prevented, false, "the user's click must still reach the report flow");
});

test("tour: a missing target falls back to a centred card", () => {
  const { doc, tour } = tourEnv();
  tour.start(4); // #hud-routing is not registered in this fake DOM
  const card = byClass(doc.body, "enodia-tour-card")[0];
  assert.equal(card.dataset.placement, "center");
  assert.ok(byClass(doc.body, "enodia-tour-spotlight")[0].classList.contains("is-hidden"));
  tour.destroy();
});

// ------------------------------------------------------------------ transit helpers
test("transit: Greek and Latin Metro refs and A1–A4 share the line palette", () => {
  const C = transit.ATHENS_LINE_COLORS;
  assert.equal(transit.lineColorForRef("Μ1"), C.M1); // U+039C
  assert.equal(transit.lineColorForRef("M1"), C.M1);
  assert.equal(transit.lineColorForRef("Μ2"), C.M2);
  assert.equal(transit.lineColorForRef("Μ3"), C.M3);
  for (const ref of ["A1", "A2", "A3", "A4", "Α1", "Α4", "Προαστιακός"]) {
    assert.equal(transit.lineColorForRef(ref), C.Suburban, ref);
  }
  assert.equal(transit.lineColorForRef("Χ95"), C.default);
  assert.equal(transit.canonicalLine("Μ1"), "M1");
  assert.equal(transit.canonicalLine("Α2"), "A2");
});

test("transit: station normalisation fills primary_line, lines, line_keys and colour", () => {
  const s = transit.normalizeStation({ type: "Feature", properties: { name: "Λαρίσης", lines: ["A1", "Μ2"] } });
  assert.equal(s.properties.primary_line, "A1");
  assert.deepEqual(s.properties.lines, ["A1", "Μ2"]);
  assert.equal(s.properties.line_keys, "|A1|M2|");
  assert.equal(s.properties.color, transit.ATHENS_LINE_COLORS.Suburban);
  // MapLibre hands array properties back as JSON strings on click.
  const j = transit.normalizeStation({ properties: { lines: '["Μ3"]' } });
  assert.deepEqual(j.properties.lines, ["Μ3"]);
  assert.equal(j.properties.color, transit.ATHENS_LINE_COLORS.M3);
});

test("transit: getBusFeatureId prefers vehicle_id over id and feature.id", () => {
  assert.equal(transit.getBusFeatureId({ id: 9, properties: { vehicle_id: "30214", id: "BUS-3922-0" } }), "30214");
  assert.equal(transit.getBusFeatureId({ id: 9, properties: { id: "bus-1" } }), "bus-1");
  assert.equal(transit.getBusFeatureId({ id: 9, properties: {} }), "9");
  assert.equal(transit.getBusFeatureId({ properties: {} }), null);
});

test("transit: bus popup shows the Greek route name, heading and a CACHED pill for a backend snapshot", () => {
  const html = transit.renderBusPopupHtml(
    { line: "040", route_name: "ΠΕΙΡΑΙΑΣ - ΣΥΝΤΑΓΜΑ", vehicle_id: "30214", bearing: 90, updated_at: "2026-11-21T18:38:04Z" },
    "snapshot",
  );
  assert.ok(html.includes("ΠΕΙΡΑΙΑΣ - ΣΥΝΤΑΓΜΑ"));
  assert.ok(html.includes("CACHED"));
  assert.ok(html.includes("Α (90°)"));
  assert.ok(html.includes("30214"));
  const unknown = transit.renderBusPopupHtml({ line: "2", mode: "trolley", route_name: "<img src=x onerror=1>" }, "live");
  assert.ok(unknown.includes("Τρόλεϊ") && unknown.includes("LIVE") && unknown.includes("άγνωστη"));
  assert.ok(!unknown.includes("<img"), "route_name is escaped");
});

function fakeMap() {
  const sources = new Map();
  const layers = new Map();
  const filters = new Map();
  const handlers = [];
  return {
    filters,
    handlers,
    getSource: (id) => sources.get(id),
    addSource(id, src) { const s = { ...src, setData(d) { s.data = d; } }; sources.set(id, s); },
    getLayer: (id) => layers.get(id),
    addLayer(l) { layers.set(l.id, { ...l }); if (l.filter) filters.set(l.id, l.filter); },
    setLayoutProperty(id, k, v) { const l = layers.get(id); if (l) l.layout = { ...l.layout, [k]: v }; },
    setFilter(id, f) { filters.set(id, f); },
    on(ev, layerId, fn) { handlers.push([ev, layerId, fn]); },
    getCanvas: () => ({ style: {} }),
    flyTo() {},
    fitBounds(b) { this.lastFit = b; },
  };
}

test("transit: setTransitFilter applies MapLibre filters to every transit layer and clears them", async () => {
  const map = fakeMap();
  await transit.register(map, null, { visible: {} });
  transit.setTransitFilter(map, { railLines: ["Μ1"], busLines: ["3922"] });
  for (const id of transit.layerIds) assert.ok(map.filters.get(id), `filter on ${id}`);
  assert.ok(JSON.stringify(map.filters.get("transit-rail-lines")).includes('"M1"'));
  assert.ok(JSON.stringify(map.filters.get("transit-rail-stations")).includes("|M1|"));
  assert.ok(JSON.stringify(map.filters.get("transit-buses")).includes('"3922"'));
  assert.deepEqual(transit.getTransitFilter(map).railLines, ["Μ1"]);
  transit.setTransitFilter(map, {});
  for (const id of transit.layerIds) assert.equal(map.filters.get(id), null);
  // Label layers are clickable like their markers (Wave 1 review).
  const clickLayers = map.handlers.filter(([ev]) => ev === "click").map(([, l]) => l);
  for (const id of ["transit-rail-stations", "transit-rail-labels", "transit-buses", "transit-buses-labels"]) {
    assert.ok(clickLayers.includes(id), `click bound on ${id}`);
  }
});

const LINE = (ref, mode, coords) => ({
  type: "Feature",
  geometry: { type: "LineString", coordinates: coords },
  properties: { ref, name: `${mode === "subway" ? "Μετρό" : "Προαστιακός"} ${ref}`, mode },
});

function transitApi() {
  let calls = 0;
  return {
    get calls() { return calls; },
    async transit(arg) {
      calls += 1;
      assert.equal(arg, undefined, "the whole network is requested, no viewport bbox");
      return {
        source: "live",
        backend_source: "snapshot",
        lines: { type: "FeatureCollection", features: [
          LINE("Μ1", "subway", [[23.70, 37.95], [23.80, 38.05]]),
          LINE("A1", "train", [[23.72, 37.99], [23.94, 37.93]]),
        ] },
        stations: { type: "FeatureCollection", features: [
          { type: "Feature", geometry: { type: "Point", coordinates: [23.73, 37.99] }, properties: { name: "Βικτώρια", lines: ["Μ1"] } },
          { type: "Feature", geometry: { type: "Point", coordinates: [23.72, 37.99] }, properties: { name: "Λαρίσης", lines: ["A1", "Μ2"] } },
        ] },
        buses: { type: "FeatureCollection", features: [] },
      };
    },
  };
}

test("transit menu: Metro / Προαστιακός / ΟΑΣΑ tabs render the catalog and a toggle filters the map", async () => {
  const map = fakeMap();
  const api = transitApi();
  const bus = new EventTarget();
  const state = { visible: { [transit.RAIL_ID]: true }, bus };
  await transit.register(map, api, state);
  assert.equal(api.calls, 1);
  const snap = transit.getLastTransitSnapshot(map);
  assert.equal(snap.source, "snapshot", "backend provenance wins over api.js 'live'");
  assert.equal(snap.routes.metro[0].ref, "Μ1");
  assert.equal(snap.routes.suburban[0].ref, "A1");

  const doc = makeDoc();
  const container = makeEl("div", doc);
  const menu = initTransitMenu(container, state, { map, api, bus });
  assert.ok(menu);
  assert.equal(container.hidden, false, "visible while a transit layer is on");
  const tabs = walk(container, (n) => n.getAttribute?.("role") === "tab");
  assert.deepEqual(tabs.map((t) => t.textContent), ["🚌 ΟΑΣΑ", "🚇 Μετρό", "🚆 Προαστιακός"]);

  menu.open();
  const pill = byClass(container, "transit-menu__pill")[0];
  assert.equal(pill.getAttribute("aria-expanded"), "true");
  assert.ok(byClass(container, "prov-pill--cached").length === 1, "CACHED provenance in the header");

  menu.selectTab("metro");
  const body = byClass(container, "transit-menu__body")[0];
  assert.ok(body.textContent.includes("Μετρό Μ1"));
  assert.ok(body.textContent.includes("1 σταθμοί"));
  menu.selectTab("suburban");
  assert.ok(body.textContent.includes("Προαστιακός A1"));

  menu.selectTab("metro");
  const toggle = walk(body, (n) => n.dataset?.focusKey === "rail-toggle-M1")[0];
  assert.ok(toggle, "per-line visibility switch");
  toggle.checked = false;
  toggle.fire("change");
  const railFilter = JSON.stringify(map.filters.get("transit-rail-lines"));
  assert.ok(railFilter.includes('"A1"') && !railFilter.includes('"M1"'), railFilter);
  assert.deepEqual(transit.getTransitFilter(map).railLines, ["A1"]);

  // Both layers off -> the whole menu hides.
  state.visible[transit.RAIL_ID] = false;
  bus.dispatchEvent(new CustomEvent("layer:toggle", { detail: { id: transit.RAIL_ID, visible: false } }));
  assert.equal(container.hidden, true);
  menu.destroy();
});

test("transit: triggerTransitRefresh makes no api.transit call while both layers are off", async () => {
  const map = fakeMap();
  const api = transitApi();
  await transit.register(map, api, { visible: {} });
  await transit.triggerTransitRefresh(map, api, { visible: {} });
  assert.equal(api.calls, 0);
});

// ------------------------------------------------------------------ health popup
test("health popup: pharmacy badge, tel link and provenance; XSS escaped", () => {
  const html = renderHealthPopupHtml(
    { kind: "φαρμακείο", name: "<img src=x onerror=alert(1)>", address: "Ερμού 1", phone: "+30 210 123 4567", hours: "08:00–23:00" },
    "live",
  );
  assert.ok(html.includes("💊 Εφημερεύον Φαρμακείο"));
  assert.ok(html.includes('href="tel:+302101234567"'));
  assert.ok(html.includes("LIVE"));
  assert.ok(html.includes("08:00–23:00"));
  assert.ok(!html.includes("<img"), "name is escaped");
});

test("health popup: hospital badge, specialties from a JSON string, unknown phone, DEMO for mock", () => {
  const html = renderHealthPopupHtml(
    { kind: "hospital", name: "Γ.Ν.Α. Ευαγγελισμός", specialties: '["Παθολογική","Χειρουργική"]' },
    "mock",
  );
  assert.ok(html.includes("🏥 Εφημερεύον Νοσοκομείο"));
  assert.ok(html.includes("Παθολογική") && html.includes("Χειρουργική"));
  assert.ok(html.includes("DEMO"));
  assert.ok(html.includes("άγνωστο") && !html.includes("tel:"));
  const evil = renderHealthPopupHtml({ kind: "pharmacy", phone: '"><script>alert(1)</script>' }, "");
  assert.ok(!evil.includes("<script") && !evil.includes("tel:"));
});
