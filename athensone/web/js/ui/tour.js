// First-visit interactive tour (Wave 2): a non-blocking spotlight + glass popover card with an animated
// arrow, walking the citizen through the six main HUD areas of citizen.html.
// Never touches document / window / maplibregl at import time and does no network I/O.
// The layer and the spotlight have pointer-events: none, so the HUD stays fully usable during the tour.

// localStorage key; bump the suffix to show a changed tour once more to returning users (design default).
export const TOUR_STORAGE_KEY = "enodia.tour.seen.v1";

// Delay before the first-visit auto start, so the map and HUD have painted (Wave 2 card).
export const TOUR_AUTOSTART_DELAY_MS = 650;

// Spotlight padding around the target and the card's distance from the viewport edges (Wave 2 card).
const SPOTLIGHT_PAD_PX = 6;
const VIEWPORT_MARGIN_PX = 12;
// Space between the card and the target, room for the 14 px arrow (design default).
const CARD_GAP_PX = 18;
// Keep the arrow this far from the card's rounded corners (design default).
const ARROW_EDGE_PX = 22;

// Six steps targeting real citizen.html elements; Greek copy from the Wave 2 card.
export const TOUR_STEPS = Object.freeze([
  Object.freeze({
    id: "welcome",
    target: "#hud-tabs",
    icon: "🗺️",
    title: "Καλώς ήρθατε στην Enodia",
    body: "Ο 3D Χάρτης Πολίτη του Δήμου Αθηναίων. Εναλλάξτε μεταξύ Χάρτη, Δημοτικών Έργων (Διαύγεια), Σκοτεινού θέματος και της παρακολούθησης των αναφορών σας.",
  }),
  Object.freeze({
    id: "layers",
    target: "#hud-layerbar",
    icon: "✨",
    title: "Ζωντανά Επίπεδα & 3D Πόλη",
    body: "Ενεργοποιήστε θερμοκρασία/AQI, προσβασιμότητα, δημοτικά έργα, εφημερεύοντα φαρμακεία και εναλλαγή 2D/3D κτιρίων με ένα πάτημα.",
  }),
  Object.freeze({
    id: "transit",
    target: 'button[data-layer="transit-buses"]',
    icon: "🚌",
    title: "Τηλεματική ΟΑΣΑ, Μετρό & Προαστιακός",
    body: "Δείτε ζωντανά λεωφορεία, δρομολόγια, γραμμές Μετρό Μ1–Μ3 και Προαστιακού, με διαδραστικό μενού φιλτραρίσματος και εντοπισμού.",
  }),
  Object.freeze({
    id: "report",
    // The '+' FAB first so the ring hugs the button; the slot is the fallback (querySelector takes the first match).
    target: "#hud-report .report-fab, #hud-report",
    icon: "📍",
    title: "Αναφορά Συμβάντος «+»",
    body: "Αναφέρετε βλάβες, εμπόδια ή πρόοδο έργου στον χάρτη. Πρόσωπα και πινακίδες θολώνονται αυτόματα — και παίρνετε κωδικό παρακολούθησης.",
  }),
  Object.freeze({
    id: "routing",
    target: "#hud-routing",
    icon: "🧭",
    title: "Έξυπνη Δρομολόγηση",
    body: "Υπολογίστε διαδρομές για αμαξίδιο, καρότσι ή δροσερότερη πορεία που αποφεύγουν ενεργά έργα και αναφερμένα εμπόδια.",
  }),
  Object.freeze({
    id: "stoa",
    // The Stoa bubble, not the hidden 380×520 .stoa-panel inside the same slot.
    target: "#hud-stoa .stoa-bubble, #hud-stoa",
    icon: "🏛️",
    title: "Stoa AI & Πόντοι Γειτονιάς",
    body: "Ρωτήστε τη Stoa AI για έργα και εγγυήσεις με επίσημα στοιχεία [ΑΔΑ] και κερδίστε Πόντους Γειτονιάς για κάθε επιβεβαιωμένη αναφορά.",
  }),
]);

// True only on a first visit: nothing stored under TOUR_STORAGE_KEY and no ?notour=1 in the URL.
export function shouldShowTour(storage, search = "") {
  let seen = null;
  try {
    seen = storage?.getItem?.(TOUR_STORAGE_KEY);
  } catch {
    // Storage blocked (private mode): treat as not seen; close() will simply fail to persist.
    seen = null;
  }
  if (seen) return false;
  return !String(search ?? "").includes("notour=1");
}

function clamp(value, min, max) {
  if (max < min) return min;
  return Math.min(Math.max(value, min), max);
}

function isUsableRect(r) {
  return Boolean(
    r &&
      [r.top, r.left, r.width, r.height].every((n) => Number.isFinite(Number(n))) &&
      Number(r.width) > 0 &&
      Number(r.height) > 0,
  );
}

// Pure geometry: where to put a card of cardSize {width, height} next to targetRect
// {top, left, width, height} inside viewport {width, height}. Tries bottom, top, right, left;
// falls back to "center" with no arrow when there is no target or no side fits.
// arrowSide is the card edge carrying the arrow ("top" when the card sits below the target).
export function computeTourPlacement(targetRect, cardSize, viewport) {
  const m = VIEWPORT_MARGIN_PX;
  const vw = Math.max(0, Number(viewport?.width) || 0);
  const vh = Math.max(0, Number(viewport?.height) || 0);
  const w = Math.min(Math.max(0, Number(cardSize?.width) || 0), Math.max(0, vw - 2 * m));
  const h = Math.max(0, Number(cardSize?.height) || 0);

  const center = () => ({
    placement: "center",
    top: Math.round(clamp((vh - h) / 2, m, vh - h - m)),
    left: Math.round(clamp((vw - w) / 2, m, vw - w - m)),
    arrowSide: null,
    arrowOffset: 0,
  });

  if (!isUsableRect(targetRect)) return center();
  const t = {
    top: Number(targetRect.top),
    left: Number(targetRect.left),
    width: Number(targetRect.width),
    height: Number(targetRect.height),
  };
  t.bottom = t.top + t.height;
  t.right = t.left + t.width;
  const cx = t.left + t.width / 2;
  const cy = t.top + t.height / 2;
  // A target entirely outside the viewport gets the centred card.
  if (t.right < 0 || t.left > vw || t.bottom < 0 || t.top > vh) return center();

  const g = CARD_GAP_PX;
  const space = {
    bottom: vh - t.bottom - g - m,
    top: t.top - g - m,
    right: vw - t.right - g - m,
    left: t.left - g - m,
  };

  const horizontal = (top, arrowSide, placement) => {
    const left = clamp(cx - w / 2, m, vw - w - m);
    return {
      placement,
      top: Math.round(clamp(top, m, vh - h - m)),
      left: Math.round(left),
      arrowSide,
      arrowOffset: Math.round(clamp(cx - left, ARROW_EDGE_PX, w - ARROW_EDGE_PX)),
    };
  };
  const vertical = (left, arrowSide, placement) => {
    const top = clamp(cy - h / 2, m, vh - h - m);
    return {
      placement,
      top: Math.round(top),
      left: Math.round(clamp(left, m, vw - w - m)),
      arrowSide,
      arrowOffset: Math.round(clamp(cy - top, ARROW_EDGE_PX, h - ARROW_EDGE_PX)),
    };
  };

  if (space.bottom >= h) return horizontal(t.bottom + g, "top", "bottom");
  if (space.top >= h) return horizontal(t.top - g - h, "bottom", "top");
  if (space.right >= w) return vertical(t.right + g, "left", "right");
  if (space.left >= w) return vertical(t.left - g - w, "right", "left");
  return center();
}

// Static, data-free arrow artwork (a chevron pointing up; CSS rotates it per side).
const ARROW_SVG =
  '<svg viewBox="0 0 28 16" width="28" height="16" aria-hidden="true" focusable="false">' +
  '<path d="M2 15 L14 2 L26 15" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>' +
  "</svg>";

export function initTour({ root = null, bus = null, storage = null, autoStart } = {}) {
  const doc = root && typeof root.createElement === "function" ? root : root?.ownerDocument ?? null;
  const win = () => doc?.defaultView ?? (typeof window !== "undefined" ? window : null);

  const st = {
    open: false,
    index: 0,
    nodes: null,
    autoTimer: null,
    rafId: null,
  };

  function emit(name, detail) {
    if (bus && typeof bus.dispatchEvent === "function" && typeof globalThis.CustomEvent === "function") {
      bus.dispatchEvent(new CustomEvent(name, { detail }));
    }
  }

  function markSeen() {
    try {
      storage?.setItem?.(TOUR_STORAGE_KEY, "1");
    } catch {
      // Storage blocked: the tour may show again next visit; nothing else breaks.
    }
  }

  function el(tag, className, text) {
    const node = doc.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function button(className, text, onClick) {
    const b = el("button", className, text);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function build() {
    const layer = el("div", "enodia-tour-layer");
    const spotlight = el("div", "enodia-tour-spotlight");
    spotlight.setAttribute("aria-hidden", "true");

    const card = el("div", "glass enodia-tour-card");
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-modal", "false");
    card.setAttribute("aria-labelledby", "enodia-tour-title");
    card.setAttribute("aria-describedby", "enodia-tour-body");

    const arrow = el("span", "enodia-tour-arrow");
    arrow.setAttribute("aria-hidden", "true");
    arrow.innerHTML = ARROW_SVG;

    const head = el("div", "enodia-tour-card__head");
    const icon = el("span", "enodia-tour-card__icon");
    icon.setAttribute("aria-hidden", "true");
    const step = el("span", "enodia-tour-card__step");
    const closeBtn = button("enodia-tour-card__close", "✕", () => close(true));
    closeBtn.setAttribute("aria-label", "Κλείσιμο οδηγού");
    closeBtn.setAttribute("title", "Κλείσιμο");
    head.append(icon, step, closeBtn);

    const title = el("h2", "enodia-tour-card__title");
    title.id = "enodia-tour-title";
    const body = el("p", "enodia-tour-card__body");
    body.id = "enodia-tour-body";
    body.setAttribute("aria-live", "polite");

    const dots = el("div", "enodia-tour-dots");
    dots.setAttribute("role", "group");
    dots.setAttribute("aria-label", "Βήματα οδηγού");
    const dotButtons = TOUR_STEPS.map((_, i) => {
      const d = button("enodia-tour-dot", null, () => goTo(i));
      d.setAttribute("aria-label", `Μετάβαση στο βήμα ${i + 1}`);
      dots.appendChild(d);
      return d;
    });

    const foot = el("div", "enodia-tour-card__foot");
    const skipBtn = button("enodia-tour-btn enodia-tour-btn--ghost", "Παράλειψη", () => close(true));
    const spacer = el("span", "enodia-tour-card__spacer");
    const prevBtn = button("enodia-tour-btn enodia-tour-btn--ghost", "Πίσω", () => prev());
    const nextBtn = button("enodia-tour-btn enodia-tour-btn--primary", "Επόμενο", () => next());
    foot.append(skipBtn, spacer, prevBtn, nextBtn);

    card.append(arrow, head, title, body, dots, foot);
    layer.append(spotlight, card);
    return { layer, spotlight, card, arrow, icon, step, title, body, dotButtons, prevBtn, nextBtn };
  }

  function viewport() {
    const w = win();
    return {
      width: w?.innerWidth ?? doc?.documentElement?.clientWidth ?? 0,
      height: w?.innerHeight ?? doc?.documentElement?.clientHeight ?? 0,
    };
  }

  // "a, b" is tried in list order (querySelector would return the first match in document order, i.e. the
  // parent slot before its child button). Our selectors contain no commas inside attribute values.
  function findTarget(selector) {
    for (const part of String(selector).split(",")) {
      const sel = part.trim();
      if (!sel) continue;
      try {
        const node = doc.querySelector?.(sel) ?? null;
        if (node) return node;
      } catch {
        // invalid selector: try the next one
      }
    }
    return null;
  }

  function px(n) {
    return `${Math.round(n)}px`;
  }

  function position() {
    if (!st.open || !st.nodes) return;
    const n = st.nodes;
    const target = findTarget(TOUR_STEPS[st.index].target);
    const rect = target?.getBoundingClientRect?.() ?? null;
    const usable = isUsableRect(rect);

    if (usable) {
      n.spotlight.classList.remove("is-hidden");
      n.spotlight.style.top = px(rect.top - SPOTLIGHT_PAD_PX);
      n.spotlight.style.left = px(rect.left - SPOTLIGHT_PAD_PX);
      n.spotlight.style.width = px(rect.width + 2 * SPOTLIGHT_PAD_PX);
      n.spotlight.style.height = px(rect.height + 2 * SPOTLIGHT_PAD_PX);
    } else {
      n.spotlight.classList.add("is-hidden");
    }

    // offsetWidth/Height ignore the entrance scale() animation; the rect is only a fallback.
    const cardRect = n.card.getBoundingClientRect?.();
    const size = {
      width: n.card.offsetWidth || cardRect?.width || 320,
      height: n.card.offsetHeight || cardRect?.height || 220,
    };
    const placed = computeTourPlacement(usable ? rect : null, size, viewport());
    n.card.style.top = px(placed.top);
    n.card.style.left = px(placed.left);
    n.card.dataset.placement = placed.placement;
    if (placed.arrowSide) {
      n.arrow.hidden = false;
      n.arrow.dataset.side = placed.arrowSide;
      const along = placed.arrowSide === "top" || placed.arrowSide === "bottom";
      n.arrow.style.left = along ? px(placed.arrowOffset) : "";
      n.arrow.style.top = along ? "" : px(placed.arrowOffset);
    } else {
      n.arrow.hidden = true;
    }
  }

  function render() {
    const n = st.nodes;
    const step = TOUR_STEPS[st.index];
    const last = st.index === TOUR_STEPS.length - 1;
    n.icon.textContent = step.icon;
    n.step.textContent = `Βήμα ${st.index + 1} / ${TOUR_STEPS.length}`;
    n.title.textContent = step.title;
    n.body.textContent = step.body;
    n.card.dataset.step = step.id;
    n.dotButtons.forEach((d, i) => {
      const active = i === st.index;
      d.classList.toggle("is-active", active);
      d.classList.toggle("is-done", i < st.index);
      if (active) d.setAttribute("aria-current", "step");
      else d.removeAttribute("aria-current");
    });
    n.prevBtn.disabled = st.index === 0;
    n.nextBtn.textContent = last ? "Ξεκινήστε!" : "Επόμενο";

    // A chip scrolled out of the horizontal layer bar (mobile) is brought into view first.
    const target = findTarget(step.target);
    try {
      target?.scrollIntoView?.({ block: "nearest", inline: "center" });
    } catch {
      // Older engines without the options object: ignore.
    }
    position();
    emit("tour:step", { index: st.index, id: step.id });
  }

  // --- global listeners, attached only while the tour is open
  function isTyping(node) {
    const tag = String(node?.tagName ?? "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || Boolean(node?.isContentEditable);
  }

  function onKeydown(event) {
    if (!st.open) return;
    if (event.key === "Escape") {
      close(true);
      return;
    }
    const active = doc.activeElement;
    // Arrow keys belong to the tour only when focus is on the card or nowhere in particular,
    // so the layer bar's own arrow-key navigation and text fields keep working.
    const onCard = Boolean(active && st.nodes?.card.contains?.(active));
    const idle = !active || active === doc.body || active === doc.documentElement;
    if (isTyping(active) || !(onCard || idle)) return;
    if (event.key === "ArrowRight") {
      event.preventDefault?.();
      next();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault?.();
      prev();
    }
  }

  function onDocClick(event) {
    // Capture phase, never preventDefault: the user's click on the '+' still opens the report flow.
    if (st.open && event?.target?.closest?.(".report-fab")) close(true);
  }

  function onResize() {
    const w = win();
    if (st.rafId !== null || typeof w?.requestAnimationFrame !== "function") {
      if (st.rafId === null) position();
      return;
    }
    st.rafId = w.requestAnimationFrame(() => {
      st.rafId = null;
      position();
    });
  }

  function attach() {
    doc.addEventListener?.("keydown", onKeydown);
    doc.addEventListener?.("click", onDocClick, true);
    win()?.addEventListener?.("resize", onResize);
  }

  function detach() {
    doc.removeEventListener?.("keydown", onKeydown);
    doc.removeEventListener?.("click", onDocClick, true);
    win()?.removeEventListener?.("resize", onResize);
    if (st.rafId !== null) {
      win()?.cancelAnimationFrame?.(st.rafId);
      st.rafId = null;
    }
  }

  // --- public API
  function start(stepIndex = 0) {
    if (st.autoTimer !== null) {
      clearTimeout(st.autoTimer);
      st.autoTimer = null;
    }
    if (!doc || typeof doc.createElement !== "function" || !doc.body?.appendChild) return false;
    const i = Number.isInteger(stepIndex) ? clamp(stepIndex, 0, TOUR_STEPS.length - 1) : 0;
    if (!st.nodes) st.nodes = build();
    if (!st.nodes.layer.parentNode) doc.body.appendChild(st.nodes.layer);
    const wasOpen = st.open;
    st.open = true;
    st.index = i;
    if (!wasOpen) attach();
    render();
    st.nodes.nextBtn.focus?.({ preventScroll: true });
    if (!wasOpen) emit("tour:open", { index: i });
    return true;
  }

  function goTo(i) {
    if (!st.open) return;
    st.index = clamp(i, 0, TOUR_STEPS.length - 1);
    render();
  }

  function next() {
    if (!st.open) return;
    if (st.index >= TOUR_STEPS.length - 1) {
      close(true);
      return;
    }
    goTo(st.index + 1);
  }

  function prev() {
    if (st.open && st.index > 0) goTo(st.index - 1);
  }

  function close(markAsSeen = true) {
    if (st.autoTimer !== null) {
      clearTimeout(st.autoTimer);
      st.autoTimer = null;
    }
    if (markAsSeen) markSeen();
    if (!st.open) return;
    st.open = false;
    detach();
    st.nodes?.layer.remove?.();
    emit("tour:close", { index: st.index });
  }

  // First-visit auto start: only on the real page document in a browser, never in Node/Deno tests.
  const shouldAuto =
    autoStart ??
    (typeof window !== "undefined" && typeof document !== "undefined" && doc !== null && doc === document);
  if (shouldAuto && shouldShowTour(storage, win()?.location?.search ?? "")) {
    st.autoTimer = setTimeout(() => {
      st.autoTimer = null;
      start(0);
    }, TOUR_AUTOSTART_DELAY_MS);
  }

  return {
    start,
    next,
    prev,
    close,
    isOpen: () => st.open,
    get index() {
      return st.index;
    },
    destroy() {
      close(false);
      st.nodes = null;
    },
  };
}
