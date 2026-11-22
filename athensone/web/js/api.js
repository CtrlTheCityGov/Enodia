// api.js: the only door to the backend (SPEC «Αρχιτεκτονική», «Offline fallback» 3–4, card B1).
//
// Every read tries, in this order (SPEC «Offline fallback» 3):
//   1. live:  our backend under /api/map/… (A-33), 5 s timeout, cookie identity only (A-34)
//   2. cache: the last good live answer for the same URL, kept in localStorage
//      (not for stoaAsk and routing: their request holds the user's question and position, A-38)
//   3. mock:  the snapshot file in web/mock/
// and resolves to the SPEC shape plus a top-level `source: "live" | "cache" | "mock"`.
// Writes (sendReport, redeem) never fall back to fake data.
//
// No DOM and no maplibregl here, and nothing runs at import time except creating `status`,
// so Node can import this file in tests. main.js passes this module to the UI as `ctx.api` (A-35).

// ---------- settings ----------

const defaults = {
  fetch: null,      // null = the browser's fetch, looked up at call time
  storage: null,    // null = the browser's localStorage, looked up at call time
  base: "",         // "" = same origin as the page (card B1)
  mockBase: "mock/", // relative to web/citizen.html (SPEC folder layout)
  timeoutMs: 5000,  // card B1: "a 5 s timeout"
};
let settings = { ...defaults };

// Prefix of our localStorage keys, so they don't clash with other modules. Our own choice.
const CACHE_PREFIX = "athensone.api:";

// Card B1 wording, verbatim.
const STOA_REFUSAL = "Δεν βρήκα τεκμηριωμένα στοιχεία για αυτό.";
const OFFLINE_ROUTE_REASON = "Χωρίς σύνδεση: ευθεία γραμμή, χωρίς υπολογισμό εμποδίων";

// For tests and for main.js. Starts a fresh session: forgets which keys were offline.
export function configure(options = {}) {
  settings = { ...defaults, ...options };
  lastSource.clear();
}

function getFetch() {
  return settings.fetch || globalThis.fetch.bind(globalThis);
}

function getStorage() {
  if (settings.storage) return settings.storage;
  try {
    return globalThis.localStorage || null;
  } catch {
    return null; // some browsers throw when storage is disabled
  }
}

// ---------- status: drives the «Offline λειτουργία» badge (SPEC «Offline fallback» 4) ----------

// Fires a "source" event with detail {key, source} after every answer.
export const status = new EventTarget();

// key -> source of the latest answer for that key. The key is the contract name
// ("works", "env", ...), not the URL, so panning the map to a new bbox can't leave
// an old bbox stuck as "offline".
const lastSource = new Map();

// Files that are mock-only by design (access is pre-downloaded, SPEC «Εξωτερικές πηγές»;
// base is the offline basemap). They report "mock" but don't switch the badge on.
const STATIC_KEYS = new Set(["access", "base"]);

function report(key, source) {
  if (!STATIC_KEYS.has(key)) lastSource.set(key, source);
  status.dispatchEvent(new CustomEvent("source", { detail: { key, source } }));
}

// True while the latest answer of any key is not live.
export function isOffline() {
  for (const source of lastSource.values()) if (source !== "live") return true;
  return false;
}

// ---------- errors ----------

// Thrown by sendReport when the backend can't be reached; ui/report.js (B6) queues the report.
export class OfflineError extends Error {
  constructor(message = "offline") {
    super(message);
    this.name = "OfflineError";
  }
}

// Thrown by sendReport when the server answered and said no (a 4xx other than 404: daily cap,
// bad photo, ...). Not offline: the caller shows the reason instead of queueing (A-38).
export class RejectedError extends Error {
  constructor(status, detail) {
    super(`rejected: HTTP ${status}`);
    this.name = "RejectedError";
    this.status = status;   // the HTTP status, e.g. 429
    this.detail = detail;   // the server's `detail` (FastAPI's error field), or null if none
  }
}

// A non-2xx answer from liveJson, with the status and the server's `detail`.
class HttpError extends Error {
  constructor(status, detail) {
    super(`HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

// A-38: a 4xx other than 404 is the server rejecting the request. Everything else that fails
// (network error, timeout, 404 = endpoint not merged yet, 5xx) counts as offline.
function isRejection(err) {
  return err instanceof HttpError && err.status >= 400 && err.status < 500 && err.status !== 404;
}

// ---------- low-level helpers ----------

// One live request. Resolves to the parsed JSON body; rejects on a network error, a timeout
// or any non-2xx status (a 404 means the endpoint isn't merged yet: card B1).
async function liveJson(path, init = {}) {
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      if (controller) controller.abort();
      reject(new Error("timeout"));
    }, settings.timeoutMs);
  });
  const request = (async () => {
    const res = await getFetch()(settings.base + path, {
      ...init,
      credentials: "same-origin", // the ao_token cookie is the identity (A-34)
      signal: controller ? controller.signal : undefined,
    });
    if (!res.ok) {
      let detail = null;
      try {
        const body = await res.json();
        if (body && body.detail !== undefined) detail = body.detail;
      } catch {
        // no JSON body: detail stays null
      }
      throw new HttpError(res.status, detail);
    }
    return res.json();
  })();
  try {
    return await Promise.race([request, timeout]);
  } finally {
    clearTimeout(timer);
    request.catch(() => {}); // the loser of the race must not raise an unhandled rejection
  }
}

async function mockJson(file) {
  const res = await getFetch()(settings.mockBase + file);
  if (!res.ok) throw new Error(`mock ${file}: HTTP ${res.status}`);
  return res.json();
}

function readCache(cacheKey) {
  const storage = getStorage();
  if (!storage) return null;
  try {
    const text = storage.getItem(CACHE_PREFIX + cacheKey);
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
}

function writeCache(cacheKey, data) {
  const storage = getStorage();
  if (!storage) return;
  try {
    storage.setItem(CACHE_PREFIX + cacheKey, JSON.stringify(data));
  } catch {
    // storage full or disabled: the live answer still goes to the caller
  }
}

// Builds "?a=1&b=2" from the defined values. bbox arrays go out as minLon,minLat,maxLon,maxLat (SPEC).
function query(params) {
  const parts = [];
  for (const [name, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    const text = Array.isArray(value) ? value.join(",") : String(value);
    parts.push(`${name}=${encodeURIComponent(text)}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

function postJson(body) {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

// live -> cache -> mock for one read.
//   key:      contract name, for the status events
//   path:     live URL path + query; also the cache key
//   init:     fetch options (POST body)
//   fallback: async () => the mock answer (without `source`)
//   cache:    false = skip the cache step entirely (stoaAsk, routing: A-38)
async function read(key, path, init, fallback, { cache = true } = {}) {
  try {
    const data = await liveJson(path, init);
    if (cache) writeCache(path, data);
    report(key, "live");
    return { ...data, source: "live" };
  } catch {
    // fall through to the cache
  }
  const cached = cache ? readCache(path) : null;
  if (cached) {
    report(key, "cache");
    return { ...cached, source: "cache" };
  }
  const data = await fallback();
  report(key, "mock");
  return { ...data, source: "mock" };
}

// ---------- reads (SPEC «Backend contracts», paths per A-33) ----------

// bbox = [minLon, minLat, maxLon, maxLat] or { bbox }. Mock answers are the whole snapshot, not cut to bbox.
export function env(bboxOrOpts) {
  const bbox = bboxOrOpts && typeof bboxOrOpts === "object" && !Array.isArray(bboxOrOpts) ? bboxOrOpts.bbox : bboxOrOpts;
  return read("env", `/api/map/env${query({ bbox })}`, undefined, () => mockJson("env.json"));
}

export function works({ bbox, status: workStatus } = {}) {
  return read("works", `/api/map/works${query({ bbox, status: workStatus })}`, undefined,
    () => mockJson("works.geojson"));
}

export function transit(bboxOrOpts) {
  const bbox = bboxOrOpts && typeof bboxOrOpts === "object" && !Array.isArray(bboxOrOpts) ? bboxOrOpts.bbox : bboxOrOpts;
  return read("transit", `/api/map/transit${query({ bbox })}`, undefined, () => mockJson("transit.geojson"));
}

// On-duty pharmacies and hospitals; date = "YYYY-MM-DD" or { date }.
export function health(dateOrOpts) {
  const date = dateOrOpts && typeof dateOrOpts === "object" ? dateOrOpts.date : dateOrOpts;
  return read("health", `/api/map/health${query({ date })}`, undefined, () => mockJson("health.geojson"));
}

export function reports({ bbox, since } = {}) {
  return read("reports", `/api/map/reports${query({ bbox, since })}`, undefined,
    () => mockJson("reports.geojson"));
}

// The SPEC's ?user_id= is not sent: the backend reads the ao_token cookie (A-34).
export function points() {
  return read("points", "/api/map/points", undefined, () => mockJson("points.json"));
}

// B13: the official registry service for a sandbox report category. Cached like other reads (the registry is
// stable). Offline: that category's entry of mock/services.json, or { category, service: null }.
export function serviceFor(category) {
  return read("service:" + category, `/api/map/services${query({ category })}`, undefined, async () => {
    const all = await mockJson("services.json");
    return (all && all[category]) || { category, service: null };
  });
}

export function transitArrivals(stopCode) {
  return liveJson(`/api/map/transit/arrivals${query({ stop_code: stopCode })}`);
}

export function coolSpots(lat, lng) {
  return liveJson(`/api/map/cool-spots${query({ lat, lng })}`);
}

export function pointsLeaderboard() {
  return liveJson("/api/map/points/leaderboard");
}

export function worksLookup(ada) {
  return liveJson(`/api/map/works/lookup${query({ ada })}`);
}

// Neural Greek/English TTS via backend POST /api/tts (returns {ok, blob, voice, lang, provider}).
export async function tts({ text, lang = null, voice = null } = {}) {
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      controller?.abort();
      reject(new Error("timeout"));
    }, Math.max(settings.timeoutMs, 12000));
  });
  try {
    const res = await Promise.race([
      getFetch()(`${settings.base}/api/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang, voice }),
        credentials: "same-origin",
        signal: controller?.signal,
      }),
      timeout,
    ]);
    if (!res.ok) return { ok: false, status: res.status };
    const blob = await res.blob();
    return {
      ok: true,
      blob,
      voice: res.headers?.get?.("X-TTS-Voice") || null,
      lang: res.headers?.get?.("X-TTS-Lang") || lang,
      provider: res.headers?.get?.("X-TTS-Provider") || "edge-tts",
    };
  } catch {
    return { ok: false, error: "offline" };
  } finally {
    clearTimeout(timer);
  }
}

// center = [lon, lat]; history = earlier turns of the chat. Accepts (question, center, history) or ({question, center, history}).
// Never cached: question and center would sit on the device (A-38). Offline -> mock/stoa.json.
export function stoaAsk(questionOrOpts, center, history = []) {
  const isObj = questionOrOpts && typeof questionOrOpts === "object" && !Array.isArray(questionOrOpts);
  const question = isObj ? questionOrOpts.question : questionOrOpts;
  const c = isObj ? questionOrOpts.center : center;
  const h = isObj ? (questionOrOpts.history ?? []) : history;
  return read("stoa", "/api/map/stoa_ask", postJson({ question, center: c, history: h }),
    () => stoaFromMock(question), { cache: false });
}

// from, to = [lon, lat]; profile = "wheelchair" | "stroller" | "cool". Accepts (from, to, profile) or ({from, to, profile}).
// Never cached: from and to are the user's position and destination (A-38). Offline -> straight line.
export function routing(fromOrOpts, to, profile) {
  const isObj = fromOrOpts && typeof fromOrOpts === "object" && !Array.isArray(fromOrOpts);
  const f = isObj ? fromOrOpts.from : fromOrOpts;
  const t = isObj ? fromOrOpts.to : to;
  const p = isObj ? fromOrOpts.profile : profile;
  return read("routing", "/api/map/routing", postJson({ from: f, to: t, profile: p }),
    async () => straightLine(f, t), { cache: false });
}

// Mock-only files (card B1): always source "mock".
export async function access() {
  const data = await mockJson("access.geojson");
  report("access", "mock");
  return { ...data, source: "mock" };
}

export async function base() {
  const data = await mockJson("base.geojson");
  report("base", "mock");
  return { ...data, source: "mock" };
}

// ---------- writes: no fake answers ----------

// fields = {category, lon, lat, note, work_id?, photo?} or a FormData (SPEC: multipart). Rejects with
// OfflineError when the backend can't be reached; the caller queues it (SPEC «Offline fallback» 5).
// Rejects with RejectedError {status, detail} when the server says no (A-38); the caller shows why.
export async function sendReport(fields) {
  let form;
  if (typeof FormData !== "undefined" && fields instanceof FormData) {
    form = fields;
    form.delete("user_id"); // identity is the cookie only (A-34)
  } else {
    form = new FormData();
    for (const [name, value] of Object.entries(fields || {})) {
      if (value === undefined || value === null) continue;
      if (name === "user_id") continue; // identity is the cookie only (A-34)
      form.append(name, value instanceof Blob ? value : String(value));
    }
  }
  let data;
  try {
    data = await liveJson("/api/map/reports", { method: "POST", body: form });
  } catch (err) {
    if (isRejection(err)) throw new RejectedError(err.status, err.detail);
    throw new OfflineError();
  }
  report("sendReport", "live");
  return { ...data, source: "live" };
}

// Offline the answer is {ok: false, error: "offline"}: a voucher is never invented.
// Rejected by the server (A-38): {ok: false, error: "rejected", status, detail}.
export async function redeem(rewardId) {
  let data;
  try {
    data = await liveJson("/api/map/points/redeem", postJson({ reward_id: rewardId }));
  } catch (err) {
    if (isRejection(err)) return { ok: false, error: "rejected", status: err.status, detail: err.detail };
    return { ok: false, error: "offline" };
  }
  report("redeem", "live");
  return { ...data, source: "live" };
}

// ---------- mock fallbacks without a 1:1 file ----------

// Lower case, no accents, no punctuation, single spaces: «Ποιο φαρμακείο;» == «ποιο φαρμακειο».
function normalizeQuestion(text) {
  return String(text || "")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")       // accents (τόνοι, διαλυτικά)
    .toLowerCase()
    .replace(/ς/g, "σ")           // final sigma
    .replace(/[^\p{L}\p{N}]+/gu, " ") // ; ? , . and the Greek question mark
    .trim();
}

async function stoaFromMock(question) {
  const entries = await mockJson("stoa.json"); // a top-level array (mock/README.md)
  const wanted = normalizeQuestion(question);
  const hit = entries.find((e) => normalizeQuestion(e.question) === wanted);
  if (hit) return { answer_md: hit.answer_md, citations: hit.citations || [] };
  return { answer_md: STOA_REFUSAL, citations: [] };
}

// Great-circle distance in metres. Earth radius 6 371 000 m (mean radius, IUGG; sure).
function haversineM([lon1, lat1], [lon2, lat2]) {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(a));
}

// Offline route: a straight walking line. duration_s is null (unknown): no speed is assumed.
function straightLine(from, to) {
  return {
    geometry: { type: "LineString", coordinates: [from, to] },
    distance_m: Math.round(haversineM(from, to)),
    duration_s: null,
    legs: [{ mode: "walk" }],
    reasons: [{ text: OFFLINE_ROUTE_REASON, layer: null, feature_id: null }],
  };
}
