import test from "node:test";
import assert from "node:assert/strict";

import {
  CATEGORIES,
  buildForm,
  submitReport,
  flushQueue,
  getQueue,
} from "../js/ui/report.js";

function makeFakeStorage() {
  const store = new Map();
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
    removeItem(key) {
      store.delete(key);
    },
  };
}

test("test_js_categories_in_spec_order", () => {
  // Verify CATEGORIES matches the 5 SPEC categories and Greek labels in exact order.
  assert.equal(CATEGORIES.length, 5);
  assert.deepEqual(
    CATEGORIES.map((c) => c.id),
    ["congestion", "incident", "obstacle", "damage", "work_progress"],
  );
  assert.deepEqual(
    CATEGORIES.map((c) => c.label.toLowerCase()),
    ["συμφόρηση", "συμβάν", "εμπόδιο", "ζημιά", "πρόοδος έργου"],
  );
});

test("test_js_build_form", () => {
  // Verify buildForm populates category, lon, lat, note, work_id and omits photo when none is given.
  const form = buildForm({
    category: "work_progress",
    lngLat: { lng: 23.7348, lat: 37.9755 },
    note: "Πρόοδος εργασιών",
    photo: null,
    work_id: "W-SEED-001",
  });
  assert.ok(form instanceof FormData);
  assert.equal(form.get("category"), "work_progress");
  assert.equal(form.get("lon"), "23.7348");
  assert.equal(form.get("lat"), "37.9755");
  assert.equal(form.get("note"), "Πρόοδος εργασιών");
  assert.equal(form.get("work_id"), "W-SEED-001");
  assert.equal(form.has("photo"), false);
});

test("test_js_offline_queue_flush", async () => {
  // Verify failed submissions queue into localStorage and flush once when the API recovers.
  let shouldFail = true;
  const sent = [];
  const fakeApi = {
    async postReport(form) {
      if (shouldFail) {
        throw new Error("offline");
      }
      sent.push(form);
      return {
        id: "MR-1",
        photo_url_blurred: null,
        points_awarded: 5,
        blur: { faces: 0, plates: 0 },
      };
    },
  };
  const storage = makeFakeStorage();

  const first = await submitReport(
    {
      category: "incident",
      lngLat: { lng: 23.7348, lat: 37.9755 },
      note: "Λακκούβα",
    },
    fakeApi,
    storage,
  );
  assert.equal(first.queued, true);
  assert.equal(sent.length, 0);
  assert.equal(getQueue(storage).length, 1);

  shouldFail = false;
  await flushQueue(fakeApi, storage);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].get("category"), "incident");
  assert.equal(sent[0].get("lon"), "23.7348");
  assert.equal(sent[0].get("lat"), "37.9755");
  assert.equal(sent[0].get("note"), "Λακκούβα");
  assert.equal(getQueue(storage).length, 0);

  await flushQueue(fakeApi, storage);
  assert.equal(sent.length, 1);
});
