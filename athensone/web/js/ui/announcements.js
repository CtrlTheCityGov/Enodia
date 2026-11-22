// Noticeboard tab ("Ανακοινώσεις"): Protests/strikes (apergia.gr) and Municipality of Athens civic events.
// Follows A-35: export mount({map, api, root, container, bus}). No fetch, DOM, or maplibregl at import time.

const SOURCE_BADGE = {
  live: "LIVE · apergia.gr",
  snapshot: "CACHED",
  cache: "CACHED",
  mock: "DEMO",
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
    id: "announcements-panel",
    class: "glass workstab-panel",
    role: "tabpanel",
    "aria-labelledby": "tab-announcements",
    hidden: "true",
  });
  panel.hidden = true;

  const header = el("div", { class: "workstab-header" });
  const heading = el("h2", { class: "workstab-heading" }, "Πίνακας Ανακοινώσεων");
  const sourceBadge = el("span", { class: "workstab-source" }, "");
  const closeBtn = el("button", { type: "button", class: "overlay-close-btn", "aria-label": "Κλείσιμο" }, "×");
  closeBtn.addEventListener("click", () => {
    const mTab = doc.getElementById?.("tab-map");
    if (mTab && typeof mTab.click === "function") mTab.click();
    else bus?.dispatchEvent?.(new CustomEvent("tab:change", { detail: { tab: "map" } }));
  });
  header.append(heading, sourceBadge, closeBtn);

  const filterBar = el("div", { class: "workstab-filters", role: "group", "aria-label": "Φίλτρο ανακοινώσεων" });
  const filters = [
    { id: "all", label: "Όλα" },
    { id: "protest", label: "Πορείες / Απεργίες" },
    { id: "event", label: "Εκδηλώσεις Δήμου" },
  ];
  let activeFilter = "all";
  let items = [];
  const filterBtns = new Map();

  const list = el("ul", { class: "workstab-list" });
  const emptyMsg = el("p", { class: "workstab-empty" }, "Φόρτωση ανακοινώσεων…");
  emptyMsg.hidden = true;

  function renderList() {
    list.textContent = "";
    const filtered = activeFilter === "all" ? items : items.filter((it) => it.kind === activeFilter);
    emptyMsg.hidden = filtered.length > 0;
    if (filtered.length === 0) {
      emptyMsg.textContent = "Δεν υπάρχουν ανακοινώσεις σε αυτή την κατηγορία.";
      return;
    }
    for (const it of filtered) {
      const li = el("li", { class: "workstab-card" });
      const top = el("div", { class: "notice-card-top" });
      const badge = el(
        "span",
        { class: it.kind === "protest" ? "notice-badge notice-badge--protest" : "notice-badge notice-badge--event" },
        it.kind === "protest" ? "Πορεία / Απεργία" : "Δήμος Αθηναίων",
      );
      const when = el("span", { class: "workstab-status" }, [it.date, it.time].filter(Boolean).join(" · "));
      top.append(badge, when);

      const title = el("strong", {}, it.title || "Ανακοίνωση");
      const loc = el("div", { class: "workstab-status" }, it.location || "");
      const summary = el("p", { class: "notice-summary" }, it.summary || "");
      const actions = el("div", { class: "notice-actions" });

      if (typeof it.lat === "number" && typeof it.lng === "number") {
        const fly = el("button", { type: "button", class: "workstab-filter" }, "Στον χάρτη");
        fly.addEventListener("click", () => {
          bus?.dispatchEvent?.(new CustomEvent("map:flyto", { detail: { lon: it.lng, lat: it.lat, zoom: 16 } }));
          const mTab = doc.getElementById?.("tab-map");
          if (mTab && typeof mTab.click === "function") mTab.click();
        });
        actions.append(fly);
      }
      if (it.url && /^https?:\/\//i.test(it.url)) {
        const link = el("a", { href: it.url, target: "_blank", rel: "noopener noreferrer", class: "workstab-filter notice-link" }, it.source_label || "Πηγή");
        actions.append(link);
      }
      li.append(top, title, loc, summary, actions);
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
  root.appendChild(panel);

  let loaded = false;
  async function loadAnnouncements() {
    if (loaded) return;
    loaded = true;
    try {
      const res = typeof api?.announcements === "function" ? await api.announcements() : null;
      sourceBadge.textContent = SOURCE_BADGE[res?.source] || "DEMO";
      items = Array.isArray(res?.items) ? res.items : [];
      renderList();
    } catch {
      sourceBadge.textContent = "DEMO";
      emptyMsg.hidden = false;
      emptyMsg.textContent = "Αδυναμία φόρτωσης ανακοινώσεων.";
    }
  }

  bus?.addEventListener?.("tab:change", (e) => {
    const open = e?.detail?.tab === "announcements";
    panel.hidden = !open;
    if (open) loadAnnouncements();
  });

  return { refresh: () => { loaded = false; return loadAnnouncements(); } };
}
