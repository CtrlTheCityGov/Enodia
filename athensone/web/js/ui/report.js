// B6: the «+» report flow (SPEC F3, HUD «Κάτω αριστερά», «Offline fallback» 5;
// UI/UX upgrades #3/#4/#5/#6: macOS fold animations, auto-close + glass toast, instant quick-report).
// No DOM or maplibregl at import time (CLAUDE.md), so Node can test the pure parts; mount(ctx) builds the UI (A-35).

// The 5 categories in SPEC order with their Greek labels. Source: SPEC F3, TASKS_B.md B6. Certainty: verified.
export const CATEGORIES = [
  { id: "congestion", label: "Συμφόρηση", icon: "🚗" },
  { id: "incident", label: "Συμβάν", icon: "⚠️" },
  { id: "obstacle", label: "Εμπόδιο", icon: "🚧" },
  { id: "damage", label: "Ζημιά", icon: "🕳️" },
  { id: "work_progress", label: "Πρόοδος έργου", icon: "🏗️" },
];

// localStorage key of the offline queue. Our choice (no SPEC name). Certainty: n/a.
export const QUEUE_KEY = "ao_report_queue";

// Message while the photo is uploaded and blurred. Source: SPEC HUD «Κάτω αριστερά». Certainty: verified.
export const BLUR_MESSAGE = "Θολώνουμε πρόσωπα και πινακίδες…";

// Fold-close animation duration matching hud.css macos-fold (design default).
const FOLD_CLOSE_MS = 200;

// Multipart fields of POST /reports (SPEC «Backend contracts»): category, lon, lat, note, work_id?, photo?
export function buildForm({ category, lngLat, note = "", photo = null, work_id = null }) {
  const form = new FormData();
  form.append("category", category);
  form.append("lon", String(lngLat.lng));
  form.append("lat", String(lngLat.lat));
  form.append("note", note || "");
  if (work_id) form.append("work_id", work_id);
  if (photo) form.append("photo", photo);
  return form;
}

export function getQueue(storage) {
  try {
    const list = JSON.parse(storage.getItem(QUEUE_KEY) || "[]");
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function setQueue(storage, list) {
  if (list.length) storage.setItem(QUEUE_KEY, JSON.stringify(list));
  else storage.removeItem(QUEUE_KEY);
}

// api.js (B1) names the call sendReport; the B6 tests use postReport. Accept either (owner question in the report).
function send(api, form) {
  return api.postReport ? api.postReport(form) : api.sendReport(form);
}

// A 4xx answer means the report itself is wrong: queueing it would retry it forever.
function isRejected(err) {
  return typeof err?.status === "number" && err.status >= 400 && err.status < 500;
}

// Send one report; if the network is down, keep it in localStorage and return {queued: true}.
// The queue holds the text fields only: a photo can't be kept in localStorage, so it is dropped (owner question).
export async function submitReport(input, api, storage) {
  try {
    return { queued: false, result: await send(api, buildForm(input)) };
  } catch (err) {
    if (isRejected(err)) throw err;
    const { category, lngLat, note = "", work_id = null } = input;
    setQueue(storage, [...getQueue(storage), { category, lngLat: { lng: lngLat.lng, lat: lngLat.lat }, note, work_id }]);
    return { queued: true, photoDropped: Boolean(input.photo) };
  }
}

// Send queued reports in order, each once. Stops at the first network failure and keeps the rest.
let flushing = false;
export async function flushQueue(api, storage) {
  if (flushing) return [];
  flushing = true;
  const results = [];
  try {
    let list = getQueue(storage);
    while (list.length) {
      try {
        results.push(await send(api, buildForm(list[0])));
      } catch (err) {
        if (!isRejected(err)) break; // still offline: try again on the next `online`
      }
      list = list.slice(1);
      setQueue(storage, list);
    }
  } finally {
    flushing = false;
  }
  return results;
}

// ---------------------------------------------------------------- UI (browser only, called by main.js)

function el(tag, attrs = {}, text = "") {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text) node.textContent = text;
  return node;
}

function canAnimateFold() {
  return typeof window !== "undefined" && typeof window.requestAnimationFrame === "function";
}

function foldHide(node, timerRef) {
  if (timerRef.id !== null) {
    clearTimeout(timerRef.id);
    timerRef.id = null;
  }
  if (node.hidden) {
    node.classList?.remove("is-closing");
    return;
  }
  if (!canAnimateFold()) {
    node.classList?.remove("is-closing");
    node.hidden = true;
    return;
  }
  node.classList?.add("is-closing");
  timerRef.id = setTimeout(() => {
    timerRef.id = null;
    node.hidden = true;
    node.classList?.remove("is-closing");
  }, FOLD_CLOSE_MS);
}

function foldShow(node, timerRef) {
  if (timerRef.id !== null) {
    clearTimeout(timerRef.id);
    timerRef.id = null;
  }
  node.classList?.remove("is-closing");
  node.hidden = false;
}

// ctx = {map, api, root, container, bus} (DECISIONS.md A-35).
export function mount({ map, api, root, container, bus }) {
  root = container || root;
  const storage = window.localStorage;
  const state = { category: null, work_id: null, marker: null };
  const menuTimer = { id: null };
  const panelTimer = { id: null };

  const fab = el("button", { type: "button", class: "glass report-fab", "aria-label": "Νέα αναφορά",
    "aria-expanded": "false", "aria-controls": "report-menu" }, "+");
  const menu = el("div", { id: "report-menu", class: "glass report-menu", role: "menu", hidden: "" });
  for (const c of CATEGORIES) {
    const item = el("button", { type: "button", role: "menuitem", "data-category": c.id }, `${c.icon} ${c.label}`);
    item.addEventListener("click", () => openForm(c.id, null, null));
    menu.append(item);
  }

  const panel = el("form", { class: "glass report-panel", hidden: "", "aria-label": "Αναφορά" });
  const title = el("p", { class: "report-title" });
  const hint = el("p", { class: "report-hint" }, "Σύρετε την πινέζα στο σωστό σημείο.");
  const noteLabel = el("label", {}, "Σχόλιο (προαιρετικό)");
  const note = el("textarea", { name: "note", rows: "2", maxlength: "500" });
  noteLabel.append(note);
  const photoLabel = el("label", {}, "Φωτογραφία (προαιρετική)");
  const photo = el("input", { type: "file", name: "photo", accept: "image/*", capture: "environment" });
  photoLabel.append(photo);
  const status = el("p", { class: "report-status", role: "status", "aria-live": "polite" });
  const preview = el("img", { class: "report-preview", alt: "Η φωτογραφία με θολωμένα πρόσωπα και πινακίδες", hidden: "" });
  const sendBtn = el("button", { type: "submit" }, "Αποστολή");
  const cancelBtn = el("button", { type: "button" }, "Άκυρο");
  panel.append(title, hint, noteLabel, photoLabel, sendBtn, cancelBtn, status, preview);
  root.append(fab, menu, panel);

  function toggleMenu(open) {
    if (open) {
      foldShow(menu, menuTimer);
    } else {
      foldHide(menu, menuTimer);
    }
    fab.setAttribute("aria-expanded", String(open));
  }

  function closeForm(immediate = false) {
    if (immediate) {
      if (panelTimer.id !== null) {
        clearTimeout(panelTimer.id);
        panelTimer.id = null;
      }
      panel.classList?.remove("is-closing");
      panel.hidden = true;
    } else {
      foldHide(panel, panelTimer);
    }
    state.marker?.remove();
    state.marker = null;
  }

  function openForm(category, workId, lngLat) {
    toggleMenu(false);
    closeForm(true);
    state.category = category;
    state.work_id = workId;
    const label = CATEGORIES.find((c) => c.id === category)?.label || category;
    title.textContent = workId ? `${label} · έργο ${workId}` : label;
    note.value = "";
    photo.value = "";
    status.textContent = "";
    preview.hidden = true;
    sendBtn.disabled = false;
    state.marker = new window.maplibregl.Marker({ draggable: true })
      .setLngLat(lngLat || map.getCenter())
      .addTo(map);
    foldShow(panel, panelTimer);
    note.focus();
  }

  function earned(result) {
    if (result?.points_awarded > 0) {
      bus.dispatchEvent(new CustomEvent("points:earned", {
        detail: { delta: result.points_awarded, reason: "Αναφορά στον χάρτη" },
      }));
    }
  }

  function notifyToast(message, extra = {}) {
    bus?.dispatchEvent(new CustomEvent("toast:show", {
      detail: { message, durationMs: 3000, ...extra },
    }));
  }

  fab.addEventListener("click", () => toggleMenu(menu.hidden || menu.classList?.contains("is-closing")));
  root.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      toggleMenu(false);
      closeForm();
      fab.focus();
    }
  });
  cancelBtn.addEventListener("click", () => closeForm());

  panel.addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = photo.files?.[0] || null;
    const { lng: lon, lat } = state.marker.getLngLat();
    const input = { category: state.category, lngLat: { lng: lon, lat }, note: note.value,
      photo: file, work_id: state.work_id };
    sendBtn.disabled = true;
    status.textContent = file ? BLUR_MESSAGE : "Αποστολή…";
    try {
      const out = await submitReport(input, api, storage);
      if (out.queued) {
        const queuedMsg = out.photoDropped
          ? "Αναφορά αποθηκεύτηκε offline (χωρίς φωτογραφία) — θα σταλεί αυτόματα."
          : "Αναφορά αποθηκεύτηκε offline — θα σταλεί μόλις επανέλθει το δίκτυο.";
        note.value = "";
        photo.value = "";
        sendBtn.disabled = false;
        closeForm();
        bus.dispatchEvent(new CustomEvent("report:created", {
          detail: { id: `offline-${Date.now()}`, category: input.category, lon, lat },
        }));
        notifyToast(queuedMsg);
        return;
      }
      const r = out.result;
      const toastMsg = r.points_awarded > 0
        ? `Αναφορά καταχωρήθηκε · +${r.points_awarded} Πόντοι Γειτονιάς`
        : "Αναφορά καταχωρήθηκε";
      if (r.photo_url_blurred) {
        preview.src = r.photo_url_blurred; // only the backend's blurred copy is ever shown (SPEC «Privacy»)
      }
      // Reset form fields and smoothly fold-close the report window (UI/UX upgrade #5).
      note.value = "";
      photo.value = "";
      status.textContent = "";
      preview.hidden = true;
      sendBtn.disabled = false;
      closeForm();
      earned(r);
      // Shared report refresh event and payload: TASKS_B.md B11 (verified).
      bus.dispatchEvent(new CustomEvent("report:created", {
        detail: { id: r.id, category: input.category, lon, lat },
      }));
      notifyToast(toastMsg, r.photo_url_blurred ? { photo_url_blurred: r.photo_url_blurred } : {});
    } catch {
      status.textContent = "Η αναφορά δεν έγινε δεκτή. Ελέγξτε τα στοιχεία και δοκιμάστε ξανά.";
      sendBtn.disabled = false;
    }
  });

  // From the works popup «Ανέφερε πρόοδο» (A-35): {work_id?, lngLat?}
  bus.addEventListener("report:open", (e) => {
    const { work_id = null, lngLat = null } = e.detail || {};
    openForm("work_progress", work_id, lngLat);
  });

  // Instant 1-tap Waze-style "⚡ Αναφορά εδώ" from Navigation mode (UI/UX upgrade #6).
  bus.addEventListener("report:quick", async (e) => {
    const detail = e?.detail || {};
    const category = detail.category || "incident";
    const quickNote = detail.note || "";
    const pos = detail.lngLat || map?.getCenter?.();
    const lon = Number(pos?.lng ?? pos?.lon ?? (Array.isArray(pos) ? pos[0] : NaN));
    const lat = Number(pos?.lat ?? (Array.isArray(pos) ? pos[1] : NaN));
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) return;
    const label = quickNote || CATEGORIES.find((c) => c.id === category)?.label || "Αναφορά";
    try {
      const out = await submitReport(
        { category, lngLat: { lng: lon, lat }, note: quickNote, photo: null, work_id: null },
        api,
        storage,
      );
      if (out.queued) {
        bus.dispatchEvent(new CustomEvent("report:created", {
          detail: { id: `offline-${Date.now()}`, category, lon, lat },
        }));
        notifyToast(`⚡ ${label} · αποθηκεύτηκε offline`);
        return;
      }
      const r = out.result;
      earned(r);
      bus.dispatchEvent(new CustomEvent("report:created", {
        detail: { id: r.id, category, lon, lat },
      }));
      const msg = r.points_awarded > 0
        ? `⚡ ${label} καταχωρήθηκε · +${r.points_awarded} Πόντοι Γειτονιάς`
        : `⚡ ${label} καταχωρήθηκε`;
      notifyToast(msg);
    } catch {
      notifyToast("Η γρήγορη αναφορά δεν έγινε δεκτή.");
    }
  });

  const flush = async () => (await flushQueue(api, storage)).forEach(earned);
  window.addEventListener("online", flush);
  if (navigator.onLine) flush();

  return { open: openForm, close: closeForm, flush };
}
