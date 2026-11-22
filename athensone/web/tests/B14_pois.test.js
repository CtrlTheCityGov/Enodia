// B14 tests: api.pois(), the official POI layer. Offline, no server, no browser.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const MOCK_DIR = path.join(here, "..", "mock");
const api = await import("../js/api.js");

const readMock = (name) => JSON.parse(readFileSync(path.join(MOCK_DIR, name), "utf8"));
const respond = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });

function fakeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
    clear: () => m.clear(),
  };
}

// Fake fetch: mock/ files come from disk (404 if missing), /api/ goes to `live`. Calls are recorded.
function makeFetch(live) {
  const calls = [];
  const f = async (url, opts = {}) => {
    calls.push({ url: String(url), opts });
    const u = String(url);
    if (u.includes("/api/")) return live(u, opts);
    const file = u.split("?")[0].split("/").pop();
    try { return respond(readMock(file)); } catch { return respond({}, 404); }
  };
  f.calls = calls;
  return f;
}

function setup(fetchFn) {
  api.configure({ fetch: fetchFn, storage: fakeStorage(), base: "", mockBase: "mock/", timeoutMs: 5000 });
}

// A 200 live answer is returned and marked "live"; the path is /api/map/pois.
test("pois: live answer marked live", async () => {
  const fc = { type: "FeatureCollection", features: [] };
  const f = makeFetch(async () => respond(fc));
  setup(f);
  const out = await api.pois({ bbox: [23.72, 37.97, 23.74, 37.98], categories: ["library"] });
  assert.equal(out.source, "live");
  assert.ok(new URL(f.calls[0].url, "http://x").pathname.startsWith("/api/map/pois"));
});

// Fetch rejects: answer comes from mock/pois.geojson, 3 official features, marked "mock".
test("pois: offline falls back to pois.geojson", async () => {
  setup(makeFetch(async () => { throw new TypeError("network down"); }));
  const out = await api.pois();
  assert.equal(out.source, "mock");
  assert.equal(out.features.length, 3);
  assert.ok(out.features.every((f) => f.properties.official === true));
});
