// B15 tests: api.resolved(), the «Διορθώθηκαν κοντά σου» layer. Offline, no server, no browser.
import { test } from "node:test";
import assert from "node:assert/strict";

const api = await import("../js/api.js");

const respond = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
function fakeStorage() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k), clear: () => m.clear() };
}
function setup(fetchFn) {
  api.configure({ fetch: fetchFn, storage: fakeStorage(), base: "", mockBase: "mock/", timeoutMs: 5000 });
}

test("resolved: live answer marked live", async () => {
  // Fake fetch answers 200: source is "live" and the path starts with /api/map/resolved.
  const fc = { type: "FeatureCollection", features: [], summary: { count: 0, median_hours_to_resolve: null } };
  const calls = [];
  setup(async (url) => { calls.push(String(url)); return respond(fc); });
  const out = await api.resolved({ bbox: [23.72, 37.97, 23.74, 37.98], days: 30 });
  assert.equal(out.source, "live");
  assert.ok(calls[0].startsWith("/api/map/resolved"));
});

test("resolved: offline gives empty collection", async () => {
  // Fetch rejects: source "mock", no features, summary.count 0.
  setup(async () => { throw new TypeError("network down"); });
  const out = await api.resolved();
  assert.equal(out.source, "mock");
  assert.equal(out.features.length, 0);
  assert.equal(out.summary.count, 0);
});

test("resolved: backend source kept as upstream_source (A-39)", async () => {
  // The live answer says the City sandbox is the mock: source stays "live", upstream_source is "mock".
  const fc = { type: "FeatureCollection", source: "mock", features: [], summary: { count: 0, median_hours_to_resolve: null } };
  setup(async () => respond(fc));
  const out = await api.resolved();
  assert.equal(out.source, "live");
  assert.equal(out.upstream_source, "mock");
});
