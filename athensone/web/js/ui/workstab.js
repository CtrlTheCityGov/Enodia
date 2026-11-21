// B10: Works tab (SPEC F8, HUD «Πάνω αριστερά», Demo script step 6).
// Top-left «Χάρτης» / «Έργα» tabs, a .glass panel listing works from api.works(),
// status filter chips, accent-insensitive search, Diavgeia link vs SEED badge,
// map-focus (map:flyto) and crowdsourced progress reporting (report:open).
// Follows A-35: export mount({map, api, root, bus}). No fetch, DOM or maplibregl at import time.

// Status filter chips in card order with Greek labels. Source: docs/TASKS_B.md B10. Certainty: verified.
export const STATUS_FILTERS = [
  { id: "all", label: "Όλα" },
  { id: "in_progress", label: "Σε εξέλιξη" },
  { id: "planned", label: "Προγραμματισμένα" },
  { id: "completed", label: "Ολοκληρωμένα" },
];

// Greek labels for each work's status field. Source: docs/SPEC.md «Φούσκα έργου», docs/TASKS_B.md B10. Certainty: verified.
const STATUS_LABELS = {
  planned: "Προγραμματισμένο",
  in_progress: "Σε εξέλιξη",
  completed: "Ολοκληρωμένο",
};

// Placeholder for missing/unknown values (never 0). Source: CLAUDE.md «Trust rules», docs/TASKS_B.md B10. Certainty: verified.
const UNKNOWN_LABEL = "άγνωστο";

// Diavgeia public decision URL prefix. Source: docs/SPEC.md «Φούσκα έργου», docs/TASKS_B.md B10. Certainty: verified.
const DIAVGEIA_BASE = "https://diavgeia.gov.gr/decision/view/";

// ADA prefix marking synthetic SEED works. Source: docs/TASKS_B.md B0 & B10. Certainty: verified.
const SEED_ADA_PREFIX = "SEED-";

// Badge label for synthetic SEED works. Source: CLAUDE.md «Mock data is labelled», docs/TASKS_B.md B10. Certainty: verified.
const SEED_BADGE = "SEED · δοκιμαστικό";

// Badge text per non-live data source. Source: CLAUDE.md «Mock data is labelled». Certainty: verified.
const SOURCE_BADGE = {
  mock: "δοκιμαστικό",
  cache: "Offline λειτουργία",
};

// Greek number formatting for EUR amounts. Standard BCP-47 locale "el-GR". Certainty: verified.
const EUR_FORMAT = new Intl.NumberFormat("el-GR", { maximumFractionDigits: 2 });

/** Normalize text for accent- and case-insensitive Greek/Latin matching (final sigma unified). */
function normalizeText(text) {
  return String(text ?? "")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/ς/g, "σ")
    .replace(/\s+/g, " ")
    .trim();
}

function nonEmptyString(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function isSeedWork(props) {
  if (!props || typeof props !== "object") return false;
  if (props.seed) return true;
  const ada = nonEmptyString(props.ada);
  return Boolean(ada && ada.toUpperCase().startsWith(SEED_ADA_PREFIX));
}

function formatEur(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return UNKNOWN_LABEL;
  return `${EUR_FORMAT.format(value)} €`;
}

/** Return the Diavgeia decision URL for a real ADA, or null for SEED / missing / malformed ADAs. */
export function diavgeiaLink(props) {
  if (!props || typeof props !== "object") return null;
  if (isSeedWork(props)) return null;
  const ada = nonEmptyString(props.ada);
  if (!ada || /[\s/?#]/.test(ada)) return null;
  return `${DIAVGEIA_BASE}${ada}`;
}

function lineMidpoint(coords) {
  if (!Array.isArray(coords)) return null;
  const pts = coords.filter(
    (p) => Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]),
  );
  if (pts.length === 0) return null;
  if (pts.length === 1) return [pts[0][0], pts[0][1]];

  const segLens = [];
  let total = 0;
  for (let i = 0; i < pts.length - 1; i += 1) {
    const len = Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]);
    segLens.push(len);
    total += len;
  }
  if (total === 0) return [pts[0][0], pts[0][1]];

  const half = total / 2;
  let acc = 0;
  for (let i = 0; i < segLens.length; i += 1) {
    const len = segLens[i];
    if (acc + len >= half && len > 0) {
      const t = (half - acc) / len;
      return [
        pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t,
        pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t,
      ];
    }
    acc += len;
  }
  const last = pts[pts.length - 1];
  return [last[0], last[1]];
}

/** Return the [lon, lat] midpoint of a GeoJSON LineString (also handles Point and MultiLineString). */
export function workMidpoint(geometry) {
  if (!geometry || typeof geometry !== "object") return null;
  if (geometry.type === "LineString") return lineMidpoint(geometry.coordinates);
  if (geometry.type === "Point") {
    const c = geometry.coordinates;
    if (Array.isArray(c) && c.length >= 2 && Number.isFinite(c[0]) && Number.isFinite(c[1])) {
      return [c[0], c[1]];
    }
    return null;
  }
  if (geometry.type === "MultiLineString" && Array.isArray(geometry.coordinates)) {
    let bestLine = null;
    let bestLen = -1;
    for (const line of geometry.coordinates) {
      if (!Array.isArray(line) || line.length === 0) continue;
      let len = 0;
      for (let i = 0; i < line.length - 1; i += 1) {
        if (Array.isArray(line[i]) && Array.isArray(line[i + 1])) {
          len += Math.hypot(line[i + 1][0] - line[i][0], line[i + 1][1] - line[i][1]);
        }
      }
      if (len > bestLen) {
        bestLen = len;
        bestLine = line;
      }
    }
    return bestLine ? lineMidpoint(bestLine) : null;
  }
  return null;
}

/** Filter work GeoJSON features by status and accent-/case-insensitive query on title, contractor, ada. */
export function filterWorks(features, { status = "all", query = "" } = {}) {
  if (!Array.isArray(features)) return [];
  const wantedStatus = status && status !== "all" ? status : null;
  const needle = normalizeText(query);

  return features.filter((feature) => {
    const props = feature?.properties || {};
    if (wantedStatus && props.status !== wantedStatus) return false;
    if (!needle) return true;
    const haystack = [props.title, props.contractor, props.ada]
      .filter((v) => typeof v === "string" && v.length > 0)
      .map(normalizeText);
    return haystack.some((field) => field.includes(needle));
  });
}

/** Format one work GeoJSON feature into display-ready fields. Missing values show «άγνωστο», never 0. */
export function formatWorkCard(feature) {
  const props = feature?.properties || {};
  const isSeed = isSeedWork(props);
  const amountPaid = formatEur(props.amount_paid_eur);
  const amountContract = formatEur(props.amount_contract_eur);
  const reportsCount =
    typeof props.reports_count === "number" && Number.isFinite(props.reports_count)
      ? props.reports_count
      : UNKNOWN_LABEL;

  return {
    id: nonEmptyString(props.id) ?? "",
    title: nonEmptyString(props.title) ?? UNKNOWN_LABEL,
    status: nonEmptyString(props.status),
    statusLabel: STATUS_LABELS[props.status] || UNKNOWN_LABEL,
    contractor: nonEmptyString(props.contractor) ?? UNKNOWN_LABEL,
    amountPaid,
    amountContract,
    amountSummary: `${amountPaid} / ${amountContract}`,
    ada: nonEmptyString(props.ada) ?? UNKNOWN_LABEL,
    adaUrl: diavgeiaLink(props),
    isSeed,
    seedBadge: isSeed ? SEED_BADGE : null,
    reportsCount,
    midpoint: workMidpoint(feature?.geometry),
  };
}

// ---------------------------------------------------------------- UI (browser / fake DOM, called by main.js)

/** Mount the top-left «Χάρτης» / «Έργα» tabs and glass works panel into ctx.root (A-35). */
export async function mount({ map, api, root, container, bus }) {
  root = container || root;
  const doc = root.ownerDocument || globalThis.document;
  const el = (tag, attrs = {}, text) => {
    const node = doc.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") node.className = String(v);
      else if (k === "type") node.type = String(v);
      else if (k === "hidden") node.hidden = true;
      else node.setAttribute(k, String(v));
    }
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const state = {
    open: false,
    status: "all",
    query: "",
    features: [],
    source: null,
    loading: false,
    error: null,
  };

  // --- Top-left pill bar: «Χάρτης» / «Έργα» tabs (SPEC HUD «Πάνω αριστερά»)
  // Reuse existing #tab-map / #tab-works buttons if citizen.html already rendered them in #hud-tabs.
  const existingMapTab = root.querySelector?.("#tab-map") || doc.getElementById?.("tab-map") || null;
  const existingWorksTab = root.querySelector?.("#tab-works") || doc.getElementById?.("tab-works") || null;
  const hasExistingTabs = Boolean(existingMapTab && existingWorksTab);

  const tablist = el("div", { class: "glass workstab-tabs", role: "tablist", "aria-label": "Προβολή" });
  const mapTab = existingMapTab || el(
    "button",
    {
      type: "button",
      role: "tab",
      id: "workstab-tab-map",
      class: "workstab-tab is-active",
      tabindex: "0",
      "aria-selected": "true",
      "aria-controls": "workstab-panel",
    },
    "Χάρτης",
  );
  const worksTab = existingWorksTab || el(
    "button",
    {
      type: "button",
      role: "tab",
      id: "workstab-tab-works",
      class: "workstab-tab",
      tabindex: "-1",
      "aria-selected": "false",
      "aria-controls": "workstab-panel",
    },
    "Έργα",
  );
  if (!hasExistingTabs) {
    tablist.append(mapTab, worksTab);
  }

  // --- Glass panel with filters, search, status line, and works list
  const panel = el("section", {
    id: "workstab-panel",
    class: "glass workstab-panel",
    role: "tabpanel",
    "aria-labelledby": "workstab-tab-works",
    hidden: true,
  });

  const header = el("div", { class: "workstab-header" });
  const heading = el("h2", { class: "workstab-heading" }, "Έργα Δήμου Αθηναίων");
  const sourceBadge = el("span", { class: "workstab-source" }, "");
  header.append(heading, sourceBadge);

  const filterBar = el("div", {
    class: "workstab-filters",
    role: "group",
    "aria-label": "Φίλτρο κατάστασης έργων",
  });
  const filterButtons = new Map();
  for (const f of STATUS_FILTERS) {
    const btn = el(
      "button",
      {
        type: "button",
        class: f.id === state.status ? "workstab-filter is-active" : "workstab-filter",
        "data-status": f.id,
        "aria-pressed": String(f.id === state.status),
      },
      f.label,
    );
    btn.addEventListener("click", () => {
      state.status = f.id;
      for (const [id, b] of filterButtons.entries()) {
        const active = id === state.status;
        b.setAttribute("aria-pressed", String(active));
        b.classList.toggle("is-active", active);
      }
      renderList();
    });
    filterButtons.set(f.id, btn);
    filterBar.append(btn);
  }

  const searchWrap = el("div", { class: "workstab-search-wrap" });
  const searchLabel = el("label", { class: "workstab-search-label", for: "workstab-search" }, "Αναζήτηση");
  const searchInput = el("input", {
    id: "workstab-search",
    type: "search",
    class: "workstab-search",
    "aria-label": "Αναζήτηση έργου κατά τίτλο, ανάδοχο ή ΑΔΑ",
  });
  searchInput.placeholder = "Οδός, ανάδοχος ή ΑΔΑ…";
  searchInput.addEventListener("input", () => {
    state.query = searchInput.value;
    renderList();
  });
  searchWrap.append(searchLabel, searchInput);

  const statusLine = el("p", { class: "workstab-status", role: "status", "aria-live": "polite" }, "");
  const list = el("ul", { class: "workstab-list" });

  panel.append(header, filterBar, searchWrap, statusLine, list);
  if (hasExistingTabs) {
    root.append(panel);
  } else {
    root.append(tablist, panel);
  }

  function renderCard(feature) {
    const card = formatWorkCard(feature);
    const item = el("li", { class: "workstab-card" });

    const top = el("div", { class: "workstab-card-top" });
    top.append(
      el("h3", { class: "workstab-card-title" }, card.title),
      el("span", { class: `workstab-status-badge status-${card.status || "unknown"}` }, card.statusLabel),
    );

    const meta = el("dl", { class: "workstab-card-meta" });
    meta.append(
      el("dt", {}, "Ανάδοχος"),
      el("dd", {}, card.contractor),
      el("dt", {}, "Πληρωμένα / Σύμβαση"),
      el("dd", {}, card.amountSummary),
      el("dt", {}, "ΑΔΑ"),
    );

    const adaDd = el("dd", {});
    if (card.adaUrl) {
      const link = el("a", { class: "workstab-ada-link" }, card.ada);
      link.href = card.adaUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      adaDd.append(link);
    } else if (card.isSeed) {
      adaDd.append(
        el("span", { class: "workstab-ada-code" }, `${card.ada} `),
        el("span", { class: "workstab-seed-badge" }, card.seedBadge),
      );
    } else {
      adaDd.textContent = card.ada;
    }
    meta.append(
      adaDd,
      el("dt", {}, "Αναφορές πολιτών"),
      el("dd", {}, String(card.reportsCount)),
    );

    const actions = el("div", { class: "workstab-card-actions" });

    const focusBtn = el(
      "button",
      {
        type: "button",
        class: "workstab-focus",
        "aria-label": `Εμφάνιση στον χάρτη: ${card.title}`,
      },
      "Εμφάνιση στον χάρτη",
    );
    focusBtn.disabled = !card.midpoint;
    focusBtn.addEventListener("click", () => {
      if (!card.midpoint) return;
      bus?.dispatchEvent(
        new CustomEvent("map:flyto", {
          detail: { lon: card.midpoint[0], lat: card.midpoint[1], label: card.title },
        }),
      );
      setOpen(false);
    });

    const reportBtn = el(
      "button",
      {
        type: "button",
        class: "workstab-report",
        "aria-label": `Ανέφερε πρόοδο για ${card.title}`,
      },
      "Ανέφερε πρόοδο",
    );
    reportBtn.addEventListener("click", () => {
      const lngLat = card.midpoint
        ? { lng: card.midpoint[0], lat: card.midpoint[1] }
        : map?.getCenter?.() || null;
      bus?.dispatchEvent(
        new CustomEvent("report:open", {
          detail: { work_id: card.id, lngLat },
        }),
      );
      setOpen(false);
    });

    actions.append(focusBtn, reportBtn);
    item.append(top, meta, actions);
    return item;
  }

  function renderList() {
    sourceBadge.textContent = SOURCE_BADGE[state.source] || "";
    if (state.loading) {
      statusLine.textContent = "Φόρτωση έργων…";
      list.replaceChildren();
      return;
    }
    if (state.error) {
      statusLine.textContent = state.error;
      list.replaceChildren();
      return;
    }
    const filtered = filterWorks(state.features, { status: state.status, query: state.query });
    if (filtered.length === 0) {
      statusLine.textContent = "Δεν βρέθηκαν έργα με αυτά τα φίλτρα.";
    } else if (filtered.length === 1) {
      statusLine.textContent = "1 έργο";
    } else {
      statusLine.textContent = `${filtered.length} έργα`;
    }
    list.replaceChildren(...filtered.map(renderCard));
  }

  let loadSeq = 0;

  async function refresh() {
    const seq = ++loadSeq;
    state.loading = true;
    state.error = null;
    renderList();
    try {
      const data = await api.works();
      if (seq !== loadSeq) return;
      state.features = Array.isArray(data?.features) ? data.features : [];
      state.source = data?.source ?? null;
    } catch {
      if (seq !== loadSeq) return;
      state.error = "Δεν ήταν δυνατή η φόρτωση των έργων.";
    } finally {
      if (seq === loadSeq) {
        state.loading = false;
        renderList();
      }
    }
  }

  function setOpen(next) {
    state.open = Boolean(next);
    panel.hidden = !state.open;
    mapTab.setAttribute("aria-selected", String(!state.open));
    mapTab.setAttribute("tabindex", state.open ? "-1" : "0");
    mapTab.classList.toggle("is-active", !state.open);
    worksTab.setAttribute("aria-selected", String(state.open));
    worksTab.setAttribute("tabindex", state.open ? "0" : "-1");
    worksTab.classList.toggle("is-active", state.open);
  }

  mapTab.addEventListener("click", () => setOpen(false));
  worksTab.addEventListener("click", () => {
    setOpen(true);
    refresh();
  });

  tablist.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      if (state.open) {
        setOpen(false);
        mapTab.focus();
      } else {
        setOpen(true);
        worksTab.focus();
        refresh();
      }
    }
  });

  root.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.open) {
      setOpen(false);
      mapTab.focus();
    }
  });

  return {
    open: async () => {
      setOpen(true);
      await refresh();
    },
    close: () => setOpen(false),
    refresh,
  };
}
