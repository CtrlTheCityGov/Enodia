// B7: «Πόντοι Γειτονιάς» pill (top right) + panel with history and rewards (SPEC F7, HUD «Πάνω δεξιά»).
// mount(ctx) follows A-35: ctx = {map, api, root, bus}. Touches `document` only inside mount(), never at import.

// Pulse and rising «+N» duration. Source: SPEC HUD table («Animation pulse 600ms»). Certainty: verified.
export const PULSE_MS = 600;

// Label for the example rewards. Source: B7 card and data/rewards.json "note". Certainty: verified.
export const REWARDS_NOTE = "πρόταση, ανοιχτό ερώτημα προς τον Δήμο";

// Badge text per non-live data source. Source: CLAUDE.md «Mock data is labelled». Certainty: verified (wording).
const SOURCE_BADGE = { mock: "δοκιμαστικό", cache: "Offline λειτουργία" };

// "+5" / "−30" (U+2212 minus sign, as in the card's test table).
export function formatDelta(n) {
  if (n > 0) return `+${n}`;
  if (n < 0) return `−${Math.abs(n)}`;
  return "0";
}

// History dates in Athens time, not the UTC date of the ISO string (B17 card: «Europe/Athens date»).
// 2026-11-21T22:30:00Z is 22/11/2026 in Athens (UTC+2). el-GR gives dd/mm/yyyy (Node full ICU; sure).
const ATHENS_DATE = new Intl.DateTimeFormat("el-GR", {
  timeZone: "Europe/Athens", day: "2-digit", month: "2-digit", year: "numeric",
});

export function athensDate(ts) {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "άγνωστο" : ATHENS_DATE.format(d);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export async function mount({ api, root, container, bus }) {
  root = container || root;
  let state = { balance: 0, district: null, history: [], rewards: [], source: null };

  // --- pill: button with balance + district progress bar
  const pill = el("button", "glass points-pill");
  pill.type = "button";
  pill.setAttribute("aria-expanded", "false");
  pill.setAttribute("aria-controls", "points-panel");
  const label = el("span", "points-label", "Πόντοι Γειτονιάς");
  const balanceEl = el("span", "points-balance", "");
  const bar = el("span", "points-bar");
  bar.setAttribute("role", "progressbar");
  bar.setAttribute("aria-valuemin", "0");
  bar.setAttribute("aria-valuemax", "100");
  const barFill = el("span", "points-bar-fill");
  bar.appendChild(barFill);
  const badge = el("span", "points-source", "");
  pill.appendChild(label);
  pill.appendChild(balanceEl);
  pill.appendChild(bar);
  pill.appendChild(badge);
  root.appendChild(pill);

  // --- panel: history + rewards, hidden until the pill is clicked
  const panel = el("section", "glass points-panel");
  panel.id = "points-panel";
  panel.setAttribute("aria-label", "Πόντοι Γειτονιάς");
  panel.hidden = true;
  root.appendChild(panel);

  function renderPill() {
    balanceEl.textContent = String(state.balance);
    const d = state.district;
    const pct = d ? d.progress_pct : 0;
    barFill.style.width = `${pct}%`;
    bar.setAttribute("aria-valuenow", String(pct));
    bar.setAttribute("aria-label", d ? `${d.name}: ${pct}% του στόχου ${d.goal}` : "Δημοτική κοινότητα: άγνωστο");
    badge.textContent = SOURCE_BADGE[state.source] || "";
  }

  function renderPanel() {
    panel.textContent = "";
    const topRow = el("div", "workstab-header");
    topRow.appendChild(el("h2", "", "Ιστορικό"));
    const closeBtn = el("button", "overlay-close-btn", "×");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Κλείσιμο");
    closeBtn.addEventListener("click", () => setPanelOpen(false));
    topRow.appendChild(closeBtn);
    panel.appendChild(topRow);
    const list = el("ul", "points-history");
    if (state.history.length === 0) list.appendChild(el("li", "", "Δεν υπάρχουν κινήσεις ακόμη."));
    for (const h of state.history) {
      list.appendChild(el("li", "", `${formatDelta(h.delta)} · ${h.reason} · ${athensDate(h.ts)}`));
    }
    panel.appendChild(list);

    panel.appendChild(el("h2", "", "Εξαργύρωση"));
    panel.appendChild(el("p", "points-note", REWARDS_NOTE));
    const status = el("p", "points-status", "");
    status.setAttribute("aria-live", "polite");
    const rewardsList = el("ul", "points-rewards");
    for (const r of state.rewards) {
      const item = el("li", "", `${r.title} · ${r.cost} πόντοι `);
      const btn = el("button", "points-redeem", "Εξαργύρωση");
      btn.type = "button";
      btn.disabled = state.balance < r.cost;
      btn.addEventListener("click", () => redeem(r, status));
      item.appendChild(btn);
      rewardsList.appendChild(item);
    }
    panel.appendChild(rewardsList);
    panel.appendChild(status);

    if (Array.isArray(state.leaderboard) && state.leaderboard.length > 0) {
      panel.appendChild(el("h2", "", "Κατάταξη Γειτονιών"));
      const lb = el("ul", "points-leaderboard");
      for (const row of state.leaderboard.slice(0, 5)) {
        lb.appendChild(el("li", "", `#${row.rank} ${row.district} · ${row.points} π. (${row.progress_pct}%)`));
      }
      panel.appendChild(lb);
    }
  }

  async function redeem(reward, status) {
    let res;
    try {
      res = await api.redeem(reward.id);
    } catch {
      res = { ok: false, error: "offline" };
    }
    if (res && res.ok) {
      await refresh();
      // Shown after refresh, because renderPanel() rebuilds the status line.
      const s = panel.querySelector(".points-status");
      if (s) s.textContent = `Κωδικός κουπονιού: ${res.voucher_code}`;
    } else {
      status.textContent = res && res.error === "offline"
        ? "Η εξαργύρωση χρειάζεται σύνδεση."
        : "Δεν φτάνουν οι πόντοι για αυτή την ανταμοιβή.";
    }
  }

  async function refresh() {
    const data = await api.points();
    if (data) state = { ...state, ...data };
    if (typeof api.pointsLeaderboard === "function") {
      try {
        const lb = await api.pointsLeaderboard();
        if (lb && Array.isArray(lb.districts)) state.leaderboard = lb.districts;
      } catch {
        // optional leaderboard enhancement
      }
    }
    renderPill();
    if (!panel.hidden) renderPanel();
  }

  let closeTimer = null;
  function setPanelOpen(open) {
    if (closeTimer !== null) {
      clearTimeout(closeTimer);
      closeTimer = null;
    }
    if (open) {
      panel.classList?.remove("is-closing");
      panel.hidden = false;
      pill.setAttribute("aria-expanded", "true");
      renderPanel();
      return;
    }
    pill.setAttribute("aria-expanded", "false");
    if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function" && !panel.hidden) {
      panel.classList?.add("is-closing");
      closeTimer = setTimeout(() => {
        closeTimer = null;
        panel.hidden = true;
        panel.classList?.remove("is-closing");
      }, 200);
    } else {
      panel.classList?.remove("is-closing");
      panel.hidden = true;
    }
  }

  pill.addEventListener("click", () => {
    setPanelOpen(panel.hidden || panel.classList?.contains("is-closing"));
  });

  // points:earned {delta, reason} (A-35): bump the balance now, pulse 600 ms, show a rising «+N».
  bus.addEventListener("points:earned", (event) => {
    const delta = Number(event.detail && event.detail.delta) || 0;
    if (delta === 0) return;
    state.balance += delta;
    renderPill();
    const float = el("span", "points-float", formatDelta(delta));
    float.setAttribute("aria-hidden", "true");
    pill.appendChild(float);
    pill.classList.add("pulse");
    setTimeout(() => {
      pill.classList.remove("pulse");
      float.remove();
    }, PULSE_MS);
  });

  await refresh();
  return { refresh };
}
