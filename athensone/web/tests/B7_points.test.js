import test from "node:test";
import assert from "node:assert/strict";

import { formatDelta, mount } from "../js/ui/points.js";

function createFakeElement(tagName) {
  const classes = new Set();
  const attrs = new Map();
  const listeners = new Map();
  let _className = "";
  let _textContent = "";

  const el = {
    tagName: String(tagName || "div").toUpperCase(),
    children: [],
    parentNode: null,
    style: {},
    dataset: {},
    id: "",
    type: "",
    disabled: false,
    get className() {
      return _className;
    },
    set className(val) {
      _className = String(val || "");
      classes.clear();
      for (const part of _className.split(/\s+/).filter(Boolean)) {
        classes.add(part);
      }
    },
    classList: {
      add(...names) {
        for (const n of names) {
          if (n) classes.add(n);
        }
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
    setAttribute(k, v) {
      const s = String(v);
      attrs.set(k, s);
      if (k === "id") this.id = s;
      if (k === "class") this.className = s;
    },
    getAttribute(k) {
      if (k === "id") return this.id || null;
      if (k === "class") return this.className || null;
      return attrs.has(k) ? attrs.get(k) : null;
    },
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
      return child;
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
      const list = listeners.get(evt.type) || [];
      for (const fn of [...list]) fn.call(this, evt);
      return true;
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
  return el.tagName.toLowerCase() === sel.toLowerCase();
}

function findInTree(root, predicate) {
  if (predicate(root)) return root;
  for (const child of root.children || []) {
    const found = findInTree(child, predicate);
    if (found) return found;
  }
  return null;
}

test("test_js_format_delta", () => {
  // Formats positive and negative point deltas using '+' and the Unicode minus sign '−'.
  assert.equal(formatDelta(5), "+5");
  assert.equal(formatDelta(-30), "\u221230");
});

test("test_js_pulse_on_event", async (t) => {
  // Receiving points:earned {delta: 5} on the bus pulses the pill for 600ms, shows '+5', and adds 5 to balance.
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const prevDocument = globalThis.document;
  globalThis.document = { createElement: createFakeElement };

  try {
    const bus = new EventTarget();
    const root = createFakeElement("div");
    const initialWallet = {
      balance: 10,
      district: { name: "1η Δημοτική Κοινότητα", progress_pct: 20, goal: 5000 },
      history: [],
      rewards: [],
      source: "mock",
    };
    const api = {
      async points() {
        return initialWallet;
      },
      async getPoints() {
        return initialWallet;
      },
      async redeemPoints() {
        return { ok: true, balance: 10, voucher_code: "MOCK" };
      },
    };

    await mount({ map: null, api, root, bus });
    assert.match(root.textContent, /10/);

    bus.dispatchEvent(new CustomEvent("points:earned", { detail: { delta: 5, reason: "Αναφορά συμβάντος" } }));

    assert.ok(findInTree(root, (el) => el.classList.contains("pulse")), "pill should have 'pulse' class");
    assert.match(root.textContent, /\+5/);
    assert.match(root.textContent, /15/);

    t.mock.timers.tick(600);
    assert.equal(findInTree(root, (el) => el.classList.contains("pulse")), null);
  } finally {
    globalThis.document = prevDocument;
  }
});
