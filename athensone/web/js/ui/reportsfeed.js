// Forum-like Citizen Reports Feed tab ("Αναφορές"): hardcoded demo posts + live api.reports(),
// with upvotes, expandable comment threads, sorting, filtering, and map fly-to.
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

export const DEMO_FORUM_REPORTS = [
  {
    id: "demo-rep-1",
    properties: {
      id: "demo-rep-1",
      category: "obstacle",
      status: "submitted",
      author: "Μαρία Κ. · Κάτοικος",
      neighborhood: "Κολωνάκι / Σύνταγμα",
      address: "Πανεπιστημίου & Βουκουρεστίου",
      description: "Παρκαρισμένο φορτηγάκι πάνω στη ράμπα ΑμεΑ στη διάβαση. Δυσκολεύει τη διέλευση αμαξιδίων και καροτσιών.",
      created_at: "2026-11-22T12:15:00+02:00",
      upvotes: 18,
      comments: [
        { author: "Νίκος Π.", text: "Το είδα κι εγώ πριν 20 λεπτά, ειδοποιήθηκε η Δημοτική Αστυνομία.", time: "12:32" },
        { author: "Ελένη Δ.", text: "Συμβαίνει συχνά τις ώρες τροφοδοσίας, χρειάζεται κολωνάκι.", time: "12:48" },
      ],
      demo: true,
    },
    geometry: { type: "Point", coordinates: [23.7336, 37.9781] },
  },
  {
    id: "demo-rep-2",
    properties: {
      id: "demo-rep-2",
      category: "pothole",
      status: "in_progress",
      author: "Γιώργος Τ. · Οδηγός",
      neighborhood: "Κυψέλη",
      address: "Πατησίων 142 (ύψος Αγ. Μελετίου)",
      description: "Βαθιά λακκούβα στη δεξιά λωρίδα κατεύθυνσης προς κέντρο — κίνδυνος για δίκυκλα και λεωφορεία.",
      created_at: "2026-11-22T10:40:00+02:00",
      upvotes: 24,
      comments: [
        { author: "Κώστας Β.", text: "Έχει τοποθετηθεί προσωρινός κώνος, περιμένουμε συνεργείο ασφαλτόστρωσης.", time: "11:10" },
      ],
      demo: true,
    },
    geometry: { type: "Point", coordinates: [23.7338, 37.9994] },
  },
  {
    id: "demo-rep-3",
    properties: {
      id: "demo-rep-3",
      category: "sidewalk",
      status: "acknowledged",
      author: "Αθηνά Σ. · Πεζή",
      neighborhood: "Εξάρχεια",
      address: "Στουρνάρη 28",
      description: "Σπασμένες πλάκες πεζοδρομίου μπροστά από τη στάση — λιμνάζουν νερά όταν βρέχει.",
      created_at: "2026-11-21T18:20:00+02:00",
      upvotes: 11,
      comments: [],
      demo: true,
    },
    geometry: { type: "Point", coordinates: [23.7316, 37.9862] },
  },
  {
    id: "demo-rep-4",
    properties: {
      id: "demo-rep-4",
      category: "lighting",
      status: "submitted",
      author: "Δημήτρης Λ.",
      neighborhood: "Παγκράτι",
      address: "Πλατεία Πλαστήρα",
      description: "Δύο δημοτικοί φανοστάτες στη βόρεια πλευρά της πλατείας δεν ανάβουν εδώ και τρεις νύχτες.",
      created_at: "2026-11-21T21:05:00+02:00",
      upvotes: 15,
      comments: [
        { author: "Σοφία Μ.", text: "Όντως είναι πολύ σκοτεινά μετά τις 19:00.", time: "21:40" },
      ],
      demo: true,
    },
    geometry: { type: "Point", coordinates: [23.7478, 37.9684] },
  },
  {
    id: "demo-rep-5",
    properties: {
      id: "demo-rep-5",
      category: "water_leak",
      status: "in_progress",
      author: "Πέτρος Α.",
      neighborhood: "Κουκάκι",
      address: "Βεΐκου 45",
      description: "Συνεχής διαρροή νερού από φρεάτιο στο οδόστρωμα — γλιστράει η άσφαλτος.",
      created_at: "2026-11-22T09:05:00+02:00",
      upvotes: 9,
      comments: [],
      demo: true,
    },
    geometry: { type: "Point", coordinates: [23.7235, 37.9628] },
  },
  {
    id: "demo-rep-6",
    properties: {
      id: "demo-rep-6",
      category: "congestion",
      status: "resolved",
      author: "Ομάδα Γειτονιάς Γκάζι",
      neighborhood: "Γκάζι / Κεραμεικός",
      address: "Πειραιώς & Ιερά Οδός",
      description: "Μεγάλη καθυστέρηση λόγω έργων και διπλοπαρκαρίσματος. Αποκαταστάθηκε η ροή μετά από παρέμβαση Τροχαίας.",
      created_at: "2026-11-20T17:30:00+02:00",
      upvotes: 31,
      comments: [
        { author: "Ανδρέας Γ.", text: "Επιβεβαιώνω, άνοιξε κανονικά η λωρίδα.", time: "18:15" },
      ],
      demo: true,
    },
    geometry: { type: "Point", coordinates: [23.7131, 37.9787] },
  },
];

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
    class: "glass workstab-panel forum-panel",
    role: "tabpanel",
    "aria-labelledby": "tab-reports-feed",
    hidden: "true",
  });
  panel.hidden = true;

  const header = el("div", { class: "workstab-header" });
  const heading = el("h2", { class: "workstab-heading" }, "Φόρουμ Αναφορών Πολιτών");
  const countBadge = el("span", { class: "workstab-source" }, "");
  const closeBtn = el("button", { type: "button", class: "overlay-close-btn", "aria-label": "Κλείσιμο" }, "×");
  closeBtn.addEventListener("click", () => {
    const mTab = doc.getElementById?.("tab-map");
    if (mTab && typeof mTab.click === "function") mTab.click();
    else bus?.dispatchEvent?.(new CustomEvent("tab:change", { detail: { tab: "map" } }));
  });
  header.append(heading, countBadge, closeBtn);

  const controls = el("div", { class: "forum-controls" });
  const filterBar = el("div", { class: "workstab-filters", role: "group", "aria-label": "Φίλτρο αναφορών" });
  const filters = [
    { id: "all", label: "Όλες" },
    { id: "open", label: "Ανοιχτές" },
    { id: "in_progress", label: "Σε εξέλιξη" },
    { id: "resolved", label: "Επιλυμένες" },
  ];
  const sortSelect = el("select", { class: "forum-sort", "aria-label": "Ταξινόμηση" });
  sortSelect.append(
    el("option", { value: "newest" }, "Πιο πρόσφατες"),
    el("option", { value: "top" }, "Περισσότερες ψήφοι"),
  );

  let activeFilter = "all";
  let sortMode = "newest";
  let liveFeatures = [];
  const localVotes = new Map();
  const localUserVoted = new Set();
  const localComments = new Map();
  const openThreads = new Set();
  const filterBtns = new Map();

  const list = el("ul", { class: "workstab-list forum-list" });
  const emptyMsg = el("p", { class: "workstab-empty" }, "Δεν υπάρχουν αναφορές.");
  emptyMsg.hidden = true;

  function getVotes(id, base) {
    return (localVotes.get(id) ?? Number(base || 0));
  }

  function getComments(id, baseComments) {
    const base = Array.isArray(baseComments) ? baseComments : [];
    const extra = localComments.get(id) || [];
    return [...base, ...extra];
  }

  function renderList() {
    list.textContent = "";
    const seenIds = new Set();
    const merged = [];
    for (const f of [...liveFeatures, ...DEMO_FORUM_REPORTS]) {
      const fid = String(f?.properties?.id || f?.id || "");
      if (fid && seenIds.has(fid)) continue;
      if (fid) seenIds.add(fid);
      merged.push(f);
    }

    const filtered = merged.filter((f) => {
      if (activeFilter === "all") return true;
      const st = String(f?.properties?.status || "submitted").toLowerCase();
      if (activeFilter === "open") return st === "submitted" || st === "open" || st === "acknowledged";
      return st === activeFilter;
    });

    filtered.sort((a, b) => {
      const pa = a.properties || {};
      const pb = b.properties || {};
      if (sortMode === "top") {
        return getVotes(pb.id, pb.upvotes) - getVotes(pa.id, pa.upvotes);
      }
      return String(pb.created_at || "").localeCompare(String(pa.created_at || ""));
    });

    countBadge.textContent = `${filtered.length} δημοσιεύσεις`;
    emptyMsg.hidden = filtered.length > 0;

    for (const f of filtered) {
      const p = f.properties || {};
      const fid = String(p.id || f.id || Math.random());
      const coords = f.geometry?.coordinates || [];
      const li = el("li", { class: "workstab-card forum-card" });

      const top = el("div", { class: "notice-card-top" });
      const cat = el("span", { class: "forum-cat" }, CATEGORY_LABELS[p.category] || p.category || "Αναφορά");
      const stKey = String(p.status || "submitted").toLowerCase();
      const st = el("span", { class: `notice-badge forum-status--${stKey}` }, STATUS_LABELS[stKey] || stKey);
      top.append(cat, st);

      const authorRow = el(
        "div",
        { class: "forum-author-row" },
        [p.author || "Πολίτης Αθήνας", p.neighborhood || p.address || "", p.created_at ? String(p.created_at).slice(0, 16).replace("T", " · ") : ""]
          .filter(Boolean)
          .join("  •  "),
      );

      const desc = el("p", { class: "notice-summary forum-body" }, p.description || p.note || "Αναφορά πολίτη στον χάρτη.");
      const addrLine = p.address ? el("div", { class: "workstab-status" }, `📍 ${p.address}`) : null;

      const actions = el("div", { class: "notice-actions forum-actions" });
      const votesCount = getVotes(fid, p.upvotes);
      const voted = localUserVoted.has(fid);
      const upvoteBtn = el(
        "button",
        { type: "button", class: voted ? "workstab-filter is-active" : "workstab-filter", "aria-pressed": String(voted) },
        `👍 ${votesCount}`,
      );
      upvoteBtn.addEventListener("click", () => {
        if (localUserVoted.has(fid)) {
          localUserVoted.delete(fid);
          localVotes.set(fid, Math.max(0, getVotes(fid, p.upvotes) - 1));
        } else {
          localUserVoted.add(fid);
          localVotes.set(fid, getVotes(fid, p.upvotes) + 1);
        }
        renderList();
      });
      actions.append(upvoteBtn);

      const allComments = getComments(fid, p.comments);
      const commentToggle = el(
        "button",
        { type: "button", class: "workstab-filter", "aria-expanded": String(openThreads.has(fid)) },
        `💬 Σχόλια (${allComments.length})`,
      );
      commentToggle.addEventListener("click", () => {
        if (openThreads.has(fid)) openThreads.delete(fid);
        else openThreads.add(fid);
        renderList();
      });
      actions.append(commentToggle);

      if (coords.length >= 2) {
        const fly = el("button", { type: "button", class: "workstab-filter" }, "Στον χάρτη");
        fly.addEventListener("click", () => {
          bus?.dispatchEvent?.(new CustomEvent("map:flyto", { detail: { lon: coords[0], lat: coords[1], zoom: 17 } }));
          const mTab = doc.getElementById?.("tab-map");
          if (mTab && typeof mTab.click === "function") mTab.click();
        });
        actions.append(fly);
      }

      li.append(top, authorRow, desc);
      if (addrLine) li.append(addrLine);
      li.append(actions);

      if (openThreads.has(fid)) {
        const thread = el("div", { class: "forum-thread" });
        for (const c of allComments) {
          const cItem = el("div", { class: "forum-comment" });
          const cHead = el("strong", {}, `${c.author || "Πολίτης"}`);
          const cTime = el("span", { class: "forum-comment-time" }, c.time ? ` · ${c.time}` : "");
          const cText = el("p", { class: "forum-comment-text" }, c.text || "");
          cItem.append(cHead, cTime, cText);
          thread.append(cItem);
        }
        const form = el("form", { class: "forum-comment-form" });
        const input = el("input", { type: "text", class: "forum-comment-input", placeholder: "Γράψτε ένα σχόλιο…", maxlength: "240" });
        const sendBtn = el("button", { type: "submit", class: "workstab-filter is-active" }, "Αποστολή");
        form.addEventListener("submit", (ev) => {
          ev.preventDefault();
          const txt = input.value.trim();
          if (!txt) return;
          const prev = localComments.get(fid) || [];
          const now = new Date();
          const hhmm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
          localComments.set(fid, [...prev, { author: "Εσείς (Πολίτης)", text: txt, time: hhmm }]);
          renderList();
        });
        form.append(input, sendBtn);
        thread.append(form);
        li.append(thread);
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
  sortSelect.addEventListener("change", () => {
    sortMode = sortSelect.value;
    renderList();
  });

  controls.append(filterBar, sortSelect);
  panel.append(header, controls, emptyMsg, list);
  root.appendChild(panel);

  async function loadReports() {
    try {
      const res = typeof api?.reports === "function" ? await api.reports() : null;
      liveFeatures = Array.isArray(res?.features) ? res.features : [];
    } catch {
      liveFeatures = [];
    }
    renderList();
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
