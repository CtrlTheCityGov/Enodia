import test from "node:test";
import assert from "node:assert/strict";

import { mount } from "../js/ui/points.js";

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
    async trigger(type, evt = { type }) {
      const list = listeners.get(type) || [];
      for (const fn of [...list]) await fn.call(this, evt);
    },
    querySelectorAll(selector) {
      const matches = [];
      const walk = (node) => {
        for (const child of node.children) {
          if (selector.startsWith(".") && child.classList.contains(selector.slice(1))) matches.push(child);
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

test("test_js_redeem_throw_handled", async () => {
  // When api.redeem throws an error, redeem() catches it and sets .points-status text instead of throwing.
  const prevDocument = globalThis.document;
  globalThis.document = { createElement: createFakeElement };

  try {
    const bus = new EventTarget();
    const root = createFakeElement("div");
    const api = {
      async points() {
        return {
          balance: 50,
          district: { name: "1η Δημοτική Κοινότητα", progress_pct: 10, goal: 5000 },
          history: [],
          rewards: [{ id: "R1", title: "Δοκιμή", cost: 30 }],
          source: "live",
        };
      },
      async redeem() {
        throw new Error("network boom");
      },
    };

    await mount({ map: null, api, root, bus });
    const pill = root.querySelector(".points-pill");
    await pill.trigger("click");

    const redeemBtn = root.querySelector(".points-redeem");
    assert.ok(redeemBtn, "expected redeem button");
    await redeemBtn.trigger("click");

    const status = root.querySelector(".points-status");
    assert.ok(status && status.textContent.length > 0, "expected error message in .points-status");
  } finally {
    globalThis.document = prevDocument;
  }
});
