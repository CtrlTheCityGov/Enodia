// Citizen Reports Feed tab ("Αναφορές"): Live scrollable feed of citizen reports with fly-to map focus.
// Follows A-35: export mount({map, api, root, container, bus}). No fetch, DOM, or maplibregl at import time.

const CATEGORY_LABELS = {
  pothole: "🕳️ Λακκούβα",
  sidewalk: "🚶 Πεζοδρόμιο",
  obstacle: "🚧 Εμπόδιο",
  congestion: "🚗 Συμφόρηση",
  lighting: "💡 Φωτισμός",
  streetlight: "💡 Φωτισμός",
  water_leak: "💧 Διαρροή νερού",
  trash: "🗑️ Απορρίμματα",
  damage: "⚠️ Φθορά",
};

const STATUS_LABELS = {
  submitted: "Ανοιχτή",
  open: "Ανοιχτή",
  acknowledged: "Ανατέθηκε",
  in_progress: "Σε εξέλιξη",
  resolved: "Επιλύθηκε",
};

export async function mount({ api, root, container, bus }) {
  root = container || root;
  if (!root) return {};
  const doc = root.ownerDocument || globalThis.document;
  const el = (tag, props = {}, text) => {
    const node = doc.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") node.className = v;
      else node.setAttribute(k, String(v));
    }
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const panel = el("section", {
    id: "reports-feed-panel",
    class: "glass workstab-panel",
    role: "tabpanel",
    "aria-labelledby": "tab-reports-feed",
    hidden: "true",
  });
  panel.hidden = true;

  const header = el("div", { class: "workstab-header" });
  const heading = el("h2", { class: "workstab-heading" }, "Ροή Αναφορών Πολιτών");
  const countBadge = el("span", { class: "workstab-source" }, "");
  const closeBtn = el("button", { type: "button", class: "overlay-close-btn", "aria-label": "Κλείσιμο" }, "×");
  closeBtn.addEventListener("click", () => {
    const mTab = doc.getElementById?.("tab-map");
    if (mTab && typeof mTab.click === "function") mTab.click();
    else bus?.dispatchEvent?.(new CustomEvent("tab:change", { detail: { tab: "map" } }));
  });
  header.append(heading, countBadge, closeBtn);

  const filterBar = el("div", { class: "workstab-filters", role: "group", "aria-label": "Φίλτρο αναφορών" });
  const filters = [
    { id: "all", label: "Όλες" },
    { id: "open", label: "Ανοιχτές" },
    { id: "in_progress", label: "Σε εξέλιξη" },
    { id: "resolved", label: "Επιλυμένες" },
  ];
  let activeFilter = "all";
  let features = [];
  const filterBtns = new Map();
  const list = el("ul", { class: "workstab-list" });
  const emptyMsg = el("p", { class: "workstab-empty" }, "Δεν υπάρχουν αναφορές.");
  emptyMsg.hidden = true;

  function renderList() {
    list.textContent = "";
    const filtered = features.filter((f) => {
      if (activeFilter === "all") return true;
      const st = String(f?.properties?.status || "submitted").toLowerCase();
      if (activeFilter === "open") return st === "submitted" || st === "open" || st === "acknowledged";
      return st === activeFilter;
    });
    countBadge.textContent = `${filtered.length} αναφορές`;
    emptyMsg.hidden = filtered.length > 0;
    for (const f of filtered) {
      const p = f.properties || {};
      const coords = f.geometry?.coordinates || [];
      const li = el("li", { class: "workstab-card" });
      const top = el("div", { class: "notice-card-top" });
      const cat = el("strong", {}, CATEGORY_LABELS[p.category] || p.category || "Αναφορά");
      const stKey = String(p.status || "submitted").toLowerCase();
      const st = el("span", { class: "notice-badge" }, STATUS_LABELS[stKey] || stKey);
      top.append(cat, st);

      const desc = el("p", { class: "notice-summary" }, p.description || p.note || "Αναφορά πολίτη στον χάρτη.");
      const meta = el("div", { class: "workstab-status" }, [p.address || p.neighborhood || "", p.created_at ? String(p.created_at).slice(0, 10) : ""].filter(Boolean).join(" · "));
      li.append(top, desc, meta);

      if (coords.length >= 2) {
        const actions = el("div", { class: "notice-actions" });
        const fly = el("button", { type: "button", class: "workstab-filter" }, "Εντοπισμός στον χάρτη");
        fly.addEventListener("click", () => {
          bus?.dispatchEvent?.(new CustomEvent("map:flyto", { detail: { lon: coords[0], lat: coords[1], zoom: 17 } }));
          const mTab = doc.getElementById?.("tab-map");
          if (mTab && typeof mTab.click === "function") mTab.click();
        });
        actions.append(fly);
        li.append(actions);
      }
      list.append(li);
    }
  }

  for (const f of filters) {
    const b = el("button", {
      type: "button",
      class: f.id === activeFilter ? "workstab-filter is-active" : "workstab-filter",
      "aria-pressed": String(f.id === activeFilter),
    }, f.label);
    b.addEventListener("click", () => {
      activeFilter = f.id;
      for (const [id, btn] of filterBtns.entries()) {
        const on = id === activeFilter;
        btn.setAttribute("aria-pressed", String(on));
        btn.classList.toggle("is-active", on);
      }
      renderList();
    });
    filterBtns.set(f.id, b);
    filterBar.append(b);
  }

  panel.append(header, filterBar, emptyMsg, list);
  const host = root.parentElement || doc.querySelector?.(".hud") || root;
  host.appendChild(panel);

  async function loadReports() {
    try {
      const res = typeof api?.reports === "function" ? await api.reports() : null;
      const raw = Array.isArray(res?.features) ? res.features : [];
      features = [...raw].sort((a, b) => String(b?.properties?.created_at || "").localeCompare(String(a?.properties?.created_at || "")));
      renderList();
    } catch {
      emptyMsg.hidden = false;
    }
  }

  bus?.addEventListener?.("tab:change", (e) => {
    const open = e?.detail?.tab === "reports-feed";
    panel.hidden = !open;
    if (open) loadReports();
  });
  bus?.addEventListener?.("report:created", () => loadReports());
  bus?.addEventListener?.("reports:changed", () => loadReports());

  return { refresh: loadReports };
}
