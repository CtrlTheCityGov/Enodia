// B11: Phase 4 integration & end-to-end demo rehearsal tests for api.js + Dev B HUD widgets.
// Runs in Node with fake DOM/window/localStorage/MapLibre objects and no network calls.
import test from "node:test";
import assert from "node:assert/strict";

import * as api from "../js/api.js";
import { mount as mountPoints } from "../js/ui/points.js";
import { mount as mountReport } from "../js/ui/report.js";
import { mount as mountStoa } from "../js/ui/stoa.js";
import { mount as mountWorkstab } from "../js/ui/workstab.js";

function makeFakeStorage() {
  const store = new Map();
  return {
    getItem(k) {
      return store.has(k) ? store.get(k) : null;
    },
    setItem(k, v) {
      store.set(k, String(v));
    },
    removeItem(k) {
      store.delete(k);
    },
  };
}

function unescapeAttr(s) {
  return String(s)
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

function createFakeElement(tagName, ownerDocument) {
  const classes = new Set();
  const attrs = new Map();
  const listeners = new Map();
  let _className = "";
  let _textContent = "";
  let _innerHTML = "";

  const el = {
    tagName: String(tagName || "div").toUpperCase(),
    ownerDocument,
    children: [],
    parentNode: null,
    style: {},
    dataset: {},
    id: "",
    type: "",
    name: "",
    value: "",
    files: [],
    href: "",
    target: "",
    rel: "",
    src: "",
    placeholder: "",
    maxLength: 500,
    scrollTop: 0,
    scrollHeight: 0,
    disabled: false,
    hidden: false,
    get className() {
      return _className;
    },
    set className(val) {
      _className = String(val || "");
      classes.clear();
      for (const part of _className.split(/\s+/).filter(Boolean)) classes.add(part);
    },
    classList: {
      add(...names) {
        for (const n of names) if (n) classes.add(n);
        _className = [...classes].join(" ");
      },
      remove(...names) {
        for (const n of names) classes.delete(n);
        _className = [...classes].join(" ");
      },
      contains(name) {
        return classes.has(name);
      },
      toggle(name, force) {
        const shouldAdd = force === undefined ? !classes.has(name) : Boolean(force);
        if (shouldAdd) classes.add(name);
        else classes.delete(name);
        _className = [...classes].join(" ");
        return shouldAdd;
      },
    },
    get textContent() {
      if (this.children.length === 0) return _textContent;
      return _textContent + this.children.map((c) => c.textContent).join("");
    },
    set textContent(val) {
      _textContent = val == null ? "" : String(val);
      this.children = [];
    },
    get innerHTML() {
      return _innerHTML;
    },
    set innerHTML(val) {
      // Minimal <a> parser so stoa.js citation links become clickable DOM nodes in Node tests.
      _innerHTML = val == null ? "" : String(val);
      this.children = [];
      _textContent = "";
      const anchorRe = /<a\b([^>]*)>([\s\S]*?)<\/a>/gi;
      let last = 0;
      for (const m of _innerHTML.matchAll(anchorRe)) {
        if (m.index > last) _textContent += _innerHTML.slice(last, m.index);
        const a = ownerDocument.createElement("a");
        for (const am of m[1].matchAll(/([a-zA-Z0-9_-]+)="([^"]*)"/g)) {
          const attrName = am[1];
          const attrVal = unescapeAttr(am[2]);
          a.setAttribute(attrName, attrVal);
          if (attrName.startsWith("data-")) {
            a.dataset[attrName.slice(5)] = attrVal;
          }
        }
        a.textContent = unescapeAttr(m[2]);
        this.appendChild(a);
        last = m.index + m[0].length;
      }
      if (last < _innerHTML.length) _textContent += _innerHTML.slice(last);
    },
    setAttribute(k, v) {
      const s = String(v);
      attrs.set(k, s);
      if (k === "id") this.id = s;
      if (k === "class") this.className = s;
      if (k === "hidden") this.hidden = true;
    },
    getAttribute(k) {
      if (k === "id") return this.id || null;
      if (k === "class") return this.className || null;
      return attrs.has(k) ? attrs.get(k) : null;
    },
    hasAttribute(k) {
      if (k === "hidden") return Boolean(this.hidden) || attrs.has(k);
      return attrs.has(k);
    },
    removeAttribute(k) {
      attrs.delete(k);
      if (k === "hidden") this.hidden = false;
    },
    appendChild(child) {
      if (typeof child === "string") {
        _textContent += child;
        return child;
      }
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    append(...nodes) {
      for (const n of nodes) this.appendChild(n);
    },
    replaceChildren(...nodes) {
      this.children = [];
      _textContent = "";
      for (const n of nodes) this.appendChild(n);
    },
    removeChild(child) {
      const idx = this.children.indexOf(child);
      if (idx >= 0) {
        this.children.splice(idx, 1);
        child.parentNode = null;
      }
      return child;
    },
    remove() {
      if (this.parentNode) this.parentNode.removeChild(this);
    },
    focus() {},
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    removeEventListener(type, fn) {
      const list = listeners.get(type);
      if (!list) return;
      const idx = list.indexOf(fn);
      if (idx >= 0) list.splice(idx, 1);
    },
    dispatchEvent(evt) {
      const eventObj = evt && typeof evt === "object" ? evt : { type: String(evt) };
      if (!eventObj.target) eventObj.target = this;
      if (!eventObj.preventDefault) eventObj.preventDefault = () => {};
      let cur = this;
      while (cur) {
        eventObj.currentTarget = cur;
        const list = cur._listeners?.get(eventObj.type) || [];
        for (const fn of [...list]) fn.call(cur, eventObj);
        cur = cur.parentNode;
      }
      return true;
    },
    click() {
      return this.dispatchEvent({ type: "click", target: this, preventDefault() {} });
    },
    closest(selector) {
      let cur = this;
      while (cur) {
        if (matchesSelector(cur, selector)) return cur;
        cur = cur.parentNode;
      }
      return null;
    },
    querySelectorAll(selector) {
      const matches = [];
      const parts = selector.split(",").map((s) => s.trim()).filter(Boolean);
      const walk = (node) => {
        for (const child of node.children) {
          if (parts.some((sel) => matchesSelector(child, sel))) matches.push(child);
          walk(child);
        }
      };
      walk(this);
      return matches;
    },
    querySelector(selector) {
      return this.querySelectorAll(selector)[0] || null;
    },
    _listeners: listeners,
  };
  return el;
}

function matchesSelector(el, sel) {
  const m = sel.match(/^([a-zA-Z0-9_-]+)?((?:\.[a-zA-Z0-9_-]+|\[[^\]]+\])*)$/);
  if (m && (m[1] || m[2])) {
    const [, tag, rest] = m;
    if (tag && el.tagName.toLowerCase() !== tag.toLowerCase()) return false;
    if (rest) {
      for (const token of rest.matchAll(/\.([a-zA-Z0-9_-]+)|\[([^=\]]+)(?:="([^"]*)")?\]/g)) {
        if (token[1] && !el.classList.contains(token[1])) return false;
        if (token[2]) {
          const propVal = el.hasAttribute(token[2]) ? el.getAttribute(token[2]) : el[token[2]];
          if (token[3] === undefined && (propVal === undefined || propVal === null || propVal === "")) return false;
          if (token[3] !== undefined && String(propVal) !== token[3]) return false;
        }
      }
    }
    return true;
  }
  if (sel.startsWith(".")) return el.classList.contains(sel.slice(1));
  if (sel.startsWith("#")) return el.id === sel.slice(1);
  return el.tagName.toLowerCase() === sel.toLowerCase();
}

function createFakeEnv() {
  const root = createFakeElement("div", null);
  const doc = {
    createElement(tag) {
      return createFakeElement(tag, doc);
    },
    getElementById(id) {
      return root.querySelector(`#${id}`);
    },
  };
  root.ownerDocument = doc;

  for (const id of ["hud-tabs", "hud-points", "hud-report", "hud-stoa"]) {
    const slot = doc.createElement("div");
    slot.setAttribute("id", id);
    root.appendChild(slot);
  }

  class FakeMarker {
    setLngLat(lngLat) {
      this._lngLat = lngLat;
      return this;
    }
    getLngLat() {
      return this._lngLat;
    }
    addTo() {
      return this;
    }
    remove() {}
  }

  const storage = makeFakeStorage();
  const win = {
    localStorage: storage,
    maplibregl: { Marker: FakeMarker },
    addEventListener() {},
    removeEventListener() {},
  };

  const map = {
    getCenter: () => ({ lng: 23.7348, lat: 37.9755 }),
  };

  return { doc, root, win, storage, map };
}

function withFakeGlobals(env, fn) {
  const prevDoc = globalThis.document;
  const prevWin = globalThis.window;
  globalThis.document = env.doc;
  globalThis.window = env.win;
  return Promise.resolve()
    .then(fn)
    .finally(() => {
      if (prevDoc === undefined) delete globalThis.document;
      else globalThis.document = prevDoc;
      if (prevWin === undefined) delete globalThis.window;
      else globalThis.window = prevWin;
    });
}

const SAMPLE_WORK = {
  type: "Feature",
  geometry: {
    type: "LineString",
    coordinates: [
      [23.741, 37.9656],
      [23.743, 37.9664],
    ],
  },
  properties: {
    id: "W-SEED-001",
    title: "Ανακατασκευή πεζοδρομίων (δείγμα)",
    status: "in_progress",
    contractor: "Ανάδοχος Α (SEED)",
    amount_contract_eur: 60000,
    amount_paid_eur: 48200,
    ada: "SEED-ΑΔΑ-001",
    reports_count: 1,
    seed: true,
  },
};

// Checks that tab:change {tab: "works"} opens the workstab panel and loads works, and {tab: "map"} hides it.
test("test_js_workstab_opens_on_bus_tab_change", async () => {
  const env = createFakeEnv();
  await withFakeGlobals(env, async () => {
    const bus = new EventTarget();
    const container = env.root.querySelector("#hud-tabs");
    let worksCalls = 0;
    const fakeApi = {
      async works() {
        worksCalls += 1;
        return { type: "FeatureCollection", features: [SAMPLE_WORK], source: "live" };
      },
    };

    await mountWorkstab({ map: env.map, api: fakeApi, root: env.root, container, bus });
    const panel = container.querySelector("#workstab-panel");
    assert.ok(panel, "expected #workstab-panel");
    assert.equal(panel.hidden, true);
    assert.equal(worksCalls, 0);

    bus.dispatchEvent(new CustomEvent("tab:change", { detail: { tab: "works" } }));
    await new Promise((r) => setTimeout(r, 0));

    assert.equal(panel.hidden, false);
    assert.equal(worksCalls, 1);
    assert.match(panel.textContent, /Ανακατασκευή πεζοδρομίων/);

    bus.dispatchEvent(new CustomEvent("tab:change", { detail: { tab: "map" } }));
    assert.equal(panel.hidden, true);
  });
});

// Checks that submitting a +15 report via report.js emits points:earned and report:created on bus, pulsing points pill.
test("test_js_report_to_points_pulse_via_bus", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const env = createFakeEnv();
  await withFakeGlobals(env, async () => {
    const bus = new EventTarget();
    const createdEvents = [];
    bus.addEventListener("report:created", (e) => createdEvents.push(e.detail));

    api.configure({
      storage: env.storage,
      fetch: async (url) => {
        if (url === "/api/map/points") {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              balance: 10,
              district: { name: "1η Δημοτική Κοινότητα", progress_pct: 20, goal: 5000 },
              history: [],
              rewards: [],
            }),
          };
        }
        if (url === "/api/map/reports") {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              id: "MR-DEMO-15",
              photo_url_blurred: "/photos/blurred.jpg",
              points_awarded: 15,
              blur: { faces: 0, plates: 0 },
            }),
          };
        }
        throw new Error(`Unexpected fetch ${url}`);
      },
    });

    const pointsSlot = env.root.querySelector("#hud-points");
    const reportSlot = env.root.querySelector("#hud-report");
    await mountPoints({ map: env.map, api, root: pointsSlot, container: pointsSlot, bus });
    mountReport({ map: env.map, api, root: reportSlot, container: reportSlot, bus });

    const pill = pointsSlot.querySelector(".points-pill");
    const balanceEl = pointsSlot.querySelector(".points-balance");
    assert.equal(balanceEl.textContent, "10");

    // Open «+» menu, choose work_progress, and submit the form.
    reportSlot.querySelector(".report-fab").click();
    reportSlot.querySelector('[data-category="work_progress"]').click();
    const form = reportSlot.querySelector(".report-panel");
    form.querySelector("textarea").value = "Πρόοδος εργασιών";
    form.dispatchEvent({ type: "submit", preventDefault() {} });

    // Drain microtasks for fetch + submitReport without blocking on mocked setTimeout.
    for (let i = 0; i < 10; i += 1) await Promise.resolve();

    assert.equal(balanceEl.textContent, "25");
    assert.ok(pill.classList.contains("pulse"), "points pill should have .pulse class");
    assert.match(pill.textContent, /\+15/);
    assert.equal(createdEvents.length, 1);
    assert.deepEqual(createdEvents[0], {
      id: "MR-DEMO-15",
      category: "work_progress",
      lon: 23.7348,
      lat: 37.9755,
    });

    t.mock.timers.tick(600);
    assert.equal(pill.classList.contains("pulse"), false);
  });
});

// Checks that clicking «Ανέφερε πρόοδο» on W-SEED-001 in workstab opens report panel with work_progress and W-SEED-001.
test("test_js_workstab_report_open_prefills_report_panel", async () => {
  const env = createFakeEnv();
  await withFakeGlobals(env, async () => {
    const bus = new EventTarget();
    const sentForms = [];
    const fakeApi = {
      async works() {
        return { type: "FeatureCollection", features: [SAMPLE_WORK], source: "live" };
      },
      async sendReport(form) {
        sentForms.push(form);
        return {
          id: "MR-W1",
          photo_url_blurred: null,
          points_awarded: 5,
          blur: { faces: 0, plates: 0 },
        };
      },
    };

    const tabsSlot = env.root.querySelector("#hud-tabs");
    const reportSlot = env.root.querySelector("#hud-report");
    const wt = await mountWorkstab({ map: env.map, api: fakeApi, root: tabsSlot, container: tabsSlot, bus });
    mountReport({ map: env.map, api: fakeApi, root: reportSlot, container: reportSlot, bus });

    await wt.open();
    const reportBtn = tabsSlot.querySelector(".workstab-report");
    assert.ok(reportBtn, "expected «Ανέφερε πρόοδο» button on W-SEED-001");
    reportBtn.click();

    const reportPanel = reportSlot.querySelector(".report-panel");
    const reportTitle = reportSlot.querySelector(".report-title");
    assert.equal(reportPanel.hidden, false);
    assert.match(reportTitle.textContent, /W-SEED-001/);
    assert.match(reportTitle.textContent, /Πρόοδος έργου/);

    reportPanel.dispatchEvent({ type: "submit", preventDefault() {} });
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(sentForms.length, 1);
    assert.equal(sentForms[0].get("category"), "work_progress");
    assert.equal(sentForms[0].get("work_id"), "W-SEED-001");
  });
});

// Checks that submitting a question in stoa.js and clicking the pharmacy citation emits map:flyto on bus.
test("test_js_stoa_citation_emits_flyto_on_shared_bus", async () => {
  const env = createFakeEnv();
  await withFakeGlobals(env, async () => {
    const bus = new EventTarget();
    const flytoEvents = [];
    bus.addEventListener("map:flyto", (e) => flytoEvents.push(e.detail));

    api.configure({
      storage: env.storage,
      fetch: async (url) => {
        if (url === "/api/map/stoa_ask") {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              answer_md: "Εφημερεύει κοντά σας: ΠΙΝΟΤΣΗ ΥΠΑΚΟΗ (2), Μητροπόλεως 27.",
              citations: [
                {
                  label: "ΠΙΝΟΤΣΗ ΥΠΑΚΟΗ (2)",
                  lon: 23.731218,
                  lat: 37.975314,
                  kind: "pharmacy",
                },
              ],
            }),
          };
        }
        throw new Error(`Unexpected fetch ${url}`);
      },
    });

    const stoaSlot = env.root.querySelector("#hud-stoa");
    mountStoa({ map: env.map, api, root: stoaSlot, container: stoaSlot, bus });

    stoaSlot.querySelector(".stoa-bubble").click();
    const form = stoaSlot.querySelector(".stoa-form");
    form.querySelector('input[name="q"]').value = "Ποιο φαρμακείο εφημερεύει κοντά μου;";
    form.dispatchEvent({ type: "submit", preventDefault() {} });

    await new Promise((r) => setTimeout(r, 0));

    const citeLink = stoaSlot.querySelector("a.stoa-cite");
    assert.ok(citeLink, "expected rendered pharmacy citation link");
    citeLink.click();

    assert.equal(flytoEvents.length, 1);
    assert.equal(typeof flytoEvents[0].lon, "number");
    assert.equal(typeof flytoEvents[0].lat, "number");
    assert.equal(flytoEvents[0].lon, 23.731218);
    assert.equal(flytoEvents[0].lat, 37.975314);
    assert.equal(flytoEvents[0].label, "ΠΙΝΟΤΣΗ ΥΠΑΚΟΗ (2)");
  });
});
