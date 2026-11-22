// B8: Stoa AI bubble (SPEC F6, HUD «Κάτω δεξιά»).
// A bubble opens into a 380×520 panel (transform + opacity, 250 ms). Answers come from POST /api/map/stoa_ask
// through api.js; `answer_md` is rendered safely (everything escaped, Markdown links only) and each citation
// label becomes a link that emits `map:flyto` {lon, lat, label} on the shared bus (A-35). main.js flies there.
// Nothing here touches `document` at import time, so Node can test the pure functions.

import { speakResponse, stopSpeech } from "../speech.js";

// Panel size and animation from SPEC HUD «Κάτω δεξιά». Sure.
export const PANEL_W = 380;
export const PANEL_H = 520;
export const ANIM_MS = 250;

// Shown when the request fails; same wording as the backend refusal (app/stoa_ask.py REFUSAL_TEXT). Sure.
const REFUSAL = "Δεν βρήκα τεκμηριωμένα στοιχεία για αυτό.";

// Only http(s) links become <a>; anything else (javascript:, data:) stays text. Sure.
const LINK_RE = /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g;

/** Escape the five HTML special characters, so text can never become an element or break an attribute. */
export function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Replace each citation label in already-escaped text with a flyTo link. Longest label first, one pass. */
function linkCitations(escapedText, citations) {
  const byLabel = new Map();
  for (const c of citations) {
    const lon = Number(c?.lon);
    const lat = Number(c?.lat);
    if (!c?.label || !Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    const key = escapeHtml(c.label);
    if (!byLabel.has(key)) byLabel.set(key, { lon, lat, label: c.label, kind: c.kind });
  }
  if (byLabel.size === 0) return escapedText;
  const keys = [...byLabel.keys()].sort((a, b) => b.length - a.length);
  const re = new RegExp(keys.map(escapeRegExp).join("|"), "g");
  return escapedText.replace(re, (match) => {
    const c = byLabel.get(match);
    return (
      `<a href="#" class="stoa-cite" data-lon="${c.lon}" data-lat="${c.lat}"` +
      ` data-label="${escapeHtml(c.label)}" data-kind="${escapeHtml(c.kind ?? "")}">${match}</a>`
    );
  });
}

function formatUpdatedAt(value) {
  if (value == null || value === "") return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value.toLocaleString("el-GR");
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const parsed = new Date(trimmed);
    return Number.isNaN(parsed.getTime()) ? trimmed : parsed.toLocaleString("el-GR");
  }
  return null;
}

export function renderProvenanceHtml(res) {
  if (!res || typeof res !== "object") return "";
  const rawSrc = String(res.source ?? res.data_source ?? "").trim().toLowerCase();
  const isSeed = String(res.data_source ?? "").trim().toUpperCase() === "SEED";
  let prov = null;
  if (rawSrc === "live" && !isSeed) prov = { key: "live", label: "LIVE" };
  else if (rawSrc === "cache" || rawSrc === "cached") prov = { key: "cached", label: "CACHED" };
  else if (rawSrc === "mock" || rawSrc === "demo" || rawSrc === "seed" || isSeed) prov = { key: "demo", label: "DEMO" };
  const updatedStr = formatUpdatedAt(res.updated_at);
  if (!prov && !updatedStr) return "";
  const parts = [];
  if (prov) parts.push(`<span class="prov-pill prov-pill--${prov.key}">${prov.label}</span>`);
  if (isSeed) parts.push(`<span class="prov-seed">SEED</span>`);
  if (updatedStr) parts.push(`<span class="prov-updated">${escapeHtml(updatedStr)}</span>`);
  return `<div class="stoa-prov">${parts.join(" ")}</div>`;
}

/** HTML for one answer: escaped text, Markdown links to http(s) only, citation labels as flyTo links. */
export function renderAnswerHtml(answerMd, citations = []) {
  const escaped = escapeHtml(answerMd);
  let html = "";
  let last = 0;
  // Escaping never adds or removes [ ] ( ), so links can be found in the escaped text.
  for (const m of escaped.matchAll(LINK_RE)) {
    html += linkCitations(escaped.slice(last, m.index), citations);
    html += `<a href="${m[2]}" target="_blank" rel="noopener noreferrer">${m[1]}</a>`;
    last = m.index + m[0].length;
  }
  html += linkCitations(escaped.slice(last), citations);
  return html.replace(/\n/g, "<br>");
}

/** Click on a citation link → `map:flyto` {lon, lat, label} on the bus. Other clicks are left alone. */
export function handleCitationClick(event, bus) {
  const link = event?.target?.closest?.("a[data-lon][data-lat]");
  if (!link) return false;
  event.preventDefault();
  const lon = Number(link.dataset.lon);
  const lat = Number(link.dataset.lat);
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return false;
  const label = link.dataset.label ?? link.textContent;
  bus.dispatchEvent(new CustomEvent("map:flyto", { detail: { lon, lat, label } }));
  return true;
}

/** Map centre as [lon, lat] for the contract, or undefined (the backend then uses its demo start point). */
function mapCenter(map) {
  const c = map?.getCenter?.();
  return c ? [c.lng, c.lat] : undefined;
}

/** Build a strictly data-grounded Greek route explanation + map citations (Layer C). */
export function buildRouteAnalysisAnswer(detail = {}) {
  const profile = detail.profile || "wheelchair";
  const profileLabel =
    detail.profileLabel ||
    (profile === "wheelchair" ? "Αμαξίδιο" : profile === "stroller" ? "Καρότσι" : "Δροσερότερη διαδρομή");
  const route = detail.route || {};
  const cmp = route.comparison || null;
  const reasons = Array.isArray(route.reasons) ? route.reasons : [];
  const citations = [];
  const bullets = [];

  const fromLbl = detail.fromLabel || "Αφετηρία";
  const toLbl = detail.toLabel || "Προορισμός";
  const distM = Number(route.distance_m);
  const durS = Number(route.duration_s);
  const distStr = Number.isFinite(distM)
    ? distM >= 1000
      ? `${(distM / 1000).toFixed(1).replace(".", ",")} χλμ.`
      : `${Math.round(distM)} μ.`
    : "άγνωστη απόσταση";
  const durStr = Number.isFinite(durS) ? `${Math.max(1, Math.round(durS / 60))} λεπτά` : "άγνωστη διάρκεια";

  const lines = [`Ανάλυση διαδρομής ${fromLbl} → ${toLbl} (${profileLabel}: ${durStr}, ${distStr}):`];

  if (cmp) {
    const avoidedWorks = Array.isArray(cmp.avoided_works) ? cmp.avoided_works : [];
    const avoidedReports = Array.isArray(cmp.avoided_reports) ? cmp.avoided_reports : [];
    for (const w of avoidedWorks) {
      const label = w.street ? `Έργο ${w.street}` : `Έργο ${w.id}`;
      const adaPart = w.ada ? ` [ΑΔΑ ${w.ada}]` : "";
      bullets.push(`• Αποφεύγει ενεργό δημοτικό έργο: ${label}${adaPart}.`);
      if (Number.isFinite(Number(w.lon)) && Number.isFinite(Number(w.lat))) {
        citations.push({ label, lon: Number(w.lon), lat: Number(w.lat), kind: "work" });
      }
    }
    for (const r of avoidedReports) {
      const catText = r.category === "congestion" ? "σημείο συμφόρησης" : "αναφερμένο εμπόδιο";
      const label = `Αναφορά ${r.id}`;
      bullets.push(`• Παρακάμπτει ${catText} πολιτών (${label}).`);
      if (Number.isFinite(Number(r.lon)) && Number.isFinite(Number(r.lat))) {
        citations.push({ label, lon: Number(r.lon), lat: Number(r.lat), kind: "report" });
      }
    }

    const bestM = cmp.best || {};
    const baseM = cmp.baseline || null;
    const deltas = cmp.deltas || {};

    if (profile === "wheelchair") {
      bullets.push("• Χρησιμοποιεί προφίλ προσβασιμότητας χωρίς σκαλιά (Valhalla wheelchair) και αποφεύγει κλειστά έργα.");
    } else if (profile === "stroller") {
      bullets.push("• Προτιμά ήπιους δρόμους χωρίς απότομα εμπόδια, έργα και έντονη κυκλοφορία.");
    }

    if (Number.isFinite(bestM.shade_pct)) {
      if (baseM && !cmp.same_as_baseline && deltas.shade_pct > 0) {
        bullets.push(`• Περισσότερη σκιά: ${bestM.shade_pct}% έναντι ${baseM.shade_pct}% στη συντομότερη (+${deltas.shade_pct}%).`);
      } else {
        bullets.push(`• Κάλυψη σκιάς κατά μήκος της διαδρομής: ${bestM.shade_pct}%.`);
      }
    }

    if (Number.isFinite(bestM.busy_pct)) {
      if (baseM && !cmp.same_as_baseline && deltas.busy_pct < 0) {
        bullets.push(`• Λιγότεροι δρόμοι υψηλής κυκλοφορίας: ${bestM.busy_pct}% αντί ${baseM.busy_pct}% (${deltas.busy_pct}%).`);
      } else {
        bullets.push(`• Έκθεση σε δρόμους με έντονη κίνηση: ${bestM.busy_pct}%.`);
      }
    }

    const envInfo = cmp.env || {};
    const envParts = [];
    if (envInfo.temp_c !== null && envInfo.temp_c !== undefined) envParts.push(`θερμοκρασία ${envInfo.temp_c}°C`);
    if (envInfo.aqi !== null && envInfo.aqi !== undefined) envParts.push(`δείκτης αέρα AQI ${envInfo.aqi}`);
    if (envInfo.uv_index !== null && envInfo.uv_index !== undefined) envParts.push(`δείκτης UV ${envInfo.uv_index}`);
    if (envParts.length > 0) {
      bullets.push(`• Τρέχουσες συνθήκες περιοχής: ${envParts.join(", ")}.`);
    }

    if (cmp.same_as_baseline) {
      if ((cmp.on_route_works ?? 0) === 0 && (cmp.on_route_reports ?? 0) === 0) {
        bullets.push("• Η συντομότερη διαδρομή είναι ήδη καθαρή από ενεργά έργα και αναφερμένα εμπόδια.");
      }
    } else if (Number.isFinite(deltas.duration_s) && Number.isFinite(deltas.distance_m)) {
      const extraMin = Math.round(deltas.duration_s / 60);
      const timeNote = extraMin > 0 ? `+${extraMin} λεπτά` : "ίδιος χρόνος";
      const distNote = deltas.distance_m > 0 ? `+${deltas.distance_m} μ.` : `${deltas.distance_m} μ.`;
      bullets.push(`• Κόστος παράκαμψης έναντι της συντομότερης: ${timeNote} (${distNote}).`);
    }
  } else if (reasons.length > 0) {
    for (const r of reasons) {
      const txt = typeof r === "string" ? r : r?.text;
      if (txt) bullets.push(`• ${txt}.`);
    }
  } else {
    bullets.push("• Επιλέχθηκε βάσει των διαθέσιμων δεδομένων προσβασιμότητας και περιβάλλοντος.");
  }

  return {
    question: `Γιατί αυτή η διαδρομή είναι καλύτερη για ${profileLabel} (${fromLbl} → ${toLbl});`,
    answer_md: [...lines, ...bullets].join("\n"),
    citations,
  };
}

/**
 * Mount the bubble + panel into ctx.root (A-35: ctx = {map, api, root, bus}).
 * Expects `ctx.api.stoaAsk({question, center, history})` → `{answer_md, citations}` (B1, api.js).
 */
export function mount({ map, api, root, container, bus }) {
  root = container || root;
  const doc = root.ownerDocument || globalThis.document;
  const el = (tag, props = {}) => Object.assign(doc.createElement(tag), props);
  const history = [];

  const bubble = el("button", { type: "button", className: "stoa-bubble", textContent: "Stoa AI" });
  bubble.setAttribute("aria-expanded", "false");
  bubble.setAttribute("aria-controls", "stoa-panel");

  const panel = el("section", { id: "stoa-panel", className: "stoa-panel" });
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Stoa AI");
  Object.assign(panel.style, {
    width: `min(${PANEL_W}px, calc(100vw - 24px))`,
    height: `min(${PANEL_H}px, calc(100vh - 96px))`,
    transformOrigin: "bottom right",
    transition: `transform ${ANIM_MS}ms cubic-bezier(0.16, 1, 0.3, 1), opacity ${ANIM_MS}ms cubic-bezier(0.16, 1, 0.3, 1)`,
    transform: "scale(0.86) translateY(14px)",
    opacity: "0",
    visibility: "hidden",
    display: "flex",
    flexDirection: "column",
  });

  const header = el("div", { className: "workstab-header" });
  const heading = el("strong", { textContent: "Stoa AI" });
  const closeBtn = el("button", { type: "button", className: "overlay-close-btn", textContent: "×" });
  closeBtn.setAttribute("aria-label", "Κλείσιμο Stoa AI");
  closeBtn.addEventListener("click", () => { setOpen(false); bubble.focus(); });
  header.append(heading, closeBtn);

  const log = el("div", { className: "stoa-log" });
  log.setAttribute("aria-live", "polite");
  Object.assign(log.style, { flex: "1", overflowY: "auto" });

  const form = el("form", { className: "stoa-form" });
  const input = el("input", { type: "text", name: "q", maxLength: 500, placeholder: "Ρωτήστε τη Stoa…" });
  input.setAttribute("aria-label", "Ερώτηση προς τη Stoa AI");
  const SpeechRec = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition;
  let micBtn = null;
  if (SpeechRec) {
    micBtn = el("button", { type: "button", className: "stoa-mic-btn", textContent: "Φωνή" });
    micBtn.setAttribute("aria-label", "Φωνητική ερώτηση στα ελληνικά");
    micBtn.addEventListener("click", () => {
      const rec = new SpeechRec();
      rec.lang = "el-GR";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      micBtn.disabled = true;
      rec.onresult = (ev) => {
        const txt = ev?.results?.[0]?.[0]?.transcript || "";
        if (txt) input.value = txt;
        input.focus();
      };
      rec.onerror = () => { micBtn.disabled = false; };
      rec.onend = () => { micBtn.disabled = false; };
      rec.start();
    });
  }
  const send = el("button", { type: "submit", textContent: "Αποστολή" });
  if (micBtn) form.append(input, micBtn, send);
  else form.append(input, send);
  panel.append(header, log, form);
  root.append(panel, bubble);

  let open = false;
  function setOpen(next) {
    open = next;
    bubble.setAttribute("aria-expanded", String(open));
    const curve = open ? "cubic-bezier(0.16, 1, 0.3, 1)" : "cubic-bezier(0.32, 0.72, 0, 1)";
    panel.style.transition = `transform ${ANIM_MS}ms ${curve}, opacity ${ANIM_MS}ms ${curve}`;
    if (open) panel.style.visibility = "visible";
    panel.style.transform = open ? "scale(1) translateY(0)" : "scale(0.86) translateY(14px)";
    panel.style.opacity = open ? "1" : "0";
    if (open) input.focus();
    else setTimeout(() => { if (!open) panel.style.visibility = "hidden"; }, ANIM_MS);
  }
  bubble.addEventListener("click", () => setOpen(!open));
  panel.addEventListener("keydown", (e) => { if (e.key === "Escape") { setOpen(false); bubble.focus(); } });

  function addMessage(who, html, speakText = "") {
    const msg = el("div", { className: `stoa-msg stoa-${who}` });
    msg.innerHTML = html; // always built by escapeHtml / renderAnswerHtml
    if (who === "bot" && speakText) {
      const speakBtn = el("button", { type: "button", className: "stoa-speak-btn", textContent: "🔊 Ανάγνωση" });
      speakBtn.setAttribute("aria-label", "Ανάγνωση απάντησης στα ελληνικά");
      const speechNote = el("span", { className: "stoa-speech-note", role: "status", "aria-live": "polite" });
      let speaking = false;
      speakBtn.addEventListener("click", async () => {
        if (speaking) {
          stopSpeech();
          speaking = false;
          speakBtn.textContent = "🔊 Ανάγνωση";
          return;
        }
        speaking = true;
        speechNote.textContent = "";
        speakBtn.textContent = "⏹ Διακοπή";
        await speakResponse({
          text: speakText,
          api,
          onStatus: (note) => {
            speechNote.textContent = note;
          },
          onEnd: () => {
            speaking = false;
            speakBtn.textContent = "🔊 Ανάγνωση";
          },
        });
      });
      msg.append(speakBtn, speechNote);
    }
    log.append(msg);
    log.scrollTop = log.scrollHeight;
  }

  log.addEventListener("click", (e) => handleCitationClick(e, bus));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    addMessage("user", escapeHtml(question));
    send.disabled = true;
    let res;
    try {
      // Last 6 turns as context; the rule router ignores it today. Implementer's choice, unverified.
      res = await api.stoaAsk({ question, center: mapCenter(map), history: history.slice(-6) });
    } catch {
      res = null;
    }
    send.disabled = false;
    const answerMd = res?.answer_md || REFUSAL;
    const provHtml = renderProvenanceHtml(res ?? { source: "mock" });
    addMessage("bot", provHtml + renderAnswerHtml(answerMd, res?.citations || []), answerMd.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1"));
    history.push({ question, answer_md: answerMd });
  });

  // Layer C: 1-tap "✨ Εξήγηση από Stoa AI" from the routing comparison card.
  if (bus && typeof bus.addEventListener === "function") {
    bus.addEventListener("stoa:analyze-route", async (event) => {
      const detail = event?.detail || {};
      setOpen(true);
      const built = buildRouteAnalysisAnswer(detail);
      addMessage("user", escapeHtml(built.question));

      let finalMd = built.answer_md;
      const mergedCitations = [...built.citations];
      let extraMeta = null;

      // Enrich with verified Diavgeia / Stoa records if an avoided municipal work names a street.
      const avoidedWorks = detail?.route?.comparison?.avoided_works;
      const firstStreet = Array.isArray(avoidedWorks)
        ? avoidedWorks.find((w) => typeof w?.street === "string" && w.street.trim())?.street?.trim()
        : null;
      if (firstStreet && api && typeof api.stoaAsk === "function") {
        try {
          const extra = await api.stoaAsk({
            question: `Τι έργα γίνονται στην ${firstStreet};`,
            center: mapCenter(map),
            history: [],
          });
          if (extra?.answer_md && extra.answer_md !== REFUSAL) {
            extraMeta = extra;
            finalMd += `\n\nΕπίσημα στοιχεία Διαύγειας (${firstStreet}):\n${extra.answer_md}`;
            if (Array.isArray(extra.citations)) {
              mergedCitations.push(...extra.citations);
            }
          }
        } catch {
          // Offline / unavailable: the telemetry-grounded route analysis already stands on its own.
        }
      }

      const routeProvHtml = renderProvenanceHtml(extraMeta ?? { source: detail?.route?.source });
      addMessage("bot", routeProvHtml + renderAnswerHtml(finalMd, mergedCitations), finalMd.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1"));
      history.push({ question: built.question, answer_md: finalMd });
    });
  }

  return { open: () => setOpen(true), close: () => setOpen(false) };
}
