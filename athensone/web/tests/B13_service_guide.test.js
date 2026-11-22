// B13 tests: api.serviceFor and web/mock/services.json. Offline, no server, no browser.
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

// Fake fetch: mock/ files come from disk; /api/ calls go to `live`. Calls are recorded.
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

const SANDBOX = ["pothole", "streetlight", "garbage", "bulky_waste", "graffiti", "tree", "sidewalk",
  "abandoned_vehicle", "noise", "stray_animals", "water_leak", "other"];

// A 200 answer is returned and marked live; the URL is /api/map/services?category=...
test("serviceFor: live answer marked live", async () => {
  const body = { category: "bulky_waste", label_el: "Ογκώδη", query: "q", service: { id: "s1", title: "T" }, source: "sandbox" };
  const f = makeFetch(async () => respond(body));
  setup(f);
  const out = await api.serviceFor("bulky_waste");
  assert.equal(out.source, "live");
  assert.ok(f.calls[0].url.includes("/api/map/services?category=bulky_waste"));
});

// Fetch rejects and nothing is cached: the entry of services.json for that category comes back.
test("serviceFor: offline falls back to mock file entry", async () => {
  setup(makeFetch(async () => { throw new TypeError("network down"); }));
  const out = await api.serviceFor("pothole");
  assert.equal(out.source, "mock");
  assert.equal(out.category, "pothole");
});

// The mock file has all 12 categories, each labelled mock; «other» has no service.
test("services.json has all 12 categories", () => {
  const data = readMock("services.json");
  assert.deepEqual(Object.keys(data).sort(), [...SANDBOX].sort());
  for (const k of SANDBOX) assert.equal(data[k].source, "mock");
  assert.strictEqual(data.other.service, null);
});
