import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { popupHtml } from "../js/ui/workpopup.js";
import { renderProvenanceHtml } from "../js/ui/stoa.js";
import { register as registerTransit } from "../js/layers/transit.js";
const RAIL_STATIONS_LAYER_ID = "transit-rail-stations";
import { initRouting } from "../js/ui/routing.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIR = path.resolve(__dirname, "..");

test("test_a_op_1_operator_ids_and_glass_claim_card", () => {
  // The Stoa panel moved into operator-case.js (loaded by operator.html); check both files together.
  const html = fs.readFileSync(path.join(WEB_DIR, "operator.html"), "utf8") +
    fs.readFileSync(path.join(WEB_DIR, "operator-case.js"), "utf8");
  const css = fs.readFileSync(path.join(WEB_DIR, "app.css"), "utf8");

  for (const id of [
    "mode",
    "count",
    "stoaAskForm",
    "radarDays",
    "equity",
    "list",
    "detail",
    "dWorks",
    // approve/resolve/reject one-click buttons were replaced by the audited case workflow (operator-case.js,
    // docs/FINAL_ENGINEERING_AUDIT.md F-6); the demo reset control is new.
    "demoReset",
  ]) {
    assert.ok(html.includes(`id="${id}"`), `operator.html must preserve #${id}`);
  }

  assert.ok(html.includes("Stoa Guarantee Claim"), "operator.html must render Stoa Guarantee Claim heading");
  assert.ok(html.includes("Φάκελος Εγγύησης"), "operator.html must render Φάκελος Εγγύησης button");
  assert.ok(html.includes("diavgeia.gov.gr/decision/view/"), "operator.html must link [ΑΔΑ] to Diavgeia");
  assert.ok(css.includes("backdrop-filter") && css.includes("prefers-color-scheme: dark"), "app.css must include glass & dark mode styles");
  assert.ok(css.includes(".stoa-claim__grid"), "app.css must style Stoa Guarantee Claim grid");
});

test("test_a_prov_1_provenance_pills_and_seed_badge", () => {
  const liveHtml = popupHtml({
    title: "Οδός Ερμού",
    status: "in_progress",
    contractor: "ΕΡΓΟ ΑΕ",
    amount_paid_eur: 12000,
    amount_contract_eur: 24000,
    ada: "Ψ1ΑΒΩ6Μ-123",
    source: "live",
    updated_at: "2026-11-21T10:00:00Z",
  });
  assert.ok(liveHtml.includes("LIVE"), "workpopup must show LIVE pill");
  assert.ok(liveHtml.includes("prov-updated"), "workpopup must show updated_at when provided");

  const cachedHtml = popupHtml({ title: "Οδός Α", status: "planned", source: "cache" });
  assert.ok(cachedHtml.includes("CACHED"), "workpopup must show CACHED pill");

  const seedHtml = popupHtml({ title: "Δείγμα", status: "completed", ada: "SEED-001" });
  assert.ok(seedHtml.includes("DEMO"), "workpopup must show DEMO pill for SEED");
  assert.ok(seedHtml.includes("SEED · δοκιμαστικό"), "workpopup must keep SEED badge");

  const stoaLive = renderProvenanceHtml({ source: "live", updated_at: "2026-11-21T12:00:00Z" });
  assert.ok(stoaLive.includes("LIVE") && stoaLive.includes("prov-updated"));
  const stoaCached = renderProvenanceHtml({ source: "cache" });
  assert.ok(stoaCached.includes("CACHED"));
  const stoaDemo = renderProvenanceHtml({ source: "mock" });
  assert.ok(stoaDemo.includes("DEMO"));
});

test("test_a_loop_1_transit_arrivals_popup_on_station_click", async () => {
  const handlers = new Map();
  const sources = new Map();
  const layers = new Map();
  const fakeMap = {
    getSource: (id) => sources.get(id),
    addSource: (id, src) => sources.set(id, { ...src, setData: () => {} }),
    getLayer: (id) => layers.get(id),
    addLayer: (l) => layers.set(l.id, l),
    on: (ev, layerId, fn) => handlers.set(`${ev}:${layerId}`, fn),
    getCanvas: () => ({ style: {} }),
  };

  let popupHtmlText = "";
  globalThis.maplibregl = {
    Popup: class {
      setLngLat() { return this; }
      setHTML(h) { popupHtmlText = h; return this; }
      addTo() { return this; }
    },
  };

  let requestedStopCode = null;
  const api = {
    transit: async () => ({ lines: { type: "FeatureCollection", features: [] }, stations: { type: "FeatureCollection", features: [] }, buses: { type: "FeatureCollection", features: [] } }),
    transitArrivals: async (stopCode) => {
      requestedStopCode = stopCode;
      return {
        stop_code: stopCode,
        source: "live",
        arrivals: [{ line: "X95", wait_min: 4 }],
      };
    },
  };

  try {
    await registerTransit(fakeMap, api, { visible: {} });
    const clickHandler = handlers.get(`click:${RAIL_STATIONS_LAYER_ID}`);
    assert.equal(typeof clickHandler, "function", "station click handler must be registered");

    await clickHandler({
      lngLat: { lng: 23.735, lat: 37.975 },
      features: [{ properties: { name: "Σύνταγμα", line: "M2", stop_code: "1001" } }],
    });

    assert.equal(requestedStopCode, "1001");
    assert.ok(popupHtmlText.includes("4 λεπτά"), "popup must display wait_min in Greek minutes");
    assert.ok(popupHtmlText.includes("X95"), "popup must display route line");
  } finally {
    delete globalThis.maplibregl;
  }
});

test("test_a_loop_1_routing_refreshes_on_reports_changed", async () => {
  const makeEl = (tag = "div") => {
    const el = {
      tagName: tag.toUpperCase(),
      children: [],
      className: "",
      style: {},
      dataset: {},
      textContent: "",
      value: "",
      disabled: false,
      classList: { add() {}, remove() {}, toggle() {} },
      setAttribute() {},
      addEventListener(ev, fn) {
        this._listeners = this._listeners || {};
        this._listeners[ev] = this._listeners[ev] || [];
        this._listeners[ev].push(fn);
      },
      appendChild(c) { this.children.push(c); return c; },
      append(...cs) { this.children.push(...cs); },
      replaceChildren(...cs) { this.children = [...cs]; },
      querySelector() { return null; },
      querySelectorAll() { return []; },
    };
    return el;
  };
  const fakeDoc = { createElement: (t) => makeEl(t) };
  const container = makeEl("div");
  container.ownerDocument = fakeDoc;

  const bus = new EventTarget();
  let routingCalls = 0;
  const api = {
    routing: async () => {
      routingCalls += 1;
      return {
        source: "live",
        geometry: { type: "LineString", coordinates: [[23.73, 37.97], [23.74, 37.98]] },
        distance_m: 1200,
        duration_s: 900,
        reasons: [],
      };
    },
  };

  const ctrl = initRouting(container, null, api, { bus });
  // Trigger initial route via route:request
  bus.dispatchEvent(new CustomEvent("route:request", {
    detail: { from: [23.73, 37.97], to: [23.74, 37.98], profile: "wheelchair" },
  }));
  await new Promise((r) => setTimeout(r, 15));
  assert.equal(routingCalls, 1, "initial route request must call api.routing once");

  // Emit reports:changed while active route is displayed -> should re-run routing
  bus.dispatchEvent(new CustomEvent("reports:changed", { detail: { count: 1 } }));
  await new Promise((r) => setTimeout(r, 15));
  assert.equal(routingCalls, 2, "reports:changed must refresh active route");

  ctrl.destroy();
});
