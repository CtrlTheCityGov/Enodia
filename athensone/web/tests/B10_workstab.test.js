// B10 tests: web/js/ui/workstab.js (Works tab F8: list, filters, crowdsourced progress).
// Runs in Node without a browser or network; uses fake DOM/bus/api objects.
import test from "node:test";
import assert from "node:assert/strict";

const MODULE_PATH = "../js/ui/workstab.js";

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
    value: "",
    href: "",
    target: "",
    rel: "",
    placeholder: "",
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
      _innerHTML = val == null ? "" : String(val);
      this.children = [];
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
      if (!eventObj.currentTarget) eventObj.currentTarget = this;
      if (!eventObj.preventDefault) eventObj.preventDefault = () => {};
      const list = listeners.get(eventObj.type) || [];
      for (const fn of [...list]) fn.call(this, eventObj);
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
  };
  return el;
}

function matchesSelector(el, sel) {
  if (sel.startsWith(".")) return el.classList.contains(sel.slice(1));
  if (sel.startsWith("#")) return el.id === sel.slice(1);
  const attrMatch = sel.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
  if (attrMatch) {
    const [, name, val] = attrMatch;
    if (val === undefined) return el.hasAttribute(name);
    return el.getAttribute(name) === val;
  }
  return el.tagName.toLowerCase() === sel.toLowerCase();
}

function createFakeDocument() {
  const doc = {
    createElement(tag) {
      return createFakeElement(tag, doc);
    },
  };
  return doc;
}

function walkTree(root, predicate, out = []) {
  if (predicate(root)) out.push(root);
  for (const child of root.children || []) walkTree(child, predicate, out);
  return out;
}

// Checks STATUS_FILTERS exposes the 4 required status filters in order with Greek labels.
test("test_js_status_filters_in_order", async () => {
  const { STATUS_FILTERS } = await import(MODULE_PATH);
  assert.equal(STATUS_FILTERS.length, 4);
  assert.deepEqual(
    STATUS_FILTERS.map((f) => f.id),
    ["all", "in_progress", "planned", "completed"],
  );
  assert.deepEqual(
    STATUS_FILTERS.map((f) => f.label),
    ["Όλα", "Σε εξέλιξη", "Προγραμματισμένα", "Ολοκληρωμένα"],
  );
});

// Checks filterWorks filters by status "in_progress" and accent-insensitive query "ερμου".
test("test_js_filter_works_by_status_and_query", async () => {
  const { filterWorks } = await import(MODULE_PATH);
  const features = [
    {
      type: "Feature",
      geometry: { type: "LineString", coordinates: [[23.7341, 37.9756], [23.7283, 37.9762]] },
      properties: {
        id: "W-DIAV-001",
        title: "Ενεργειακή αναβάθμιση πεζοδρομίων (τμήμα Ερμού)",
        status: "in_progress",
        contractor: "ΩΡΙΩΝ Α.Τ.Ε.",
        ada: "Ψ0ΣΝΩ6Μ-5ΙΖ",
      },
    },
    {
      type: "Feature",
      geometry: { type: "LineString", coordinates: [[23.734, 37.975], [23.729, 37.976]] },
      properties: {
        id: "W-PLANNED-ERMOU",
        title: "Διαπλάτυνση πεζοδρομίων οδού Ερμού",
        status: "planned",
        contractor: "ΑΛΦΑ Α.Τ.Ε.",
        ada: "ΑΒΓΔ123-456",
      },
    },
    {
      type: "Feature",
      geometry: { type: "LineString", coordinates: [[23.7337, 37.9768], [23.7297, 37.9818]] },
      properties: {
        id: "W-DIAV-004",
        title: "Αναβάθμιση πεζοδρομίων (τμήμα Σταδίου)",
        status: "in_progress",
        contractor: "ΟΔΟΣ Α.Τ.Ε.",
        ada: "91Π7Ω6Μ-ΠΕ8",
      },
    },
  ];

  const matched = filterWorks(features, { status: "in_progress", query: "ερμου" });
  assert.deepEqual(
    matched.map((f) => f.properties.id),
    ["W-DIAV-001"],
  );
});

// Checks formatWorkCard shows «άγνωστο» for null contractor/amounts and never falls back to 0.
test("test_js_unknown_values_never_zero", async () => {
  const { formatWorkCard } = await import(MODULE_PATH);
  const feature = {
    type: "Feature",
    geometry: { type: "LineString", coordinates: [[23.73, 37.97], [23.75, 37.99]] },
    properties: {
      id: "W-DIAV-9",
      title: "Επιστροφή εγγυήσεων",
      status: "completed",
      contractor: null,
      amount_contract_eur: null,
      amount_paid_eur: null,
      ada: "ΨΓΟ3Ω6Μ-ΔΚ6",
      reports_count: 2,
      seed: false,
    },
  };

  const card = formatWorkCard(feature);
  const serialized = typeof card === "string" ? card : JSON.stringify(card);
  assert.ok(serialized.includes("άγνωστο"), "missing fields must render as άγνωστο");
  assert.doesNotMatch(serialized, /(?<!\d)0(?:[.,]0+)?(?!\d)/, "missing numeric fields must never render as 0");
  if (card && typeof card === "object") {
    for (const [key, val] of Object.entries(card)) {
      if (/contractor|paid|contract|amount/i.test(key)) {
        assert.notEqual(val, 0, `${key} must not be 0`);
        assert.notEqual(val, null, `${key} must not be null`);
        assert.ok(String(val).includes("άγνωστο"), `${key} must show άγνωστο`);
      }
    }
  }
});

// Checks real ΑΔΑ produces a Diavgeia link while SEED works get null URL and a SEED label.
test("test_js_seed_ada_not_linked_to_diavgeia", async () => {
  const { diavgeiaLink, formatWorkCard } = await import(MODULE_PATH);
  const realProps = {
    id: "W-DIAV-001",
    title: "Έργο Ερμού",
    status: "in_progress",
    contractor: "ΩΡΙΩΝ Α.Τ.Ε.",
    amount_contract_eur: null,
    amount_paid_eur: 200023.43,
    ada: "Ψ0ΣΝΩ6Μ-5ΙΖ",
    reports_count: 4,
    seed: false,
  };
  const seedProps = {
    id: "W-SEED-001",
    title: "Ανακατασκευή πεζοδρομίων Μητροπόλεως",
    status: "in_progress",
    contractor: "Ανάδοχος Δείγματος Α",
    amount_contract_eur: 185000,
    amount_paid_eur: 118400,
    ada: "SEED-ΑΔΑ-001",
    reports_count: 3,
    seed: true,
  };

  assert.equal(diavgeiaLink(realProps), "https://diavgeia.gov.gr/decision/view/Ψ0ΣΝΩ6Μ-5ΙΖ");
  assert.equal(diavgeiaLink(seedProps), null);

  const seedCard = formatWorkCard({
    type: "Feature",
    geometry: { type: "LineString", coordinates: [[23.7336, 37.9752], [23.7289, 37.9755]] },
    properties: seedProps,
  });
  const seedText = typeof seedCard === "string" ? seedCard : JSON.stringify(seedCard);
  assert.match(seedText, /SEED|δοκιμαστικ/i);
  assert.equal(seedText.includes("diavgeia.gov.gr"), false);
});

// Checks workMidpoint returns the [lon, lat] midpoint of a LineString geometry.
test("test_js_work_midpoint", async () => {
  const { workMidpoint } = await import(MODULE_PATH);
  const mid = workMidpoint({
    type: "LineString",
    coordinates: [[23.72, 37.97], [23.74, 37.99]],
  });
  assert.ok(Array.isArray(mid) && mid.length === 2);
  assert.ok(Math.abs(mid[0] - 23.73) < 1e-9, `expected lon ~23.73, got ${mid[0]}`);
  assert.ok(Math.abs(mid[1] - 37.98) < 1e-9, `expected lat ~37.98, got ${mid[1]}`);
});

// Checks mount opens the Έργα tab and clicking «Ανέφερε πρόοδο» / map-focus emits report:open and map:flyto on bus.
test("test_js_mount_emits_report_open_and_flyto", async () => {
  const { mount } = await import(MODULE_PATH);
  const prevDocument = globalThis.document;
  const fakeDoc = createFakeDocument();
  globalThis.document = fakeDoc;

  try {
    const bus = new EventTarget();
    const reportEvents = [];
    const flytoEvents = [];
    bus.addEventListener("report:open", (e) => reportEvents.push(e.detail));
    bus.addEventListener("map:flyto", (e) => flytoEvents.push(e.detail));

    const workFeature = {
      type: "Feature",
      geometry: { type: "LineString", coordinates: [[23.72, 37.97], [23.74, 37.99]] },
      properties: {
        id: "W-TEST-1",
        title: "Αναβάθμιση οδού Ερμού",
        status: "in_progress",
        contractor: "ΩΡΙΩΝ Α.Τ.Ε.",
        amount_contract_eur: 100000,
        amount_paid_eur: 50000,
        ada: "Ψ0ΣΝΩ6Μ-5ΙΖ",
        reports_count: 3,
        seed: false,
      },
    };
    const api = {
      async works() {
        return { type: "FeatureCollection", features: [workFeature], source: "mock" };
      },
    };
    const map = { getCenter: () => ({ lng: 23.7348, lat: 37.9755 }) };
    const root = fakeDoc.createElement("div");

    await mount({ map, api, root, bus });
    await new Promise((r) => setTimeout(r, 0));

    const worksTab = walkTree(
      root,
      (el) => el.getAttribute("role") === "tab" && el.textContent.includes("Έργα"),
    )[0];
    assert.ok(worksTab, "expected «Έργα» tab with role=\"tab\"");
    worksTab.click();
    await new Promise((r) => setTimeout(r, 0));

    const reportBtn = walkTree(
      root,
      (el) => el.tagName === "BUTTON" && el.textContent.includes("Ανέφερε πρόοδο"),
    )[0];
    assert.ok(reportBtn, "expected «Ανέφερε πρόοδο» button in works list");
    reportBtn.click();

    assert.equal(reportEvents.length, 1);
    assert.equal(reportEvents[0].work_id, "W-TEST-1");
    assert.ok(reportEvents[0].lngLat, "report:open detail must include lngLat");
    assert.ok(Math.abs(reportEvents[0].lngLat.lng - 23.73) < 1e-9);
    assert.ok(Math.abs(reportEvents[0].lngLat.lat - 37.98) < 1e-9);

    const filterLabels = new Set(["Όλα", "Σε εξέλιξη", "Προγραμματισμένα", "Ολοκληρωμένα"]);
    const focusBtn = walkTree(
      root,
      (el) =>
        el.tagName === "BUTTON" &&
        el.getAttribute("role") !== "tab" &&
        !filterLabels.has(el.textContent.trim()) &&
        !el.textContent.includes("Ανέφερε πρόοδο") &&
        /χάρτ|εστία|προβολ|θέση|εντοπισ|focus|fly|map/i.test(
          `${el.textContent} ${el.getAttribute("aria-label") || ""} ${el.className}`,
        ),
    )[0];
    assert.ok(focusBtn, "expected map-focus button on the work card");
    focusBtn.click();

    assert.equal(flytoEvents.length, 1);
    assert.ok(Math.abs(flytoEvents[0].lon - 23.73) < 1e-9);
    assert.ok(Math.abs(flytoEvents[0].lat - 37.98) < 1e-9);
    assert.equal(flytoEvents[0].label, "Αναβάθμιση οδού Ερμού");
  } finally {
    if (prevDocument === undefined) delete globalThis.document;
    else globalThis.document = prevDocument;
  }
});

// Checks importing ui/workstab.js in Node touches no DOM/map/network globals and throws no error.
test("test_js_import_has_no_dom", async () => {
  const before = new Set(Object.getOwnPropertyNames(globalThis));
  const prevFetch = globalThis.fetch;
  let fetchCalled = false;
  globalThis.fetch = () => {
    fetchCalled = true;
    throw new Error("fetch must not be called at import time");
  };
  try {
    await import(`${MODULE_PATH}?fresh-import`);
  } finally {
    globalThis.fetch = prevFetch;
  }
  const after = Object.getOwnPropertyNames(globalThis);
  assert.deepEqual(after.filter((k) => !before.has(k)), []);
  assert.equal(fetchCalled, false);
  assert.equal(typeof document, "undefined");
  assert.equal(typeof window, "undefined");
  assert.equal(typeof maplibregl, "undefined");
});
