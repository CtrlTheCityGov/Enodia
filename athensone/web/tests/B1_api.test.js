// B1 tests: web/js/api.js, the only door to the backend. Offline, no server, no browser.
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const MOCK_DIR = path.join(here, "..", "mock");
const api = await import("../js/api.js");

const readMock = (name) => JSON.parse(readFileSync(path.join(MOCK_DIR, name), "utf8"));
const respond = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });

// Fake localStorage.
function fakeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
    clear: () => m.clear(),
  };
}

// Fake fetch: files under mock/ are served from disk; /api/ calls go to `live(url, opts)`.
// Every call is recorded in `calls`.
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
const failing = () => makeFetch(async () => { throw new TypeError("network down"); });

function setup(fetchFn, extra = {}) {
  const storage = fakeStorage();
  api.configure({ fetch: fetchFn, storage, base: "", mockBase: "mock/", timeoutMs: 5000, ...extra });
  return storage;
}

const BBOX = [23.72, 37.97, 23.74, 37.98];
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };

// A live works answer returns the same object plus source "live"; URL is /api/map/works.
test("test_live_answer_has_source_live", async () => {
  const fc = { type: "FeatureCollection", features: [{ type: "Feature", properties: { id: "w1" }, geometry: { type: "Point", coordinates: [23.73, 37.97] } }] };
  const f = makeFetch(async () => respond(fc));
  setup(f);
  const out = await api.works({ bbox: BBOX });
  assert.equal(out.source, "live");
  assert.deepEqual(out.features, fc.features);
  assert.equal(out.type, "FeatureCollection");
  assert.ok(f.calls[0].url.includes("/api/map/works"));
});

// One live call, then fetch fails: second call returns the first answer marked "cache".
test("test_live_answer_cached", async () => {
  const fc = { type: "FeatureCollection", features: [{ type: "Feature", properties: { id: "live-1" }, geometry: null }] };
  let ok = true;
  const f = makeFetch(async () => { if (!ok) throw new Error("down"); return respond(fc); });
  setup(f);
  const first = await api.works({ bbox: BBOX });
  assert.equal(first.source, "live");
  ok = false;
  const second = await api.works({ bbox: BBOX });
  assert.equal(second.source, "cache");
  assert.deepEqual(second.features, fc.features);
});

// Fetch fails and storage is empty: answer comes from mock/works.geojson, cut to the bbox (B17: a LineString is kept
// when any vertex is inside).
test("test_no_cache_falls_back_to_mock", async () => {
  setup(failing());
  const out = await api.works({ bbox: BBOX });
  assert.equal(out.source, "mock");
  const [w, s, e, n] = BBOX;
  const inside = ([x, y]) => x >= w && x <= e && y >= s && y <= n;
  const expected = readMock("works.geojson").features.filter((f) => f.geometry.type !== "LineString"
    || f.geometry.coordinates.some(inside));
  assert.deepEqual(out.features, expected);
});

// A 404 (endpoint not merged yet) is a failure: its body must never reach the caller.
test("test_404_counts_as_failure", async () => {
  const f = makeFetch(async () => respond({ detail: "Not Found", marker: "BODY404" }, 404));
  setup(f);
  const out = await api.works({ bbox: BBOX });
  assert.ok(out.source === "cache" || out.source === "mock");
  assert.equal(JSON.stringify(out).includes("BODY404"), false);
});

// Fetch never resolves; after 5 s of mocked time the call falls back instead of hanging.
test("test_timeout_5s", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const f = makeFetch(() => new Promise(() => {}));
    setup(f);
    let done = false;
    const p = api.works({ bbox: BBOX }).then((v) => { done = true; return v; });
    await flush();
    assert.equal(done, false);
    mock.timers.tick(5000);
    const out = await p;
    assert.equal(out.source, "mock");
  } finally {
    mock.timers.reset();
  }
});

// bbox goes out as bbox=minLon,minLat,maxLon,maxLat; status as status=...
test("test_query_params_spec_format", async () => {
  const f = makeFetch(async () => respond({ type: "FeatureCollection", features: [] }));
  setup(f);
  await api.env(BBOX);
  await api.works({ status: "in_progress" });
  const urls = f.calls.map((c) => decodeURIComponent(c.url));
  assert.ok(urls.some((u) => u.includes("/api/map/env") && u.includes("bbox=23.72,37.97,23.74,37.98")), urls.join("\n"));
  assert.ok(urls.some((u) => u.includes("/api/map/works") && u.includes("status=in_progress")), urls.join("\n"));
});

// Every function called: no URL has user_id or the cookie value; credentials are same-origin.
test("test_no_user_id_in_urls", async () => {
  const SECRET = "SECRETCOOKIE123";
  globalThis.document = { cookie: `ao_token=${SECRET}` };
  try {
    const f = makeFetch(async () => respond({ type: "FeatureCollection", features: [], ok: true }));
    setup(f);
    await api.env(BBOX);
    await api.works({ bbox: BBOX, status: "in_progress" });
    await api.transit(BBOX);
    await api.health("2026-11-21");
    await api.reports({ bbox: BBOX, since: "2026-11-01T00:00:00Z" });
    await api.sendReport({ category: "damage", lon: 23.73, lat: 37.97, note: "x" }).catch(() => {});
    await api.points();
    await api.redeem("r1");
    await api.stoaAsk("ποια έργα;", [23.73, 37.97], []);
    await api.routing([23.72, 37.97], [23.73, 37.98], "wheelchair");
    await api.access();
    await api.base();
    assert.ok(f.calls.length >= 10);
    for (const c of f.calls) {
      assert.equal(c.url.includes("user_id"), false, c.url);
      assert.equal(c.url.includes(SECRET), false, c.url);
      if (c.url.includes("/api/")) assert.equal(c.opts.credentials, "same-origin", c.url);
    }
  } finally {
    delete globalThis.document;
  }
});

const pharmacyQ = "ποιο φαρμακειο εφημερευει κοντα μου";

// Offline, accent-/case-insensitive match returns the stoa.json pharmacy answer with citations.
test("test_stoa_mock_match_accent_insensitive", async () => {
  setup(failing());
  const out = await api.stoaAsk(pharmacyQ, [23.73, 37.97], []);
  const expected = readMock("stoa.json").find((e) => e.question.startsWith("Ποιο φαρμακείο"));
  assert.equal(out.source, "mock");
  assert.equal(out.answer_md, expected.answer_md);
  assert.deepEqual(out.citations, expected.citations);
});

// Offline unknown question: the refusal text and no citations.
test("test_stoa_mock_no_match_refuses", async () => {
  setup(failing());
  const out = await api.stoaAsk("Ποια είναι η πρωτεύουσα της Γαλλίας;", [23.73, 37.97], []);
  assert.ok(out.answer_md.includes("Δεν βρήκα τεκμηριωμένα στοιχεία για αυτό."));
  assert.deepEqual(out.citations, []);
});

// Offline routing: straight LineString from -> to, one walk leg, the offline reason, source mock.
test("test_routing_offline_straight_line", async () => {
  setup(failing());
  const from = [23.72, 37.97], to = [23.73, 37.98];
  const out = await api.routing(from, to, "wheelchair");
  assert.equal(out.source, "mock");
  assert.equal(out.geometry.type, "LineString");
  assert.deepEqual(out.geometry.coordinates[0], from);
  assert.deepEqual(out.geometry.coordinates.at(-1), to);
  assert.deepEqual(out.legs, [{ mode: "walk" }]);
  assert.ok(out.reasons.some((r) => r.text === "Χωρίς σύνδεση: ευθεία γραμμή, χωρίς υπολογισμό εμποδίων"));
});

// Offline redeem is not faked: ok false, error offline, no voucher.
test("test_redeem_offline_not_faked", async () => {
  setup(failing());
  const out = await api.redeem("r1");
  assert.equal(out.ok, false);
  assert.equal(out.error, "offline");
  assert.equal(out.voucher_code, undefined);
});

// Offline sendReport rejects with OfflineError (the queue lives in ui/report.js).
test("test_send_report_offline_throws", async () => {
  setup(failing());
  assert.equal(typeof api.OfflineError, "function");
  await assert.rejects(
    api.sendReport({ category: "damage", lon: 23.73, lat: 37.97, note: "x" }),
    (e) => e instanceof api.OfflineError,
  );
});

// One live call and one mock call give two "source" events; isOffline() true, then false after a live call for that key.
test("test_status_events_and_is_offline", async () => {
  let live = true;
  const f = makeFetch(async () => { if (!live) throw new Error("down"); return respond({ type: "FeatureCollection", features: [] }); });
  setup(f);
  const events = [];
  const on = (e) => events.push(e.detail);
  api.status.addEventListener("source", on);
  try {
    await api.works({ bbox: BBOX });          // live
    assert.equal(api.isOffline(), false);
    live = false;
    await api.env(BBOX);                      // mock
    assert.equal(events.length, 2);
    assert.equal(events[0].source, "live");
    assert.equal(events[1].source, "mock");
    assert.equal(api.isOffline(), true);
    live = true;
    await api.env(BBOX);                      // live again for that key
    assert.equal(api.isOffline(), false);
  } finally {
    api.status.removeEventListener("source", on);
  }
});

// Importing in Node needs no DOM and leaves globals untouched.
test("test_import_has_no_dom", async () => {
  const before = new Set(Object.getOwnPropertyNames(globalThis));
  await import("../js/api.js?fresh-import");
  const after = Object.getOwnPropertyNames(globalThis);
  assert.deepEqual(after.filter((k) => !before.has(k)), []);
  assert.equal(typeof document, "undefined");
  assert.equal(typeof maplibregl, "undefined");
});
