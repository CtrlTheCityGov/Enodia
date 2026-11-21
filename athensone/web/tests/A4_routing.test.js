// A4 Routing drawer + animated route tests (TASKS_A.md "### A4", SPEC.md F5 & "Routing").
import test from "node:test";
import assert from "node:assert/strict";
import * as routingMod from "../js/ui/routing.js";

function withGlobals(overrides, fn) {
  const previous = new Map();
  for (const key of Object.keys(overrides)) {
    previous.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
    Object.defineProperty(globalThis, key, {
      value: overrides[key],
      configurable: true,
      writable: true,
      enumerable: true,
    });
  }
  try {
    return fn();
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

function createFakeLocalStorage() {
  const store = new Map();
  return {
    get length() {
      return store.size;
    },
    key(index) {
      return [...store.keys()][index] ?? null;
    },
    getItem(key) {
      return store.has(String(key)) ? store.get(String(key)) : null;
    },
    setItem(key, value) {
      store.set(String(key), String(value));
    },
    removeItem(key) {
      store.delete(String(key));
    },
    clear() {
      store.clear();
    },
    _dump() {
      return Object.fromEntries(store.entries());
    },
  };
}

function camelToKebab(name) {
  return name.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`);
}

function kebabToCamel(name) {
  return name.replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
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

function createFakeElement(tagName, ownerDocument, options = {}) {
  const attrs = new Map();
  const listeners = new Map();
  const children = [];
  let classSet = new Set();
  let text = "";
  let height = options.height ?? 0;

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
      ownKeys() {
        return [...attrs.keys()]
          .filter((k) => k.startsWith("data-"))
          .map((k) => kebabToCamel(k.slice(5)));
      },
      getOwnPropertyDescriptor(_target, prop) {
        const key = `data-${camelToKebab(String(prop))}`;
        if (!attrs.has(key)) return undefined;
        return { enumerable: true, configurable: true, value: attrs.get(key) };
      },
    },
  );

  const el = {
    tagName: tagName.toUpperCase(),
    ownerDocument,
    parentNode: null,
    children,
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
      text = val === null || val === undefined ? "" : String(val);
    },
    get offsetHeight() {
      return height;
    },
    get clientHeight() {
      return height;
    },
    getBoundingClientRect() {
      return { width: 360, height, top: 0, left: 0, right: 360, bottom: height };
    },
    _setHeight(h) {
      height = h;
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
      if (child.parentNode && child.parentNode !== el) {
        const idx = child.parentNode.children.indexOf(child);
        if (idx !== -1) child.parentNode.children.splice(idx, 1);
      }
      child.parentNode = el;
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

function createFakeDocument() {
  const doc = {
    createElement(tag) {
      return createFakeElement(tag, doc);
    },
    createTextNode(str) {
      return { textContent: String(str) };
    },
  };
  return doc;
}

function createFakeMap() {
  const sources = new Map();
  const layers = new Map();
  const paintProps = new Map();
  const layoutProps = new Map();
  const listeners = new Map();
  const setPaintCalls = [];
  const fitBoundsCalls = [];

  const fakeMap = {
    setPaintCalls,
    fitBoundsCalls,
    getSource(id) {
      return sources.get(id);
    },
    addSource(id, src) {
      sources.set(id, {
        ...src,
        setData(next) {
          sources.get(id).data = next;
        },
      });
      return fakeMap;
    },
    removeSource(id) {
      sources.delete(id);
      return fakeMap;
    },
    getLayer(id) {
      return layers.get(id);
    },
    addLayer(layer) {
      layers.set(layer.id, layer);
      return fakeMap;
    },
    removeLayer(id) {
      layers.delete(id);
      return fakeMap;
    },
    setPaintProperty(layerId, name, value) {
      paintProps.set(`${layerId}:${name}`, value);
      setPaintCalls.push({ layerId, name, value });
      return fakeMap;
    },
    getPaintProperty(layerId, name) {
      return paintProps.get(`${layerId}:${name}`);
    },
    setLayoutProperty(layerId, name, value) {
      layoutProps.set(`${layerId}:${name}`, value);
      return fakeMap;
    },
    fitBounds(bounds, options) {
      fitBoundsCalls.push({ bounds, options });
      return fakeMap;
    },
    on(event, fn) {
      if (!listeners.has(event)) listeners.set(event, []);
      listeners.get(event).push(fn);
      return fakeMap;
    },
    off(event, fn) {
      if (listeners.has(event)) {
        listeners.set(
          event,
          listeners.get(event).filter((cb) => cb !== fn),
        );
      }
      return fakeMap;
    },
  };

  return fakeMap;
}

function isTransparentColor(color) {
  if (typeof color !== "string") return false;
  const c = color.trim().toLowerCase();
  if (c === "transparent") return true;
  if (/^#([0-9a-f]{4}|[0-9a-f]{8})$/.test(c)) {
    const alphaHex = c.length === 5 ? c.slice(4) : c.slice(7);
    return Number.parseInt(alphaHex, 16) === 0;
  }
  const rgbaMatch = c.match(/^(?:rgba|hsla)\([^,]+,[^,]+,[^,]+,\s*([0-9.]+)\s*\)$/);
  if (rgbaMatch) {
    return Number(rgbaMatch[1]) === 0;
  }
  return false;
}

function getGradientDrawnEnd(expr) {
  assert.ok(Array.isArray(expr), "line-gradient expression must be an array");
  const op = expr[0];

  if (op === "interpolate") {
    assert.ok(Array.isArray(expr[1]), "interpolate must specify interpolation method");
    assert.deepEqual(expr[2], ["line-progress"], "interpolate must use ['line-progress']");
    const args = expr.slice(3);
    assert.ok(args.length >= 4 && args.length % 2 === 0, "interpolate needs >= 2 stop/color pairs");

    let prevStop = -Infinity;
    let lastDrawnStop = null;
    for (let i = 0; i < args.length; i += 2) {
      const stop = args[i];
      const color = args[i + 1];
      assert.equal(typeof stop, "number", "gradient stop must be a number");
      assert.ok(stop >= 0 && stop <= 1, "gradient stop must be within [0, 1]");
      assert.ok(stop > prevStop, "interpolate stops must be strictly ascending");
      assert.equal(typeof color, "string", "gradient color must be a string");
      assert.ok(color.length > 0, "gradient color must be non-empty");
      prevStop = stop;
      if (!isTransparentColor(color)) {
        lastDrawnStop = stop;
      }
    }
    return lastDrawnStop ?? 0;
  }

  if (op === "step") {
    assert.deepEqual(expr[1], ["line-progress"], "step must use ['line-progress']");
    const defaultColor = expr[2];
    assert.equal(typeof defaultColor, "string", "step default color must be a string");
    const args = expr.slice(3);
    assert.ok(args.length % 2 === 0, "step stops must come in pairs");

    let prevStop = -Infinity;
    let firstTransparentStop = null;
    for (let i = 0; i < args.length; i += 2) {
      const stop = args[i];
      const color = args[i + 1];
      assert.equal(typeof stop, "number", "gradient stop must be a number");
      assert.ok(stop >= 0 && stop <= 1, "gradient stop must be within [0, 1]");
      assert.ok(stop > prevStop, "step stops must be strictly ascending");
      assert.equal(typeof color, "string", "gradient color must be a string");
      prevStop = stop;
      if (isTransparentColor(color) && firstTransparentStop === null) {
        firstTransparentStop = stop;
      }
    }
    if (isTransparentColor(defaultColor)) return 0;
    return firstTransparentStop ?? 1;
  }

  assert.fail(`Unsupported line-gradient expression operator: ${String(op)}`);
}

// Verify PROFILES lists wheelchair, stroller, and cool in SPEC order with Greek labels.
test("test_profiles_three_in_order", () => {
  const { PROFILES } = routingMod;
  assert.ok(Array.isArray(PROFILES), "PROFILES export must be an array");
  assert.equal(PROFILES.length, 3, "PROFILES must contain exactly three profiles");
  assert.deepEqual(
    PROFILES.map((p) => p.id),
    ["wheelchair", "stroller", "cool"],
  );
  assert.equal(PROFILES[0].label, "Αμαξίδιο");
  assert.equal(PROFILES[1].label, "Καρότσι");
  assert.ok(
    typeof PROFILES[2].label === "string" && PROFILES[2].label.includes("Δροσερότερη"),
    "third profile label must be Greek Δροσερότερη",
  );
});

// Verify picking the cool profile persists it to localStorage and restores it on re-init.
test("test_profile_saved_and_restored", () => {
  const storage = createFakeLocalStorage();
  const doc = createFakeDocument();

  withGlobals({ localStorage: storage, document: doc }, () => {
    const container1 = doc.createElement("div");
    const map1 = createFakeMap();
    routingMod.initRouting(container1, map1, null);

    const coolBtn1 = container1.querySelector('[data-profile="cool"]');
    assert.ok(coolBtn1, "initRouting must render a profile button with data-profile='cool'");
    coolBtn1.click();

    assert.ok(
      Object.values(storage._dump()).includes("cool"),
      "selecting cool must save 'cool' in localStorage",
    );

    const container2 = doc.createElement("div");
    const map2 = createFakeMap();
    routingMod.initRouting(container2, map2, null);

    const coolBtn2 = container2.querySelector('[data-profile="cool"]');
    const wheelchairBtn2 = container2.querySelector('[data-profile="wheelchair"]');
    const strollerBtn2 = container2.querySelector('[data-profile="stroller"]');
    assert.ok(coolBtn2, "re-init must render the cool profile button");
    assert.equal(coolBtn2.getAttribute("aria-pressed"), "true");
    if (wheelchairBtn2) {
      assert.equal(wheelchairBtn2.getAttribute("aria-pressed"), "false");
    }
    if (strollerBtn2) {
      assert.equal(strollerBtn2.getAttribute("aria-pressed"), "false");
    }
  });
});

// Verify routeSource(geojson) returns a GeoJSON source with lineMetrics: true for line-gradient.
test("test_route_source_has_line_metrics", () => {
  assert.equal(typeof routingMod.routeSource, "function", "routeSource export must exist");
  const geojson = {
    type: "Feature",
    properties: {},
    geometry: {
      type: "LineString",
      coordinates: [
        [23.7348, 37.9755],
        [23.7257, 37.9764],
      ],
    },
  };

  const src = routingMod.routeSource(geojson);
  assert.ok(src && typeof src === "object", "routeSource must return a source object");
  assert.equal(src.type, "geojson");
  assert.equal(src.lineMetrics, true);
  assert.deepEqual(src.data, geojson);
});

// Verify gradientAt(0), gradientAt(0.5), and gradientAt(1) produce valid line-gradient expressions ending at 0, 0.5, and 1.
test("test_gradient_progress", () => {
  assert.equal(typeof routingMod.gradientAt, "function", "gradientAt export must exist");

  const g0 = routingMod.gradientAt(0);
  const gHalf = routingMod.gradientAt(0.5);
  const g1 = routingMod.gradientAt(1);

  const end0 = getGradientDrawnEnd(g0);
  const endHalf = getGradientDrawnEnd(gHalf);
  const end1 = getGradientDrawnEnd(g1);

  assert.ok(end0 <= 0.01, `gradientAt(0) drawn part must end at 0, got ${end0}`);
  assert.ok(Math.abs(endHalf - 0.5) <= 0.01, `gradientAt(0.5) drawn part must end at 0.5, got ${endHalf}`);
  assert.equal(end1, 1, `gradientAt(1) drawn part must end at 1, got ${end1}`);
});

// Verify animateRoute advances progress via mocked requestAnimationFrame to reach 1 at ~1200 ms, not before 1100 ms.
test("test_animation_duration_1200ms", () => {
  assert.equal(typeof routingMod.animateRoute, "function", "animateRoute export must exist");

  let now = 0;
  let nextId = 1;
  let queue = [];

  function fakeRaf(cb) {
    const id = nextId++;
    queue.push({ id, cb });
    return id;
  }

  function fakeCancelRaf(id) {
    queue = queue.filter((item) => item.id !== id);
  }

  function stepTo(ms) {
    now = ms;
    const batch = queue;
    queue = [];
    for (const item of batch) {
      item.cb(now);
    }
  }

  const fakeMap = createFakeMap();
  fakeMap.addLayer({ id: "route-line", type: "line", source: "route", paint: {} });
  let completed = false;

  withGlobals(
    {
      requestAnimationFrame: fakeRaf,
      cancelAnimationFrame: fakeCancelRaf,
      performance: { now: () => now },
    },
    () => {
      routingMod.animateRoute(fakeMap, "route-line", () => {
        completed = true;
      });

      assert.ok(queue.length > 0, "animateRoute must schedule requestAnimationFrame");

      stepTo(0);
      assert.equal(completed, false, "animation must not complete at 0 ms");
      assert.ok(fakeMap.setPaintCalls.length >= 1, "animation must update line-gradient");

      stepTo(600);
      const midCall = fakeMap.setPaintCalls.at(-1);
      assert.equal(midCall.layerId, "route-line");
      assert.equal(midCall.name, "line-gradient");
      assert.ok(getGradientDrawnEnd(midCall.value) < 1, "progress must be < 1 at 600 ms");
      assert.equal(completed, false);

      stepTo(1099);
      const before1100Call = fakeMap.setPaintCalls.at(-1);
      assert.ok(
        getGradientDrawnEnd(before1100Call.value) < 1,
        "progress must not reach 1 before 1100 ms",
      );
      assert.equal(completed, false, "animation must not finish before 1100 ms");

      stepTo(1200);
      if (!completed && queue.length > 0) {
        stepTo(1250);
      }
      const endCall = fakeMap.setPaintCalls.at(-1);
      assert.equal(
        getGradientDrawnEnd(endCall.value),
        1,
        "progress must reach 1 at ~1200 ms",
      );
      assert.equal(completed, true, "onComplete must fire once animation reaches 1");
    },
  );
});

// Verify fitRouteBounds leaves at least drawerHeight + 24 px bottom padding (324 px for a 300 px drawer).
test("test_fit_bounds_padding_leaves_drawer", () => {
  assert.equal(typeof routingMod.fitRouteBounds, "function", "fitRouteBounds export must exist");

  const doc = createFakeDocument();
  const drawerEl = doc.createElement("div");
  drawerEl._setHeight(300);

  const fakeMap = createFakeMap();
  const routeGeojson = {
    type: "Feature",
    properties: {},
    geometry: {
      type: "LineString",
      coordinates: [
        [23.7348, 37.9755],
        [23.7257, 37.9764],
      ],
    },
  };

  routingMod.fitRouteBounds(fakeMap, routeGeojson, drawerEl);

  assert.equal(fakeMap.fitBoundsCalls.length, 1, "fitBounds must be called once");
  const { options } = fakeMap.fitBoundsCalls[0];
  assert.ok(options && options.padding && typeof options.padding === "object");
  assert.ok(
    options.padding.bottom >= 324,
    `expected bottom padding >= 324 for a 300 px drawer, got ${options.padding.bottom}`,
  );
});

// Verify routeLabel formats duration in minutes, distance in km with Greek comma, and joined reasons.
test("test_route_label", () => {
  assert.equal(typeof routingMod.routeLabel, "function", "routeLabel export must exist");

  const label = routingMod.routeLabel({
    distance_m: 1520,
    duration_s: 1260,
    reasons: [
      { text: "αποφεύγει 2 έργα", layer: "works", feature_id: "w1" },
      { text: "−2°C σκιά", layer: "env", feature_id: "e1" },
    ],
  });

  assert.equal(label, "21′ · 1,5 km · αποφεύγει 2 έργα, −2°C σκιά");
});

// Verify routeLabel omits the separator when reasons is empty.
test("test_route_label_no_reasons", () => {
  assert.equal(typeof routingMod.routeLabel, "function", "routeLabel export must exist");

  const label = routingMod.routeLabel({
    distance_m: 1520,
    duration_s: 1260,
    reasons: [],
  });

  assert.equal(label, "21′ · 1,5 km");
});
