// B17 tests: official service after a report, Athens dates in points history, mock filters, offline flush event.
// Offline: fake DOM, fake api, fake fetch. No server, no browser.
import test from "node:test";
import assert from "node:assert/strict";

import * as reportMod from "../js/ui/report.js";
import { mount as mountPoints } from "../js/ui/points.js";
import * as api from "../js/api.js";

const settle = async () => { for (let i = 0; i < 8; i++) await new Promise((r) => setTimeout(r, 0)); };

// ---------- minimal fake DOM (tags, attributes, text, listeners, a few selectors) ----------
function fakeEl(tag) {
  const attrs = new Map();
  const listeners = new Map();
  const classes = new Set();
  let text = "";
  const el = {
    tagName: String(tag).toUpperCase(), children: [], parentNode: null, style: {}, dataset: {},
    hidden: false, disabled: false, value: "", checked: false, files: [], id: "",
    classList: {
      add: (...n) => n.forEach((x) => classes.add(x)), remove: (...n) => n.forEach((x) => classes.delete(x)),
      contains: (n) => classes.has(n),
    },
    get className() { return [...classes].join(" "); },
    set className(v) { classes.clear(); String(v).split(/\s+/).filter(Boolean).forEach((x) => classes.add(x)); },
    get textContent() { return text + this.children.map((c) => c.textContent).join(""); },
    set textContent(v) { text = v == null ? "" : String(v); this.children = []; },
    setAttribute(k, v) {
      attrs.set(k, String(v));
      if (k === "class") this.className = v;
      if (k === "id") this.id = String(v);
      if (k === "hidden") this.hidden = true;
      if (k === "value") this.value = String(v);
    },
    getAttribute: (k) => (attrs.has(k) ? attrs.get(k) : null),
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    append(...cs) { cs.forEach((c) => this.appendChild(typeof c === "string" ? Object.assign(fakeEl("#text"), { textContent: c }) : c)); },
    replaceChildren(...cs) { this.children = []; text = ""; this.append(...cs); },
    remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((c) => c !== this); },
    addEventListener(t, fn) { if (!listeners.has(t)) listeners.set(t, []); listeners.get(t).push(fn); },
    async trigger(t, evt = {}) { for (const fn of [...(listeners.get(t) || [])]) await fn.call(this, { type: t, preventDefault() {}, ...evt }); },
    focus() {},
    querySelectorAll(sel) {
      const out = [];
      const match = (n) => {
        if (sel === "input:checked") return n.tagName === "INPUT" && n.checked;
        if (sel.startsWith(".")) return n.classList.contains(sel.slice(1));
        return n.tagName === sel.toUpperCase();
      };
      const walk = (n) => { for (const c of n.children) { if (match(c)) out.push(c); walk(c); } };
      walk(this);
      return out;
    },
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
  };
  return el;
}

function withDom(fn) {
  return async () => {
    const prev = { document: globalThis.document, window: globalThis.window };
    const store = new Map();
    const localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) };
    class Marker {
      setLngLat(p) { this.p = p; return this; }
      addTo() { return this; }
      getLngLat() { return { lng: 23.73, lat: 37.98 }; }
      remove() {}
    }
    globalThis.document = { createElement: fakeEl };
    globalThis.window = { localStorage, maplibregl: { Marker }, addEventListener() {} };
    try { await fn(); } finally { globalThis.document = prev.document; globalThis.window = prev.window; }
  };
}

// Mounts report.js, opens the form for a category (and optional ramp-like subtype), submits, returns the panel.
async function submitFlow({ category, subtype = null, fakeApi }) {
  const root = fakeEl("div");
  const bus = new EventTarget();
  const map = { getCenter: () => ({ lng: 23.73, lat: 37.98 }) };
  reportMod.mount({ map, api: fakeApi, root, bus });
  const menu = root.querySelector(".report-menu");
  await menu.querySelector(`button`).trigger("click"); // opens some form; re-open the wanted one below
  const item = menu.querySelectorAll("button").find((b) => b.getAttribute("data-category") === category);
  await item.trigger("click");
  const panel = root.querySelector("form");
  if (subtype) {
    const radio = panel.querySelectorAll("input").find((i) => i.getAttribute("value") === subtype);
    radio.checked = true;
  }
  await panel.trigger("submit");
  await settle();
  return panel;
}

const SERVICE = (over = {}) => ({
  category: "sidewalk", label_el: "Πεζοδρόμιο", source: "sandbox",
  service: { id: "s1", title: "Επισκευή πεζοδρομίου", documents: ["Φωτογραφία του σημείου", "Διεύθυνση"],
    cost_eur: 0, online_url: "https://www.cityofathens.gr/service/1", where: null, when: null, faq: [] },
  ...over,
});
const okSend = async () => ({ id: "R-1", tracking_id: "R-1", points_awarded: 0 });

// Mapping from report category + subtype to the sandbox category (same as app/categories.py SUBTYPE_TO_SANDBOX).
test("sandboxCategoryFor maps subtypes", () => {
  const f = reportMod.sandboxCategoryFor;
  assert.equal(f("damage", "ramp"), "sidewalk");
  assert.equal(f("obstacle", "pothole"), "pothole");
  assert.equal(f("damage", "other"), "other");
  assert.equal(f("congestion"), null);
  assert.equal(f("work_progress"), null);
});

// After a successful send the form shows the service block: title, documents, free cost, safe official link.
test("report shows official service after submit", withDom(async () => {
  const calls = [];
  const fakeApi = { sendReport: okSend, serviceFor: async (c) => { calls.push(c); return SERVICE(); } };
  const panel = await submitFlow({ category: "damage", subtype: "ramp", fakeApi });
  assert.deepEqual(calls, ["sidewalk"]);
  const t = panel.textContent;
  for (const s of ["Τι μπορείτε να κάνετε ακόμα", "Επισκευή πεζοδρομίου", "Φωτογραφία του σημείου", "Διεύθυνση", "Δωρεάν", "Επίσημη σελίδα"]) {
    assert.ok(t.includes(s), `missing: ${s}`);
  }
  const a = panel.querySelector("a");
  assert.ok(a, "expected a link");
  const rel = a.getAttribute("rel") ?? a.rel;
  assert.ok(String(rel).includes("noopener"));
  assert.equal(a.getAttribute("href") ?? a.href, "https://www.cityofathens.gr/service/1");
}));

// cost_eur null is unknown, never 0 or free (CLAUDE.md: unknown values show «άγνωστο»).
test("report shows unknown cost as άγνωστο", withDom(async () => {
  const s = SERVICE();
  s.service.cost_eur = null;
  const panel = await submitFlow({ category: "damage", subtype: "ramp", fakeApi: { sendReport: okSend, serviceFor: async () => s } });
  assert.ok(panel.textContent.includes("άγνωστο"));
  assert.ok(!panel.textContent.includes("Δωρεάν"));
}));

// Congestion has no sandbox category: no registry lookup at all.
test("report skips service for congestion", withDom(async () => {
  let called = 0;
  await submitFlow({ category: "congestion", fakeApi: { sendReport: okSend, serviceFor: async () => { called++; return SERVICE(); } } });
  assert.equal(called, 0);
}));

// service null, then a rejected call: no block, no error text, and the normal submit success still happens.
test("report hides block when service null or call fails", withDom(async () => {
  for (const serviceFor of [async () => ({ category: "sidewalk", service: null, source: "sandbox" }), async () => { throw new Error("boom"); }]) {
    const root = fakeEl("div");
    const bus = new EventTarget();
    const created = [];
    bus.addEventListener("report:created", (e) => created.push(e.detail));
    reportMod.mount({ map: { getCenter: () => ({ lng: 23.7, lat: 37.9 }) }, api: { sendReport: okSend, serviceFor }, root, bus });
    const menu = root.querySelector(".report-menu");
    await menu.querySelectorAll("button").find((b) => b.getAttribute("data-category") === "damage").trigger("click");
    const panel = root.querySelector("form");
    panel.querySelectorAll("input").find((i) => i.getAttribute("value") === "ramp").checked = true;
    await panel.trigger("submit");
    await settle();
    assert.ok(!panel.textContent.includes("Τι μπορείτε να κάνετε ακόμα"));
    assert.ok(!panel.textContent.includes("δεν έγινε δεκτή"), "no rejection text");
    assert.equal(panel.querySelector("a"), null);
    assert.equal(created.length, 1, "submit success still dispatched");
  }
}));

// A mock registry answer is labelled (CLAUDE.md «Mock data is labelled»).
test("report labels mock service", withDom(async () => {
  const panel = await submitFlow({ category: "damage", subtype: "ramp",
    fakeApi: { sendReport: okSend, serviceFor: async () => SERVICE({ upstream_source: "mock", source: "live" }) } });
  assert.ok(panel.textContent.includes("δοκιμαστικό"));
}));

// 2026-11-21T22:30:00Z is 00:30 on 22 Nov in Athens (UTC+2): the date shown must be the Athens one.
test("points history shows Athens date", withDom(async () => {
  const root = fakeEl("div");
  const fakeApi = { points: async () => ({ balance: 5, district: null, history: [{ delta: 5, reason: "Αναφορά", ts: "2026-11-21T22:30:00Z" }], rewards: [], source: "live" }) };
  await mountPoints({ map: null, api: fakeApi, root, bus: new EventTarget() });
  await root.querySelector(".points-pill").trigger("click");
  const li = root.querySelector(".points-history").children[0].textContent;
  assert.ok(li.includes("22/11/2026"), li);
  assert.ok(!li.includes("2026-11-21"), li);
}));

// ---------- api.js mock fallbacks ----------
function fakeStorage() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) };
}
// /api/ always fails (offline); mock files come from `files`.
function offlineSetup(files) {
  api.configure({
    storage: fakeStorage(), base: "", mockBase: "mock/", timeoutMs: 1000,
    fetch: async (url) => {
      if (String(url).includes("/api/")) throw new TypeError("network down");
      const name = String(url).split("?")[0].split("/").pop();
      return { ok: true, status: 200, json: async () => files[name] };
    },
  });
}
const line = (id, status) => ({ type: "Feature", geometry: { type: "LineString", coordinates: [[23.7, 37.9], [23.71, 37.91]] }, properties: { id, status } });
const pt = (id, lon, lat) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { id } });

// Offline works({status}) must filter the snapshot by status.
test("works mock filtered by status", async () => {
  offlineSetup({ "works.geojson": { type: "FeatureCollection", features: [line("a", "planned"), line("b", "completed")] } });
  const out = await api.works({ status: "completed" });
  assert.equal(out.source, "mock");
  assert.deepEqual(out.features.map((f) => f.properties.id), ["b"]);
});

// Offline reads with a bbox drop Point features outside it.
test("mock GeoJSON filtered by bbox", async () => {
  offlineSetup({ "reports.geojson": { type: "FeatureCollection", features: [pt("in", 23.725, 37.975), pt("out", 23.9, 38.1)] } });
  const out = await api.reports({ bbox: [23.72, 37.97, 23.73, 37.98] });
  assert.deepEqual(out.features.map((f) => f.properties.id), ["in"]);
});

// flushQueue(api, storage, bus): every report it sends fires one report:created (3rd argument is the bus; owner question).
test("flushQueue dispatches report:created", async () => {
  const storage = fakeStorage();
  storage.setItem(reportMod.QUEUE_KEY, JSON.stringify([{ category: "incident", lngLat: { lng: 23.73, lat: 37.98 }, note: "", work_id: null }]));
  const bus = new EventTarget();
  const seen = [];
  bus.addEventListener("report:created", (e) => seen.push(e.detail));
  await reportMod.flushQueue({ sendReport: async () => ({ id: "R-9", points_awarded: 0 }) }, storage, bus);
  assert.equal(seen.length, 1);
  assert.equal(seen[0].id, "R-9");
});
