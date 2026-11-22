// Transit & routes menu (Wave 1): a collapsible glass panel listing OASA routes (δρομολόγια) with their
// live vehicles, Metro lines Μ1–Μ3 and Suburban lines Α1–Α4. Per-line visibility toggles call
// layers/transit.js setTransitFilter(); "Εντοπισμός" flies the map to a line or to a live bus.
// Appears only while "Τηλεματική ΟΑΣΑ" or "Μετρό/Προαστιακός" is on (listens to "layer:toggle" on the bus)
// and re-renders on "transit:updated".
// Never touches document or maplibregl at import time, and does no network I/O (data comes from the
// transit layer's last api.transit snapshot).

import * as transitLayer from "../layers/transit.js";

// Greek UI strings (certainty: design default, Wave 1 card wording).
export const PILL_LABEL = "🚌 Γραμμές & Δρομολόγια";
export const TITLE = "Συγκοινωνίες & Δρομολόγια";
export const TABS = Object.freeze([
  Object.freeze({ id: "oasa", label: "🚌 ΟΑΣΑ" }),
  Object.freeze({ id: "metro", label: "🚇 Μετρό" }),
  Object.freeze({ id: "suburban", label: "🚆 Προαστιακός" }),
]);

// Camera settings for "Εντοπισμός" (design default; zoom 16 shows a bus with its street name).
const FLY_BUS_ZOOM = 16;
const FLY_DURATION_MS = 900;
const FIT_PADDING_PX = 60;
const FIT_MAX_ZOOM = 15;
// Max live buses listed under the OASA tab, to keep the panel short (design default).
const MAX_LIVE_BUSES = 40;
// Desktop breakpoint above which the panel opens by itself the first time it appears
// (matches the 600 px mobile breakpoint in css/hud.css; design default).
const AUTO_OPEN_MEDIA = "(min-width: 601px)";

const PANEL_ID = "transit-menu-panel";

function provenance(source) {
  const raw = String(source ?? "").trim().toLowerCase();
  if (raw === "live") return { cls: "prov-pill prov-pill--live", text: "LIVE" };
  if (raw === "cache" || raw === "cached" || raw === "snapshot") return { cls: "prov-pill prov-pill--cached", text: "CACHED" };
  if (raw === "mock" || raw === "demo" || raw === "seed") return { cls: "prov-pill prov-pill--demo", text: "DEMO" };
  return null;
}

function busId(feature) {
  return transitLayer.getBusFeatureId(feature);
}

function validBbox(b) {
  return Array.isArray(b) && b.length === 4 && b.every((x) => Number.isFinite(Number(x)));
}

export function initTransitMenu(container, state = {}, { map = null, api = null, bus = null } = {}) {
  if (!container) {
    return null;
  }
  const doc = container.ownerDocument ?? (typeof document !== "undefined" ? document : null);
  if (!doc || typeof doc.createElement !== "function") {
    return null;
  }
  const eventBus = bus ?? state?.bus ?? null;

  const ui = {
    open: false,
    tab: "oasa",
    autoOpened: false,
    hiddenRail: new Set(), // canonical refs ("M1", "A3") the user switched off
    hiddenBus: new Set(), // OASA route codes the user switched off
    refreshing: false,
  };

  // --- small DOM helpers (createElement + textContent only: no HTML injection from data)
  function el(tag, className, text) {
    const node = doc.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function button(className, text, onClick) {
    const b = el("button", className, text);
    b.type = "button";
    if (onClick) b.addEventListener("click", onClick);
    return b;
  }
  function badge(code, color) {
    const b = el("span", "transit-badge", code);
    const bg = /^#[0-9a-f]{6}$/i.test(String(color)) ? color : transitLayer.lineColorForRef(code);
    if (b.style) {
      b.style.background = bg;
      b.style.color = transitLayer.badgeTextColor(bg);
    }
    return b;
  }

  // --- static shell
  container.classList?.add("hud-transit");
  container.replaceChildren?.();

  const pill = button("glass glass-pill transit-menu__pill", PILL_LABEL, () => setOpen(!ui.open));
  pill.setAttribute("aria-expanded", "false");
  pill.setAttribute("aria-controls", PANEL_ID);

  const panel = el("section", "glass transit-menu");
  panel.id = PANEL_ID;
  panel.setAttribute("aria-label", TITLE);
  panel.hidden = true;

  const header = el("div", "transit-menu__header");
  const title = el("h2", "transit-menu__title", TITLE);
  const meta = el("div", "transit-menu__meta");
  const provEl = el("span", "");
  const countEl = el("span", "transit-menu__count");
  const updatedEl = el("span", "prov-updated");
  meta.append?.(provEl, countEl, updatedEl);
  const actions = el("div", "transit-menu__actions");
  const refreshBtn = button("hud-btn transit-menu__icon-btn", "⟳", () => refresh());
  refreshBtn.setAttribute("aria-label", "Ανανέωση");
  refreshBtn.setAttribute("title", "Ανανέωση");
  const collapseBtn = button("hud-btn transit-menu__icon-btn", "✕", () => setOpen(false));
  collapseBtn.setAttribute("aria-label", "Σύμπτυξη");
  collapseBtn.setAttribute("title", "Σύμπτυξη");
  actions.append?.(refreshBtn, collapseBtn);
  header.append?.(title, actions);

  const tablist = el("div", "transit-menu__tabs");
  tablist.setAttribute("role", "tablist");
  tablist.setAttribute("aria-label", "Μέσα μεταφοράς");
  const tabButtons = new Map();
  for (const t of TABS) {
    const tb = button("hud-btn hud-tab transit-menu__tab", t.label, () => selectTab(t.id));
    tb.id = `transit-tab-${t.id}`;
    tb.dataset.tab = t.id;
    tb.setAttribute("role", "tab");
    tb.setAttribute("aria-controls", `${PANEL_ID}-body`);
    tb.addEventListener("keydown", (event) => {
      const idx = TABS.findIndex((x) => x.id === ui.tab);
      let next = -1;
      if (event?.key === "ArrowRight") next = (idx + 1) % TABS.length;
      else if (event?.key === "ArrowLeft") next = (idx - 1 + TABS.length) % TABS.length;
      if (next >= 0) {
        event.preventDefault?.();
        selectTab(TABS[next].id);
        tabButtons.get(TABS[next].id)?.focus?.();
      }
    });
    tabButtons.set(t.id, tb);
    tablist.appendChild(tb);
  }

  const toolbar = el("div", "transit-menu__toolbar");
  const resetBtn = button("hud-btn transit-menu__reset", "Όλες οι γραμμές", () => resetFilters());
  toolbar.appendChild(resetBtn);

  const body = el("div", "transit-menu__body");
  body.id = `${PANEL_ID}-body`;
  body.setAttribute("role", "tabpanel");

  panel.append?.(header, meta, tablist, toolbar, body);
  container.append?.(pill, panel);

  panel.addEventListener?.("keydown", (event) => {
    if (event?.key === "Escape") {
      setOpen(false);
      pill.focus?.();
    }
  });

  // --- state helpers
  function railOn() {
    return Boolean(state?.visible?.[transitLayer.RAIL_ID]);
  }
  function busesOn() {
    return Boolean(state?.visible?.[transitLayer.BUSES_ID]);
  }
  function snapshot() {
    return transitLayer.getLastTransitSnapshot(map);
  }
  function routes() {
    const r = snapshot()?.routes;
    return {
      metro: Array.isArray(r?.metro) ? r.metro : [],
      suburban: Array.isArray(r?.suburban) ? r.suburban : [],
      buses: Array.isArray(r?.buses) ? r.buses : [],
    };
  }
  function liveBuses() {
    if (!busesOn()) return [];
    const fc = snapshot()?.buses;
    return Array.isArray(fc?.features) ? fc.features : [];
  }

  function applyFilter() {
    const r = routes();
    const allRail = [...r.metro, ...r.suburban].map((e) => String(e.ref ?? ""));
    const allBus = r.buses.map((e) => String(e.route_code ?? e.line ?? ""));
    const railLines = ui.hiddenRail.size
      ? allRail.filter((ref) => !ui.hiddenRail.has(transitLayer.canonicalLine(ref)))
      : null;
    const busLines = ui.hiddenBus.size ? allBus.filter((rc) => !ui.hiddenBus.has(rc)) : null;
    transitLayer.setTransitFilter(map, { railLines, busLines });
  }

  function resetFilters() {
    ui.hiddenRail.clear();
    ui.hiddenBus.clear();
    applyFilter();
    render();
  }

  // --- camera actions
  function fitBbox(b) {
    if (!map || !validBbox(b)) return false;
    const [w, s, e, n] = b.map(Number);
    if (typeof map.fitBounds === "function") {
      map.fitBounds(
        [
          [w, s],
          [e, n],
        ],
        { padding: FIT_PADDING_PX, duration: FLY_DURATION_MS, maxZoom: FIT_MAX_ZOOM, essential: true },
      );
      return true;
    }
    if (typeof map.flyTo === "function") {
      map.flyTo({ center: [(w + e) / 2, (s + n) / 2], zoom: 13, duration: FLY_DURATION_MS, essential: true });
      return true;
    }
    return false;
  }

  function flyToBus(feature) {
    const coords = feature?.geometry?.coordinates;
    if (!map || !Array.isArray(coords) || !Number.isFinite(coords[0]) || !Number.isFinite(coords[1])) return false;
    if (typeof map.flyTo === "function") {
      map.flyTo({ center: [coords[0], coords[1]], zoom: FLY_BUS_ZOOM, duration: FLY_DURATION_MS, essential: true });
    }
    transitLayer.openBusPopup(map, feature);
    return true;
  }

  function locateRail(entry) {
    const key = transitLayer.canonicalLine(entry.ref);
    if (ui.hiddenRail.delete(key)) {
      applyFilter();
      render();
    }
    fitBbox(entry.bbox);
  }

  function locateRoute(entry) {
    const rc = String(entry.route_code ?? entry.line ?? "");
    if (ui.hiddenBus.delete(rc)) {
      applyFilter();
      render();
    }
    const first = liveBuses().find((f) => {
      const p = f?.properties || {};
      return String(p.route_code ?? p.line ?? "") === rc;
    });
    if (first && flyToBus(first)) return;
    fitBbox(entry.bbox);
  }

  // --- rendering
  let focusables = new Map();

  function toggleChip(key, checked, label, onChange) {
    const wrap = el("label", "transit-menu__toggle");
    const input = el("input", "");
    input.type = "checkbox";
    input.checked = checked;
    input.dataset.focusKey = key;
    input.addEventListener("change", () => onChange(Boolean(input.checked)));
    focusables.set(key, input);
    const text = el("span", "transit-menu__sr", label);
    wrap.append?.(input, text);
    return wrap;
  }

  function locateButton(key, label, onClick) {
    const b = button("hud-btn transit-menu__locate", "Εντοπισμός", onClick);
    b.setAttribute("aria-label", `Εντοπισμός: ${label}`);
    b.dataset.focusKey = key;
    focusables.set(key, b);
    return b;
  }

  function hint(text) {
    return el("p", "transit-menu__hint", text);
  }

  function renderRailList(entries, emptyText) {
    const frag = el("div", "transit-menu__section");
    if (!railOn()) {
      frag.appendChild(hint("Ενεργοποιήστε «Μετρό/Προαστιακός» για να δείτε τις γραμμές στον χάρτη."));
    }
    if (entries.length === 0) {
      frag.appendChild(hint(emptyText));
      return frag;
    }
    const ul = el("ul", "transit-menu__list");
    for (const entry of entries) {
      const ref = String(entry.ref ?? "");
      const key = transitLayer.canonicalLine(ref);
      const li = el("li", "transit-menu__item");
      const visible = !ui.hiddenRail.has(key);
      li.classList?.toggle("is-muted", !visible);
      li.appendChild(badge(ref, entry.color));
      const info = el("div", "transit-menu__info");
      info.appendChild(el("span", "transit-menu__name", entry.name || ref));
      const count = Number(entry.station_count);
      info.appendChild(
        el("span", "transit-menu__sub", Number.isFinite(count) && count > 0 ? `${count} σταθμοί` : "σταθμοί: άγνωστο"),
      );
      li.appendChild(info);
      li.appendChild(
        toggleChip(`rail-toggle-${key}`, visible, `Εμφάνιση ${ref}`, (on) => {
          if (on) ui.hiddenRail.delete(key);
          else ui.hiddenRail.add(key);
          applyFilter();
          render();
        }),
      );
      li.appendChild(locateButton(`rail-locate-${key}`, entry.name || ref, () => locateRail(entry)));
      ul.appendChild(li);
    }
    frag.appendChild(ul);
    return frag;
  }

  function renderOasa() {
    const wrap = el("div", "transit-menu__section");
    const r = routes();
    const buses = liveBuses();
    if (!busesOn()) {
      wrap.appendChild(hint("Ενεργοποιήστε «Τηλεματική ΟΑΣΑ» για ζωντανές θέσεις οχημάτων."));
    }

    wrap.appendChild(el("h3", "transit-menu__subtitle", "Δρομολόγια"));
    if (r.buses.length === 0) {
      wrap.appendChild(hint("Δεν υπάρχουν διαθέσιμα δρομολόγια."));
    } else {
      const ul = el("ul", "transit-menu__list");
      for (const entry of r.buses) {
        const rc = String(entry.route_code ?? entry.line ?? "");
        const line = String(entry.line ?? rc);
        const li = el("li", "transit-menu__item");
        const visible = !ui.hiddenBus.has(rc);
        li.classList?.toggle("is-muted", !visible);
        li.appendChild(badge(line, transitLayer.busColorForMode(entry.mode)));
        const info = el("div", "transit-menu__info");
        info.appendChild(el("span", "transit-menu__name", entry.name || `Γραμμή ${line}`));
        const live = busesOn()
          ? buses.filter((f) => String(f?.properties?.route_code ?? f?.properties?.line ?? "") === rc).length
          : null;
        const sub = entry.mode === "trolley" ? "Τρόλεϊ" : "Λεωφορείο";
        info.appendChild(
          el("span", "transit-menu__sub", live === null ? sub : `${sub} · ${live} ενεργά οχήματα`),
        );
        li.appendChild(info);
        li.appendChild(
          toggleChip(`bus-toggle-${rc}`, visible, `Εμφάνιση ${line} ${entry.name || ""}`.trim(), (on) => {
            if (on) ui.hiddenBus.delete(rc);
            else ui.hiddenBus.add(rc);
            applyFilter();
            render();
          }),
        );
        li.appendChild(locateButton(`bus-locate-${rc}`, `${line} ${entry.name || ""}`.trim(), () => locateRoute(entry)));
        ul.appendChild(li);
      }
      wrap.appendChild(ul);
    }

    if (busesOn()) {
      wrap.appendChild(el("h3", "transit-menu__subtitle", "Ζωντανά οχήματα"));
      const shown = buses.filter((f) => {
        const p = f?.properties || {};
        return !ui.hiddenBus.has(String(p.route_code ?? p.line ?? ""));
      });
      if (shown.length === 0) {
        wrap.appendChild(hint("Κανένα ενεργό όχημα στην περιοχή αυτή τη στιγμή."));
      } else {
        const ul = el("ul", "transit-menu__list transit-menu__list--buses");
        for (const f of shown.slice(0, MAX_LIVE_BUSES)) {
          const p = f?.properties || {};
          const idKey = busId(f) ?? "";
          const li = el("li", "transit-menu__item");
          const b = button("transit-menu__bus", null, () => flyToBus(f));
          b.dataset.focusKey = `bus-live-${idKey}`;
          focusables.set(`bus-live-${idKey}`, b);
          b.appendChild(badge(String(p.line ?? "?"), transitLayer.busColorForMode(p.mode)));
          const info = el("span", "transit-menu__info");
          info.appendChild(el("span", "transit-menu__name", p.route_name || "Δρομολόγιο: άγνωστο"));
          const time = transitLayer.formatTimeEl(p.updated_at);
          info.appendChild(
            el("span", "transit-menu__sub", `Όχημα ${p.vehicle_id || "άγνωστο"}${time ? ` · ${time}` : ""}`),
          );
          b.appendChild(info);
          b.setAttribute(
            "aria-label",
            `Εντοπισμός οχήματος ${p.vehicle_id || ""} γραμμής ${p.line || ""} ${p.route_name || ""}`.replace(/\s+/g, " ").trim(),
          );
          li.appendChild(b);
          ul.appendChild(li);
        }
        wrap.appendChild(ul);
      }
    }
    return wrap;
  }

  function renderMeta() {
    const snap = snapshot();
    const prov = snap ? provenance(snap.source) : null;
    provEl.className = prov ? prov.cls : "";
    provEl.textContent = prov ? prov.text : "";
    provEl.hidden = !prov;
    countEl.textContent = busesOn() ? `${liveBuses().length} ενεργά οχήματα` : "";
    const time = snap?.updated_at ? transitLayer.formatTimeEl(snap.updated_at) : "";
    updatedEl.textContent = time ? `Ενημέρωση ${time}` : "";
  }

  function render() {
    const activeKey = doc.activeElement?.dataset?.focusKey ?? null;
    focusables = new Map();

    for (const [tid, tb] of tabButtons) {
      const selected = tid === ui.tab;
      tb.setAttribute("aria-selected", String(selected));
      tb.setAttribute("tabindex", selected ? "0" : "-1");
      tb.classList?.toggle("is-active", selected);
    }
    body.setAttribute("aria-labelledby", `transit-tab-${ui.tab}`);
    renderMeta();
    resetBtn.disabled = ui.hiddenRail.size === 0 && ui.hiddenBus.size === 0;

    let content;
    if (!snapshot()) {
      content = hint("Φόρτωση γραμμών…");
    } else if (ui.tab === "metro") {
      content = renderRailList(routes().metro, "Δεν βρέθηκαν γραμμές Μετρό.");
    } else if (ui.tab === "suburban") {
      content = renderRailList(routes().suburban, "Δεν βρέθηκαν γραμμές Προαστιακού.");
    } else {
      content = renderOasa();
    }
    body.replaceChildren?.(content);

    // Keep keyboard focus on the same control across the 20 s re-render.
    if (activeKey && focusables.has(activeKey)) {
      focusables.get(activeKey).focus?.();
    }
  }

  function selectTab(tabId) {
    if (!TABS.some((t) => t.id === tabId)) return;
    ui.tab = tabId;
    render();
  }

  function setOpen(open) {
    ui.open = Boolean(open);
    panel.hidden = !ui.open;
    pill.setAttribute("aria-expanded", String(ui.open));
    container.classList?.toggle("is-open", ui.open);
    if (ui.open) render();
  }

  function syncVisibility(changedId = null, nowVisible = false) {
    const show = railOn() || busesOn();
    container.hidden = !show;
    container.classList?.toggle("is-hidden", !show);
    if (!show) {
      setOpen(false);
      return;
    }
    // Jump to the tab of the layer that was just switched on.
    if (nowVisible && changedId === transitLayer.BUSES_ID) ui.tab = "oasa";
    if (nowVisible && changedId === transitLayer.RAIL_ID && ui.tab === "oasa" && !busesOn()) ui.tab = "metro";
    if (!ui.autoOpened && nowVisible) {
      ui.autoOpened = true;
      const wide = typeof globalThis.matchMedia === "function" && globalThis.matchMedia(AUTO_OPEN_MEDIA)?.matches;
      if (wide) {
        setOpen(true);
        return;
      }
    }
    if (ui.open) render();
  }

  async function refresh() {
    if (ui.refreshing) return;
    ui.refreshing = true;
    refreshBtn.setAttribute("aria-busy", "true");
    refreshBtn.disabled = true;
    try {
      await transitLayer.triggerTransitRefresh(map, api, state);
    } finally {
      ui.refreshing = false;
      refreshBtn.removeAttribute?.("aria-busy");
      refreshBtn.disabled = false;
      if (ui.open) render();
    }
  }

  // --- wiring
  const onToggle = (event) => {
    const id = event?.detail?.id;
    if (id !== transitLayer.BUSES_ID && id !== transitLayer.RAIL_ID) return;
    syncVisibility(id, Boolean(event?.detail?.visible));
  };
  const onUpdated = () => {
    // Re-apply the user's filter so new routes from a fresh snapshot follow it.
    if (ui.hiddenRail.size || ui.hiddenBus.size) applyFilter();
    if (ui.open) render();
    else renderMeta();
  };
  if (eventBus && typeof eventBus.addEventListener === "function") {
    eventBus.addEventListener("layer:toggle", onToggle);
    eventBus.addEventListener("transit:updated", onUpdated);
  }

  syncVisibility();
  render();

  return {
    pill,
    panel,
    open: () => setOpen(true),
    close: () => setOpen(false),
    isOpen: () => ui.open,
    selectTab,
    refresh,
    render,
    sync: () => syncVisibility(),
    destroy() {
      if (eventBus && typeof eventBus.removeEventListener === "function") {
        eventBus.removeEventListener("layer:toggle", onToggle);
        eventBus.removeEventListener("transit:updated", onUpdated);
      }
      container.replaceChildren?.();
    },
  };
}
