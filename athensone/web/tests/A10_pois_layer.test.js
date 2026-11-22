// A10 tests: "Υπηρεσίες Δήμου" layer (web/js/layers/pois.js) and its chip in layerbar.
import test from "node:test";
import assert from "node:assert/strict";

import * as pois from "../js/layers/pois.js";
import * as layerbar from "../js/ui/layerbar.js";

const FEATURES = [
  { type: "Feature", geometry: { type: "Point", coordinates: [23.73, 37.98] }, properties: { id: "a", name: "A", category: "library" } },
  { type: "Feature", geometry: { type: "Point", coordinates: [23.74, 37.99] }, properties: { id: "b", name: "B", category: "friendship_club" } },
];

function fakeMap() {
  const sources = {};
  const layers = [];
  return {
    sources,
    layers,
    getSource: (id) => sources[id],
    addSource(id, spec) {
      sources[id] = { spec, data: spec.data, setData(d) { this.data = d; } };
    },
    getLayer: (id) => layers.find((l) => l.id === id),
    addLayer(l) { layers.push(l); },
    on() {},
  };
}

const okApi = (source = "live") => ({ pois: async () => ({ type: "FeatureCollection", features: FEATURES, source }) });

// Importing the module must not need document or maplibregl, and exports are as the card says.
test("pois layer exports id, label, layerIds", () => {
  assert.equal(globalThis.document, undefined);
  assert.equal(globalThis.maplibregl, undefined);
  assert.equal(pois.id, "pois");
  assert.equal(pois.label, "Δήμος");
  assert.deepEqual(pois.layerIds, ["pois-points"]);
});

// A hidden circle layer and a geojson source carrying the API features.
test("register adds source and hidden layer", async () => {
  const map = fakeMap();
  await pois.register(map, okApi(), { visible: {} });
  const srcs = Object.values(map.sources);
  assert.equal(srcs.length, 1);
  assert.equal(srcs[0].spec.type, "geojson");
  assert.equal(map.layers.length, 1);
  assert.equal(map.layers[0].type, "circle");
  assert.equal(map.layers[0].layout.visibility, "none");
  assert.equal(srcs[0].data.features.length, 2);
});

// state.visible.pois = true shows the layer.
test("register visible when state says so", async () => {
  const map = fakeMap();
  await pois.register(map, okApi(), { visible: { pois: true } });
  assert.equal(map.layers[0].layout.visibility, "visible");
});

// Mock data triggers the offline badge exactly once.
test("register calls onOffline for mock data", async () => {
  const map = fakeMap();
  let calls = 0;
  await pois.register(map, okApi("mock"), { visible: {}, onOffline: () => { calls += 1; } });
  assert.equal(calls, 1);
});

// A failing API must not throw and leaves an empty collection.
test("register survives api failure", async () => {
  const map = fakeMap();
  const api = { pois: async () => { throw new Error("down"); } };
  await assert.doesNotReject(() => pois.register(map, api, { visible: {} }));
  const src = Object.values(map.sources)[0];
  assert.deepEqual(src.data.features, []);
});

// Greek category label, open state and official badge; no mock badge for live data.
test("popupHtml shows Greek category and open state", () => {
  const html = pois.popupHtml({ name: "Λέσχη Φιλίας Παγκρατίου", category: "friendship_club", address: "Χ 1", open_now: true, source: "live" });
  assert.ok(html.includes("Λέσχη Φιλίας"));
  assert.ok(html.includes("Ανοιχτό τώρα"));
  assert.ok(html.includes("επίσημο"));
  assert.ok(!html.includes("δοκιμαστικό"));
});

// Unknown address and opening hours show «άγνωστο», never blank.
test("popupHtml unknowns", () => {
  const html = pois.popupHtml({ name: "X", category: "library", address: null, open_now: null, source: "live" });
  assert.ok(html.includes("άγνωστο"));
  assert.ok(html.includes("Ωράριο: άγνωστο"));
});

// The name is untrusted text and must be escaped.
test("popupHtml escapes the name", () => {
  const html = pois.popupHtml({ name: "<img src=x onerror=1>", category: "library", address: "Χ", open_now: false, source: "live" });
  assert.ok(!html.includes("<img"));
});

// Mock data is labelled.
test("popupHtml labels mock", () => {
  const html = pois.popupHtml({ name: "X", category: "library", address: "Χ", open_now: true, source: "mock" });
  assert.ok(html.includes("δοκιμαστικό"));
});

// The seventh chip is the municipal one, added last.
test("layerbar has the Δήμος chip last", () => {
  const chips = layerbar.CHIPS;
  assert.equal(chips.length, 7);
  assert.equal(chips[chips.length - 1].id, "pois");
  assert.equal(chips[chips.length - 1].label, "Δήμος");
});
