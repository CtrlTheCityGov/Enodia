// B1 fix round tests: no cached Stoa/route (privacy), rejected vs offline (A-38). Offline, no server, no browser.
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

// Fake localStorage that also lets a test dump every key and value.
function fakeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
    clear: () => m.clear(),
    dump: () => [...m.entries()].flat().join("\n"),
  };
}

// Fake fetch: files under mock/ come from disk; /api/ calls go to `live(url, opts)`.
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
  const storage = fakeStorage();
  api.configure({ fetch: fetchFn, storage, base: "", mockBase: "mock/", timeoutMs: 5000 });
  return storage;
}

const FROM = [23.7311, 37.9712];
const TO = [23.7422, 37.9833];
const liveRoute = { geometry: { type: "LineString", coordinates: [FROM, TO] }, distance_m: 1, duration_s: 1, legs: [{ mode: "walk" }], reasons: [] };

// A live Stoa answer is not kept: when fetch then fails, the answer comes from mock, not cache.
test("test_stoa_not_cached", async () => {
  let ok = true;
  const f = makeFetch(async () => { if (!ok) throw new Error("down"); return respond({ answer_md: "live", citations: [] }); });
  setup(f);
  const first = await api.stoaAsk("ποιο φαρμακείο εφημερεύει", [23.73, 37.97], []);
  assert.equal(first.source, "live");
  ok = false;
  const second = await api.stoaAsk("ποιο φαρμακείο εφημερεύει", [23.73, 37.97], []);
  assert.equal(second.source, "mock");
});

// A live route is not kept: when fetch then fails, the answer is the mock straight line, not cache.
test("test_routing_not_cached", async () => {
  let ok = true;
  const f = makeFetch(async () => { if (!ok) throw new Error("down"); return respond(liveRoute); });
  setup(f);
  const first = await api.routing(FROM, TO, "wheelchair");
  assert.equal(first.source, "live");
  ok = false;
  const second = await api.routing(FROM, TO, "wheelchair");
  assert.equal(second.source, "mock");
  assert.equal(second.geometry.type, "LineString");
});

// Every function called once live with distinctive coordinates and question: storage holds none of them.
test("test_no_user_location_or_question_in_storage", async () => {
  const question = "ΜΟΝΑΔΙΚΗ ερώτηση xyzzy 12345";
  const center = [23.123456, 37.654321];
  const from = [23.111111, 37.222222];
  const to = [23.333333, 37.444444];
  const f = makeFetch(async (u) => {
    if (u.includes("stoa_ask")) return respond({ answer_md: "a", citations: [] });
    if (u.includes("routing")) return respond(liveRoute);
    if (u.includes("redeem")) return respond({ ok: true });
    if (u.includes("/reports") && !u.includes("bbox")) return respond({ ok: true });
    return respond({ type: "FeatureCollection", features: [] });
  });
  const storage = setup(f);
  const bbox = [23.72, 37.97, 23.74, 37.98];
  await api.env(bbox);
  await api.works({ bbox, status: "in_progress" });
  await api.transit(bbox);
  await api.health("2026-11-21");
  await api.reports({ bbox, since: "2026-11-01" });
  await api.points();
  await api.stoaAsk(question, center, [{ role: "user", text: question }]);
  await api.routing(from, to, "wheelchair");
  await api.redeem("r1").catch(() => {});
  await api.sendReport({ category: "pothole", lon: 23.555555, lat: 37.555555, note: "n" }).catch(() => {});
  const all = storage.dump();
  for (const secret of ["xyzzy", "12345", "23.123456", "37.654321", "23.111111", "37.222222", "23.333333", "37.444444"]) {
    assert.ok(!all.includes(secret), `storage must not contain ${secret}`);
  }
});

// 429 on sendReport is a rejection with status and detail, not an offline error.
test("test_send_report_429_rejected", async () => {
  setup(makeFetch(async () => respond({ detail: "όριο αναφορών" }, 429)));
  await assert.rejects(
    () => api.sendReport({ category: "pothole", lon: 23.7, lat: 37.9, note: "x" }),
    (err) => {
      assert.ok(err instanceof api.RejectedError);
      assert.ok(!(err instanceof api.OfflineError));
      assert.equal(err.status, 429);
      assert.equal(err.detail, "όριο αναφορών");
      return true;
    },
  );
});

// 500 on sendReport counts as offline.
test("test_send_report_500_offline", async () => {
  setup(makeFetch(async () => respond({ detail: "boom" }, 500)));
  await assert.rejects(() => api.sendReport({ category: "pothole", lon: 23.7, lat: 37.9, note: "x" }), api.OfflineError);
});

// 404 on sendReport counts as offline (endpoint not merged yet).
test("test_send_report_404_offline", async () => {
  setup(makeFetch(async () => respond({ detail: "Not Found" }, 404)));
  await assert.rejects(() => api.sendReport({ category: "pothole", lon: 23.7, lat: 37.9, note: "x" }), api.OfflineError);
});

// 400 on redeem resolves {ok:false, error:"rejected", status, detail}.
test("test_redeem_400_rejected", async () => {
  setup(makeFetch(async () => respond({ detail: "όχι αρκετοί πόντοι" }, 400)));
  const out = await api.redeem("r1");
  assert.equal(out.ok, false);
  assert.equal(out.error, "rejected");
  assert.equal(out.status, 400);
  assert.equal(out.detail, "όχι αρκετοί πόντοι");
});
