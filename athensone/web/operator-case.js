// Operator Console · case panel: workflow, supporting submissions, Stoa evidence, decisions, audit trail.
// Classic script (operator.html is a plain page). All data arrives through window.opApi (operator.html) and is
// rendered with textContent / DOM nodes only, never innerHTML, so report text can't inject markup.
(function () {
  "use strict";
  const STAGES = ["NEW", "TRIAGED", "STOA_INVESTIGATION", "EVIDENCE_REVIEW", "ENGINEER_DECISION", "LEGAL_REVIEW",
    "APPROVED_ACTION", "RESOLVED", "CITIZEN_NOTIFIED"];
  const STAGE_SHORT = { NEW: "Νέα", TRIAGED: "Διαλογή", STOA_INVESTIGATION: "Stoa", EVIDENCE_REVIEW: "Τεκμήρια",
    ENGINEER_DECISION: "Μηχανικός", LEGAL_REVIEW: "Νομική", APPROVED_ACTION: "Ενέργεια", RESOLVED: "Επίλυση",
    CITIZEN_NOTIFIED: "Πολίτης", REJECTED: "Απορρίφθηκε" };
  const ACTION_UI = {
    triage: { label: "Διαλογή ολοκληρώθηκε", cls: "ghost" },
    start_investigation: { label: "🔎 Έναρξη διερεύνησης Stoa", cls: "primary" },
    request_investigation: { label: "Αίτημα περαιτέρω διερεύνησης", cls: "ghost", reason: true },
    generate_dossier: { label: "📄 Φάκελος Εγγύησης · σύνταξη τεκμηρίων", cls: "primary", role: "engineer" },
    decide_municipal_repair: { label: "🛠 Αποκατάσταση από τον Δήμο", cls: "ghost", reason: true, role: "engineer" },
    decide_refer_contractor: { label: "⚖️ Παραπομπή σε ανάδοχο (μέσω Νομικής)", cls: "primary", reason: true, role: "engineer" },
    escalate_legal: { label: "Παραπομπή στη Νομική Υπηρεσία", cls: "ghost", reason: true, role: "engineer" },
    legal_approve: { label: "✔ Έγκριση Νομικής Υπηρεσίας", cls: "good", reason: true, role: "legal" },
    legal_return: { label: "↩ Επιστροφή στον μηχανικό", cls: "ghost", reason: true, role: "legal" },
    resolve: { label: "Επιλύθηκε", cls: "good" },
    notify_citizen: { label: "✉ Ενημέρωση πολίτη", cls: "primary", reason: true, message: true },
    reject_report: { label: "Απόρριψη αναφοράς", cls: "bad", reason: true },
    reopen: { label: "Επανάνοιγμα", cls: "ghost", reason: true },
  };
  const GSTATE = {
    ACTIVE: ["Πιθανώς εντός εγγύησης", "good"], EXPIRED: ["Πιθανώς έληξε", ""], UNKNOWN: ["Άγνωστη · λείπει βεβαίωση περάτωσης", "warn"],
    REQUIRES_HUMAN_REVIEW: ["Απαιτείται έλεγχος", "warn"],
  };
  const MTYPE_CLS = { EXACT: "good", STREET: "good", NEIGHBOURHOOD: "info", MUNICIPALITY: "", PROXIMITY: "warn" };

  function h(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const k of kids.flat()) if (k != null && k !== false) n.append(k instanceof Node ? k : String(k));
    return n;
  }
  const badge = (t, cls = "") => h("span", { class: "badge " + cls }, t);
  const fmtD = (iso) => (iso ? new Date(iso).toLocaleDateString("el-GR") : "—");
  const fmtDT = (iso) => (iso ? new Date(iso).toLocaleString("el-GR") : "—");
  const eur = (v) => (v == null ? "—" : "€" + Number(v).toLocaleString("el-GR", { maximumFractionDigits: 2 }));
  const val = (f) => (f && typeof f === "object" ? f.value : f);

  function who() {
    const s = window.sessionStorage;
    return { actor: (s.getItem("op_actor") || "").trim(), role: s.getItem("op_role") || "engineer" };
  }

  function stepper(stage) {
    const ol = h("ol", { class: "case-steps", "aria-label": "Στάδια υπόθεσης" });
    const rejected = stage === "REJECTED";
    const idx = STAGES.indexOf(stage);
    STAGES.forEach((s, i) => {
      const st = rejected ? "todo" : i < idx ? "done" : i === idx ? "now" : "todo";
      ol.append(h("li", { class: "case-step " + st, "aria-current": st === "now" ? "step" : null }, STAGE_SHORT[s]));
    });
    if (rejected) ol.append(h("li", { class: "case-step now bad", "aria-current": "step" }, STAGE_SHORT.REJECTED));
    return ol;
  }

  function adaLink(work) {
    const ada = val(work.ada);
    if (!ada) return badge("χωρίς ΑΔΑ", "warn");
    if (work.is_seed) return badge(`ΑΔΑ ${ada} · SEED δοκιμαστικό`, "warn");
    const href = work.source_url || `https://diavgeia.gov.gr/decision/view/${encodeURIComponent(ada)}`;
    return h("a", { class: "stoa-claim__ada", href, target: "_blank", rel: "noopener noreferrer" },
      `ΑΔΑ ${ada} ↗`);
  }

  function factRow(label, f, fmt = (x) => x) {
    const known = f && f.value != null && f.value !== "";
    const src = f && f.source && f.source.ada ? `${f.label} · ΑΔΑ ${f.source.ada}${f.source.page ? ", σελ. " + f.source.page : ""}`
      : known ? (f.label || "") : "";
    return h("div", { class: "fact" }, h("span", { class: "fact__k" }, label),
      h("span", { class: "fact__v" + (known ? "" : " unk") }, known ? fmt(f.value) : "ΑΓΝΩΣΤΟ"),
      h("span", { class: "fact__s" }, src));
  }

  function guaranteeBlock(g) {
    const [txt, cls] = GSTATE[g.state] || [g.state, ""];
    const box = h("div", { class: "gbox " + cls },
      h("div", { class: "gbox__head" }, h("b", {}, "Περίοδος εγγύησης"), badge(txt, cls)));
    const grid = h("div", { class: "stoa-claim__grid" });
    const stat = (l, v, sub) => grid.append(h("div", { class: "stoa-claim__stat" },
      h("span", { class: "stoa-claim__stat-label" }, l), h("span", { class: "stoa-claim__stat-val" }, v),
      sub ? h("span", { class: "stoa-claim__stat-sub" }, sub) : null));
    stat("Χρόνος", `${g.period.months} μήνες`, g.period.basis_el);
    stat("Έναρξη", g.start.date ? fmtD(g.start.date) : "ΑΓΝΩΣΤΗ", g.start.basis_el);
    stat("Λήξη", g.expiry ? fmtD(g.expiry) : "Δεν υπολογίζεται", g.expiry ? "" : "χωρίς βεβαίωση περάτωσης");
    stat("Υπόλοιπο", g.days_remaining == null ? "—" : g.days_remaining < 0 ? "Έληξε" : `${g.days_remaining} ημ.`);
    box.append(grid, h("p", { class: "muted formula" }, g.formula_el));
    if (g.start.quote) box.append(h("blockquote", {}, `«${g.start.quote}»`,
      g.start.source && g.start.source.ada ? h("small", {}, ` · ΑΔΑ ${g.start.source.ada}, σελ. ${g.start.source.page ?? "-"}`) : null));
    const lim = [...g.limitations, ...g.review_reasons];
    if (lim.length) box.append(h("ul", { class: "lim" }, lim.map((x) => h("li", {}, x))));
    return box;
  }

  function candidateCard(c, ctx) {
    const w = c.work || {};
    const card = h("article", { class: "cand-card" + (c.accepted ? " accepted" : "") + (c.rejected ? " rejected" : ""),
      "aria-label": `Υποψήφιο έργο ${c.work_id}` });
    card.append(h("header", { class: "cand-card__head" },
      h("div", {}, h("div", { class: "cand-card__title" }, val(w.title) || c.work_id),
        h("div", { class: "muted" }, `${c.work_id} · ${w.works_type_el || ""}`)),
      adaLink(w)));
    const conf = Math.round(c.confidence * 100);
    card.append(h("div", { class: "stoa-claim__badges" },
      badge(c.match_type_el, MTYPE_CLS[c.match_type] || ""), badge(`~${c.distance_m} m`, "info"),
      h("span", { class: "confbar", title: `Βεβαιότητα αντιστοίχισης ${conf}%`, role: "meter", "aria-valuenow": conf,
        "aria-valuemin": 0, "aria-valuemax": 100, "aria-label": "Βεβαιότητα αντιστοίχισης" },
        h("span", { class: "confbar__fill", style: `width:${conf}%` }), h("span", { class: "confbar__txt" }, `${conf}%`)),
      c.accepted ? badge("✔ Αποδεκτή από μηχανικό", "good") : null,
      c.rejected ? badge("✖ Απορρίφθηκε", "bad") : null,
      w.is_seed ? badge("SEED · όχι πραγματικό έργο", "warn") : badge("Πραγματική πράξη Διαύγειας", "info")));
    const facts = h("div", { class: "facts" },
      factRow("Ανάδοχος", w.contractor), factRow("Ποσό σύμβασης", w.amount_contract_eur, eur),
      factRow("Πληρωμές", w.amount_paid_eur, eur), factRow("ΑΔΑΜ", w.adam),
      factRow("Έναρξη", w.start_date, fmtD), factRow("Βεβαίωση περάτωσης", w.completion_date, fmtD));
    if (w.decision_type) facts.append(factRow("Είδος πράξης", w.decision_type));
    card.append(facts);
    if (w.contractor_note) card.append(h("p", { class: "muted" }, w.contractor_note));
    card.append(guaranteeBlock(c.guarantee));
    card.append(h("details", { class: "why", open: c === ctx.best ? true : null },
      h("summary", {}, "Γιατί προτείνεται · αβεβαιότητες"),
      h("ul", {}, c.evidence.map((x) => h("li", {}, x))),
      c.uncertainty.length ? h("ul", { class: "unc" }, c.uncertainty.map((x) => h("li", {}, "⚠ " + x))) : null,
      c.review ? h("p", { class: "muted" }, `Έλεγχος: ${c.review.verdict === "accept" ? "αποδοχή" : "απόρριψη"} από ${c.review.actor}` +
        `${c.review.reason ? " · " + c.review.reason : ""} · ${fmtDT(c.review.at)}`) : null));
    const acts = h("div", { class: "stoa-claim__actions" },
      h("button", { type: "button", class: "ghost", onclick: () => ctx.showWork(c) }, "🗺 Στον χάρτη"));
    if (ctx.allowed.includes("accept_match") && !c.accepted)
      acts.append(h("button", { type: "button", class: "good", onclick: () => ctx.run("accept_match", { work_id: c.work_id }) },
        "✔ Αποδοχή αντιστοίχισης"));
    if (ctx.allowed.includes("reject_match") && !c.rejected)
      acts.append(h("button", { type: "button", class: "bad", onclick: () => ctx.run("reject_match", { work_id: c.work_id }, true) },
        "✖ Λάθος αντιστοίχιση"));
    card.append(acts);
    return card;
  }

  function supportingBlock(v, ctx) {
    const sec = h("section", { class: "case-sec", "aria-labelledby": "supH" },
      h("h3", { id: "supH" }, `Αναφορές πολιτών για αυτό το σημείο · ${v.support_count}`));
    if (!v.supporting.length) {
      sec.append(h("p", { class: "muted" }, "Μία αναφορά. Νέες αναφορές του ίδιου τύπου σε 50 m συνδέονται εδώ αυτόματα."));
      return sec;
    }
    const list = h("div", { class: "sup-list" });
    for (const s of v.supporting) {
      list.append(h("div", { class: "sup" },
        s.photo_url ? h("img", { src: s.photo_url, alt: "Φωτογραφία υποστηρικτικής αναφοράς (θολωμένη)", loading: "lazy" }) :
          h("div", { class: "sup__nophoto", "aria-hidden": "true" }, "📍"),
        h("div", { class: "sup__body" }, h("b", {}, s.child_id),
          h("div", { class: "muted" }, `${fmtDT(s.created_at)} · ~${s.distance_m ?? "?"} m από την αρχική`),
          s.note ? h("div", {}, `«${s.note}»`) : null),
        h("button", { type: "button", class: "ghost small", onclick: () => ctx.unlink(s.child_id),
          "aria-label": `Αποσύνδεση ${s.child_id}` }, "Αποσύνδεση")));
    }
    sec.append(list);
    return sec;
  }

  function classificationBlock(v, ctx) {
    const c = v.classification;
    const sec = h("section", { class: "case-sec", "aria-labelledby": "clsH" }, h("h3", { id: "clsH" }, "Κατηγοριοποίηση"));
    sec.append(h("div", { class: "stoa-claim__badges" }, badge(c.label_el, "info"),
      badge(`μέθοδος: ${c.method}`), badge(`βεβαιότητα ${Math.round(c.confidence * 100)}%`, c.confidence >= 0.85 ? "good" : "warn"),
      c.needs_review ? badge("NEEDS REVIEW", "warn") : null,
      c.stoa_eligible ? badge("Συνδέεται με έργα Stoa", "good") : badge("Δεν συνδέεται με έργα", "")));
    sec.append(h("p", { class: "muted" }, (c.reasons || []).join(" "),
      c.original_category ? ` Αρχική επιλογή πολίτη: ${c.original_category}${c.original_subtype ? " / " + c.original_subtype : ""}.` : ""));
    if (ctx.allowed.includes("reclassify")) {
      const sel = h("select", { "aria-label": "Νέα κατηγορία" },
        ["sidewalk", "pothole", "streetlight", "garbage", "tree", "water_leak", "other"].map((k) =>
          h("option", { value: k, selected: k === c.city_category ? true : null }, k)));
      sec.append(h("div", { class: "row" }, sel,
        h("button", { type: "button", class: "ghost", onclick: () => ctx.run("reclassify", { category: sel.value }, true) }, "Αλλαγή κατηγορίας")));
    }
    return sec;
  }

  function decisionBlock(v, ctx) {
    const me = who();
    const sec = h("section", { class: "case-sec decide", "aria-labelledby": "decH" }, h("h3", { id: "decH" }, "Απόφαση"));
    const actor = h("input", { id: "opActor", type: "text", value: me.actor, placeholder: "Ονοματεπώνυμο υπαλλήλου", autocomplete: "name" });
    const role = h("select", { id: "opRole" }, [["engineer", "Μηχανικός επίβλεψης"], ["legal", "Νομική Υπηρεσία"], ["operator", "Υπάλληλος"]]
      .map(([k, l]) => h("option", { value: k, selected: k === me.role ? true : null }, l)));
    actor.addEventListener("change", () => sessionStorage.setItem("op_actor", actor.value.trim()));
    role.addEventListener("change", () => { sessionStorage.setItem("op_role", role.value); ctx.rerender(); });
    sec.append(h("div", { class: "who" }, h("label", { for: "opActor" }, "Ποιος αποφασίζει", actor),
      h("label", { for: "opRole" }, "Ρόλος", role)));
    const reason = h("textarea", { id: "opReason", rows: "2", placeholder: "Αιτιολόγηση (καταγράφεται στο ιστορικό)" });
    sec.append(h("label", { for: "opReason" }, "Αιτιολόγηση / μήνυμα"), reason);
    const btns = h("div", { class: "row wrap decide__btns" });
    for (const a of v.allowed_actions) {
      const ui = ACTION_UI[a];
      if (!ui) continue;
      const wrongRole = ui.role && ui.role !== role.value;
      btns.append(h("button", { type: "button", class: ui.cls, disabled: wrongRole ? true : null,
        title: wrongRole ? `Απαιτείται ρόλος: ${ui.role === "legal" ? "Νομική Υπηρεσία" : "Μηχανικός"}` : null,
        onclick: () => ctx.run(a, ui.message ? { message: reason.value } : {}, !!ui.reason) }, ui.label));
    }
    sec.append(btns, h("p", { class: "muted guard" }, "Η AI και η Stoa μόνο προτείνουν. Το σύστημα δεν στέλνει τίποτα σε αναδόχους " +
      "και δεν λαμβάνει νομικές αποφάσεις· κάθε απόφαση καταγράφεται με όνομα, ρόλο και ώρα."));
    if (v.dossiers.length) {
      sec.append(h("div", { class: "dossiers" }, h("b", {}, "Φάκελοι: "),
        v.dossiers.map((d) => h("a", { href: `/api/cases/${encodeURIComponent(v.report.id)}/dossiers/${encodeURIComponent(d.id)}`,
          target: "_blank", rel: "noopener", class: "pill", onclick: (e) => ctx.openDossier(e, d) },
          `📄 ${d.kind === "claim_draft" ? "Φάκελος + σχέδιο αιτήματος" : "Φάκελος τεκμηρίων"} · ${fmtDT(d.created_at)}`))));
    }
    return sec;
  }

  function auditBlock(v) {
    const ul = h("ul", { class: "timeline" });
    for (const e of v.events) {
      ul.append(h("li", {}, h("b", {}, e.action_el), ` · ${e.actor}${e.role ? " (" + e.role + ")" : ""} · ${fmtDT(e.at)}`,
        e.stage_to && e.stage_to !== e.stage_from ? ` · → ${STAGE_SHORT[e.stage_to] || e.stage_to}` : "",
        e.reason ? h("div", { class: "muted" }, e.reason) : null));
    }
    return h("details", { class: "case-sec" }, h("summary", {}, h("b", {}, `Ιστορικό ενεργειών (audit) · ${v.events.length}`)), ul);
  }

  // Public entry point used by operator.html
  window.renderCase = function (box, v, hooks) {
    box.innerHTML = "";
    const ctx = {
      allowed: v.allowed_actions, best: v.stoa.best,
      rerender: () => window.renderCase(box, v, hooks),
      showWork: (c) => hooks.showWork(c, v),
      openDossier: (e, d) => hooks.openDossier(e, v, d),
      unlink: async (child) => {
        const me = who(), reason = prompt("Γιατί δεν είναι η ίδια βλάβη; (καταγράφεται)");
        if (!reason) return;
        if (!me.actor) { hooks.toast("Συμπληρώστε «Ποιος αποφασίζει»"); return; }
        await hooks.post(`/api/cases/${encodeURIComponent(v.report.id)}/links/${encodeURIComponent(child)}/unlink`,
          { actor: me.actor, reason });
      },
      run: async (action, extra = {}, needReason = false) => {
        const me = { actor: (document.getElementById("opActor")?.value || "").trim(),
          role: document.getElementById("opRole")?.value || "engineer" };
        sessionStorage.setItem("op_actor", me.actor);
        let reason = (document.getElementById("opReason")?.value || "").trim();
        if (!me.actor) { hooks.toast("Συμπληρώστε «Ποιος αποφασίζει»: κάθε απόφαση καταγράφεται ονομαστικά."); document.getElementById("opActor")?.focus(); return; }
        if (needReason && !reason) {
          reason = (prompt("Αιτιολόγηση (υποχρεωτική για αυτή την ενέργεια):") || "").trim();
          if (!reason) return;
        }
        const out = await hooks.post(`/api/cases/${encodeURIComponent(v.report.id)}/actions`,
          { action, actor: me.actor, role: me.role, reason: reason || null, ...extra });
        if (out && out.url) window.open(out.url, "_blank", "noopener");
      },
    };

    box.append(h("div", { class: "case-head" }, h("h3", {}, "Υπόθεση · ", v.stage_el), stepper(v.stage)));
    if (v.decision) box.append(h("p", { class: "muted" }, `Καταγεγραμμένη απόφαση: ${v.decision}`));
    box.append(supportingBlock(v, ctx), classificationBlock(v, ctx));

    const st = v.stoa;
    const stoa = h("section", { class: "case-sec stoa", "aria-labelledby": "stoaH" },
      h("div", { class: "stoa__head" }, h("h3", { id: "stoaH" }, "🏛 Stoa Guarantee Claim · Δημόσια έργα & εγγυήσεις"),
        badge(st.match_type_el, MTYPE_CLS[st.match_type] || ""),
        badge(`Πηγή: ${v.data_source.source} · ${v.data_source.snapshot || ""}`, "info")),
      h("p", { class: "stoa__expl" }, st.explanation));
    if (!st.candidates.length) {
      stoa.append(h("p", { class: "muted" }, v.classification.stoa_eligible ?
        "Κανένα έργο σχετικού τύπου κοντά. Η αποκατάσταση πιθανότατα βαρύνει τον Δήμο." :
        "Η κατηγορία δεν αντιστοιχεί σε δημόσιο έργο. Αλλάξτε κατηγορία αν πρόκειται για φθορά έργου."));
    } else {
      const shown = st.candidates.slice(0, 3);
      shown.forEach((c) => stoa.append(candidateCard(c, ctx)));
      if (st.candidates.length > 3) {
        const more = h("details", {}, h("summary", {}, `Άλλες ${st.candidates.length - 3} ασθενέστερες αντιστοιχίσεις`));
        st.candidates.slice(3).forEach((c) => more.append(candidateCard(c, ctx)));
        stoa.append(more);
      }
    }
    stoa.append(h("p", { class: "muted guard" }, "Η εγγύτητα σε έργο δεν σημαίνει ευθύνη αναδόχου. Η Stoa δείχνει τι λένε οι " +
      "δημόσιες πράξεις, με πηγή και βαθμό βεβαιότητας· ο μηχανικός κρίνει."));
    box.append(stoa, decisionBlock(v, ctx), auditBlock(v));
  };
})();
