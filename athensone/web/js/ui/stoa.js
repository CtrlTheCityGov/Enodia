// B8: Stoa AI bubble (SPEC F6, HUD «Κάτω δεξιά»).
// A bubble opens into a 380×520 panel (transform + opacity, 250 ms). Answers come from POST /api/map/stoa_ask
// through api.js; `answer_md` is rendered safely (everything escaped, Markdown links only) and each citation
// label becomes a link that emits `map:flyto` {lon, lat, label} on the shared bus (A-35). main.js flies there.
// Nothing here touches `document` at import time, so Node can test the pure functions.

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
    transition: `transform ${ANIM_MS}ms ease, opacity ${ANIM_MS}ms ease`,
    transform: "scale(0.6) translateY(20px)",
    opacity: "0",
    visibility: "hidden",
    display: "flex",
    flexDirection: "column",
  });

  const log = el("div", { className: "stoa-log" });
  log.setAttribute("aria-live", "polite");
  Object.assign(log.style, { flex: "1", overflowY: "auto" });

  const form = el("form", { className: "stoa-form" });
  const input = el("input", { type: "text", name: "q", maxLength: 500, placeholder: "Ρωτήστε τη Stoa…" });
  input.setAttribute("aria-label", "Ερώτηση προς τη Stoa AI");
  const send = el("button", { type: "submit", textContent: "Αποστολή" });
  form.append(input, send);
  panel.append(log, form);
  root.append(panel, bubble);

  let open = false;
  function setOpen(next) {
    open = next;
    bubble.setAttribute("aria-expanded", String(open));
    if (open) panel.style.visibility = "visible";
    panel.style.transform = open ? "none" : "scale(0.6) translateY(20px)";
    panel.style.opacity = open ? "1" : "0";
    if (open) input.focus();
    else setTimeout(() => { if (!open) panel.style.visibility = "hidden"; }, ANIM_MS);
  }
  bubble.addEventListener("click", () => setOpen(!open));
  panel.addEventListener("keydown", (e) => { if (e.key === "Escape") { setOpen(false); bubble.focus(); } });

  function addMessage(who, html) {
    const msg = el("div", { className: `stoa-msg stoa-${who}` });
    msg.innerHTML = html; // always built by escapeHtml / renderAnswerHtml
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
    addMessage("bot", renderAnswerHtml(answerMd, res?.citations || []));
    history.push({ question, answer_md: answerMd });
  });

  return { open: () => setOpen(true), close: () => setOpen(false) };
}
