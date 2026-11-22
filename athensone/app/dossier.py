"""Stoa evidence dossier: built only from stored report data and works records, rendered as a printable HTML
document (the browser's «Save as PDF» gives the PDF; no extra dependency, Greek renders everywhere).

Every factual line carries its provenance: label (CITED / INFERRED / UNKNOWN / SEED), ΑΔΑ, page, URL and the exact
quote when one exists. Interpretations are written as such; quotes are only ever copied from the record's `quote`
field (text taken from the source document), never generated.

A claim draft is only included when a works match has been *accepted by an engineer*; otherwise the dossier is an
evidence summary plus a request for the missing documents. The draft always says it is not an issued notice.
"""
from __future__ import annotations

import html
from datetime import date

from . import categories, guarantee

DIAVGEIA_VIEW = "https://diavgeia.gov.gr/decision/view/"

FIELDS = (  # (works field, Greek label)
    ("title", "Τίτλος πράξης"),
    ("contractor", "Ανάδοχος"),
    ("ada", "ΑΔΑ"),
    ("adam", "ΑΔΑΜ (ΚΗΜΔΗΣ)"),
    ("amount_contract_eur", "Ποσό σύμβασης (€)"),
    ("amount_paid_eur", "Ποσό πληρωμών (€)"),
    ("start_date", "Έναρξη"),
    ("completion_date", "Βεβαίωση περάτωσης"),
    ("guarantee_months", "Χρόνος εγγύησης (μήνες)"),
    ("decision_type", "Είδος πράξης"),
    ("final_acceptance_evidence", "Ένδειξη οριστικής παραλαβής"),
)


def _seed(ada: str | None) -> bool:
    return str(ada or "").upper().startswith("SEED")


def source_url(ada: str | None) -> str | None:
    if not ada or _seed(ada):
        return None
    return DIAVGEIA_VIEW + str(ada)


def fact(w: dict, name: str, label_el: str) -> dict:
    f = w.get(name) if isinstance(w.get(name), dict) else {}
    src = f.get("source") or {}
    ada = src.get("ada")
    val = f.get("value")
    label = f.get("label") or ("UNKNOWN" if val in (None, "") else "CITED")
    if _seed(ada):
        label = f"{label} · SEED"
    return {"field": name, "label_el": label_el, "value": val, "label": label, "ada": ada, "page": src.get("page"),
            "url": source_url(ada), "quote": f.get("quote"), "note": f.get("note"), "known": val not in (None, "")}


def build(case: dict, work: dict | None, candidate: dict | None, today: date, actor: str) -> dict:
    """Structured dossier. `case` is the API case view; `work` the accepted works record (or None)."""
    report = case["report"]
    cls = case["classification"]
    missing: list[str] = []
    review: list[str] = []
    facts: list[dict] = []
    g = None
    if work:
        optional = ("decision_type", "final_acceptance_evidence")
        facts = [f for f in (fact(work, n, l) for n, l in FIELDS) if f["known"] or f["field"] not in optional]
        g = guarantee.evaluate(work, today)
        missing += [f["label_el"] for f in facts if not f["known"] and f["field"] not in ("decision_type",
                                                                                           "final_acceptance_evidence")]
        review += g["review_reasons"] + (candidate or {}).get("uncertainty", [])
    else:
        review.append("Καμία αντιστοίχιση έργου δεν έχει γίνει δεκτή από μηχανικό.")
    if cls.get("needs_review"):
        review.append("Η κατηγορία της αναφοράς χρειάζεται επιβεβαίωση.")
    can_draft = bool(work and candidate and candidate.get("accepted") and g and g["state"] in
                     (guarantee.ACTIVE, guarantee.REQUIRES_HUMAN_REVIEW) and g["expiry"])
    if not work:
        next_action = "Ολοκληρώστε τον έλεγχο αντιστοίχισης έργου ή αποφασίστε αποκατάσταση από τον Δήμο."
    elif g["state"] == guarantee.UNKNOWN:
        next_action = ("Ζητήστε από την επιβλέπουσα υπηρεσία τη βεβαίωση περάτωσης και τους όρους εγγύησης της "
                       "σύμβασης πριν από οποιαδήποτε ενέργεια προς τον ανάδοχο.")
    elif g["state"] == guarantee.EXPIRED:
        next_action = "Η περίοδος πιθανώς έχει λήξει: αποκατάσταση από τον Δήμο, εκτός αν η Νομική Υπηρεσία κρίνει διαφορετικά."
    else:
        next_action = ("Αυτοψία από μηχανικό για να κριθεί αν πρόκειται για κακοτεχνία/φθορά του έργου και όχι εμπόδιο, "
                       "βανδαλισμό ή εκσκαφή οργανισμού κοινής ωφέλειας· στη συνέχεια Νομική Υπηρεσία.")
    contractor = (work or {}).get("contractor", {}).get("value") if work else None
    return {
        "generated_at": case.get("generated_at"), "generated_by": actor, "today": today.isoformat(),
        "request_id": report["id"], "title": report.get("title"), "address": report.get("address"),
        "lat": report.get("lat"), "lng": report.get("lng"), "district": report.get("district_name"),
        "created_at": report.get("created_at"), "status": report.get("status"),
        "classification": cls, "category_label": cls.get("label_el") or categories.LABEL_EL.get(cls.get("city_category"), "-"),
        "supporting": [{"child_id": s["child_id"], "kind": s["child_kind"], "distance_m": s.get("distance_m"),
                        "photo_url": s.get("photo_url"), "note": s.get("note"), "created_at": s.get("created_at")}
                       for s in case.get("supporting", [])],
        "photo_url": case.get("photo_url"),
        "work_id": (work or {}).get("id"), "candidate": candidate and {k: candidate[k] for k in (
            "match_type", "match_type_el", "confidence", "distance_m", "evidence", "uncertainty", "geometry_basis")},
        "facts": facts, "guarantee": g, "contractor": contractor, "missing": missing,
        "review_reasons": list(dict.fromkeys(review)), "next_action": next_action, "can_draft_claim": can_draft,
        "sent": False, "data_source": _source_line(case.get("data_source")),
    }


def _source_line(ds) -> str:
    if not isinstance(ds, dict):
        return str(ds or "-")
    return f"αναφορές: {ds.get('reports', '-')} · έργα: {ds.get('source', '-')} (στιγμιότυπο {ds.get('snapshot') or '-'})"


# ------------------------------------------------------------------ HTML
def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "Ναι" if v else "Όχι"
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(v)


def _src_cell(f: dict, n: int | None) -> str:
    parts = [f'<span class="lbl lbl-{_e(f["label"].split(" ")[0])}">{_e(f["label"])}</span>']
    if f["ada"]:
        a = f'<a href="{_e(f["url"])}">ΑΔΑ {_e(f["ada"])}</a>' if f["url"] else f"ΑΔΑ {_e(f['ada'])}"
        parts.append(a + (f", σελ. {_e(f['page'])}" if f["page"] else ""))
    if n:
        parts.append(f'<a href="#ev{n}">[{n}]</a>')
    return " · ".join(parts)


def render_html(d: dict) -> str:
    g = d.get("guarantee")
    seed = any("SEED" in (f["label"] or "") for f in d["facts"])
    appendix, rows = [], []
    for f in d["facts"]:
        n = None
        if f["known"] and (f["quote"] or f["ada"]):
            appendix.append(f)
            n = len(appendix)
        val = _e(_fmt(f["value"])) if f["known"] else '<b class="unk">ΑΓΝΩΣΤΟ</b>'
        rows.append(f"<tr><th>{_e(f['label_el'])}</th><td>{val}</td><td class='src'>{_src_cell(f, n)}</td></tr>")
    c = d.get("candidate") or {}
    gblock = ""
    if g:
        lim = "".join(f"<li>{_e(x)}</li>" for x in g["limitations"])
        gblock = f"""
<h2>4. Περίοδος εγγύησης (ντετερμινιστικός υπολογισμός)</h2>
<table class="kv">
<tr><th>Κατάσταση</th><td><b>{_e(g['state_el'])}</b> ({_e(g['state'])})</td></tr>
<tr><th>Χρόνος εγγύησης</th><td>{_e(g['period']['months'])} μήνες · {_e(g['period']['basis_el'])}<br><small>{_e(g['period']['note'])}</small></td></tr>
<tr><th>Έναρξη</th><td>{_e(g['start']['date'] or 'ΑΓΝΩΣΤΗ')} · {_e(g['start']['basis_el'])}</td></tr>
<tr><th>Λήξη</th><td>{_e(g['expiry'] or 'Δεν υπολογίζεται')}</td></tr>
<tr><th>Υπόλοιπο ημερών</th><td>{_e(g['days_remaining'] if g['days_remaining'] is not None else '—')}</td></tr>
<tr><th>Υπολογισμός</th><td>{_e(g['formula_el'])}</td></tr>
</table>
{'<ul class="lim">' + lim + '</ul>' if lim else ''}"""
    sup = "".join(f"<li>{_e(s['child_id'])} · {_e(s['created_at'])} · ~{_e(round(s['distance_m']) if s['distance_m'] is not None else '?')} m"
                  f"{' · «' + _e(s['note']) + '»' if s.get('note') else ''}</li>" for s in d["supporting"])
    review = "".join(f"<li>{_e(r)}</li>" for r in d["review_reasons"]) or "<li>—</li>"
    missing = "".join(f"<li>{_e(m)}</li>" for m in d["missing"]) or "<li>—</li>"
    ev = "".join(f"<li>{_e(x)}</li>" for x in c.get("evidence", []))
    unc = "".join(f"<li>{_e(x)}</li>" for x in c.get("uncertainty", []))
    apx = "".join(
        f"<li id='ev{i}'><b>[{i}] {_e(f['label_el'])}</b> · {_e(f['label'])} · "
        f"{('<a href=' + chr(34) + _e(f['url']) + chr(34) + '>' + _e(f['url']) + '</a>') if f['url'] else 'ΑΔΑ ' + _e(f['ada'] or '-')}"
        f"{' · σελ. ' + _e(f['page']) if f['page'] else ''}"
        f"{'<blockquote>' + _e(f['quote']) + '</blockquote>' if f['quote'] else '<p class=muted>Δεν υπάρχει αυτούσιο απόσπασμα στα δεδομένα· η τιμή προέρχεται από τα μεταδεδομένα της πράξης.</p>'}"
        f"{'<p class=muted>' + _e(f['note']) + '</p>' if f.get('note') else ''}</li>"
        for i, f in enumerate(appendix, 1))
    if d["can_draft_claim"]:
        draft = f"""
<h2>7. Σχέδιο αιτήματος αποκατάστασης προς τον ανάδοχο</h2>
<div class="draft">
<p class="stamp">ΣΧΕΔΙΟ · ΔΕΝ ΑΠΟΤΕΛΕΙ ΕΠΙΣΗΜΗ ΚΟΙΝΟΠΟΙΗΣΗ · ΔΕΝ ΕΧΕΙ ΑΠΟΣΤΑΛΕΙ</p>
<p>Προς: {_e(d['contractor'] or 'ΑΝΑΔΟΧΟΣ (να συμπληρωθεί)')}</p>
<p>Θέμα: Αίτημα αποκατάστασης βλάβης, πιθανώς εντός του χρόνου υποχρεωτικής συντήρησης του έργου
«{_e(next((f['value'] for f in d['facts'] if f['field'] == 'title'), ''))}» [ΑΔΑ {_e(next((f['value'] for f in d['facts'] if f['field'] == 'ada'), '-'))}]</p>
<p>Σύμφωνα με το {guarantee.LEGAL_REF} και τους όρους της σύμβασης, κατά τον χρόνο εγγύησης ο ανάδοχος υποχρεούται στη
συντήρηση του έργου. Στη θέση {_e(d['address'])} ({_e(d['lat'])}, {_e(d['lng'])}) καταγράφηκε από πολίτη στις {_e(d['created_at'])}
βλάβη κατηγορίας «{_e(d['category_label'])}» (αναφορά {_e(d['request_id'])}). Με βάση τα στοιχεία του φακέλου, ο χρόνος εγγύησης
πιθανώς διαρκεί έως {_e(g['expiry'])}.</p>
<p>Παρακαλούμε, εφόσον επιβεβαιωθεί κατά την αυτοψία ότι η βλάβη αφορά το έργο σας, για την αποκατάστασή της.</p>
<p>Ο/Η επιβλέπων/ουσα μηχανικός: ______________________ &nbsp; Νομική Υπηρεσία: ______________________ &nbsp; Ημερομηνία: __________</p>
</div>"""
    else:
        draft = """
<h2>7. Σχέδιο αιτήματος προς τον ανάδοχο</h2>
<p class="muted">Δεν συντάχθηκε: τα τεκμήρια δεν επαρκούν (απαιτείται αποδεκτή αντιστοίχιση έργου από μηχανικό και
τεκμηριωμένη ημερομηνία περάτωσης). Δείτε «Επόμενη ενέργεια».</p>"""
    photo = f'<img src="{_e(d["photo_url"])}" alt="Φωτογραφία αναφοράς (θολωμένα πρόσωπα/πινακίδες)">' if d.get("photo_url") else ""
    return f"""<!doctype html><html lang="el"><head><meta charset="utf-8">
<title>Φάκελος τεκμηρίων Stoa · {_e(d['request_id'])}</title>
<style>
body{{font:11pt/1.45 "Segoe UI",system-ui,-apple-system,"Noto Sans",Arial,sans-serif;color:#14181f;max-width:860px;margin:24px auto;padding:0 24px}}
h1{{font-size:18pt;margin:0 0 4px}} h2{{font-size:12.5pt;margin:22px 0 8px;border-bottom:1px solid #d5dae1;padding-bottom:4px}}
.banner{{background:#fff4e5;border:1px solid #f0b35a;padding:8px 12px;border-radius:6px;font-weight:600}}
.seed{{background:#f3ecff;border:1px solid #b69ae6;padding:6px 10px;border-radius:6px;margin-top:8px}}
table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;vertical-align:top;padding:5px 8px;border-bottom:1px solid #eceff3}}
th{{width:30%;color:#4a5361;font-weight:600}} .src{{font-size:9.5pt;color:#4a5361}} .unk{{color:#b42318}}
.lbl{{font-size:8.5pt;padding:1px 6px;border-radius:4px;background:#eef1f5}} .lbl-CITED{{background:#e3f4e8}} .lbl-INFERRED{{background:#fff1d6}} .lbl-UNKNOWN{{background:#fde4e1}}
blockquote{{margin:6px 0;padding:6px 10px;border-left:3px solid #0b5cad;background:#f5f8fc;font-style:italic}}
.muted{{color:#5b6472}} .draft{{border:1px dashed #8a94a3;padding:12px 16px;border-radius:6px}} .stamp{{color:#b42318;font-weight:700;letter-spacing:.3px}}
img{{max-width:320px;border-radius:6px;margin-top:6px}} .meta{{color:#5b6472;font-size:9.5pt}}
.tools{{margin:12px 0}} @media print{{.tools{{display:none}} body{{margin:0}} a{{color:inherit}}}}
</style></head><body>
<div class="tools"><button onclick="window.print()">Εκτύπωση / Αποθήκευση ως PDF</button></div>
<div class="banner">ΠΡΟΣΧΕΔΙΟ ΓΙΑ ΕΣΩΤΕΡΙΚΟ ΕΛΕΓΧΟ · ΔΕΝ ΑΠΟΤΕΛΕΙ ΝΟΜΙΚΗ ΓΝΩΜΑΤΕΥΣΗ ΟΥΤΕ ΕΠΙΣΗΜΗ ΚΟΙΝΟΠΟΙΗΣΗ · ΔΕΝ ΕΧΕΙ ΑΠΟΣΤΑΛΕΙ</div>
{'<div class="seed">Περιέχει δοκιμαστικά δεδομένα SEED (όχι πραγματικό έργο του Δήμου).</div>' if seed else ''}
<h1>Φάκελος τεκμηρίων Stoa</h1>
<p class="meta">Αναφορά {_e(d['request_id'])} · συντάχθηκε {_e(d['generated_at'])} από {_e(d['generated_by'])} · πηγές δεδομένων: {_e(d['data_source'])}</p>

<h2>1. Αναφορά πολίτη</h2>
<table class="kv">
<tr><th>Κωδικός</th><td>{_e(d['request_id'])}</td></tr>
<tr><th>Τίτλος</th><td>{_e(d['title'])}</td></tr>
<tr><th>Θέση</th><td>{_e(d['address'])} · {_e(d['lat'])}, {_e(d['lng'])}{(' · ' + _e(d['district'])) if d['district'] else ''}</td></tr>
<tr><th>Καταχώρηση</th><td>{_e(d['created_at'])}</td></tr>
<tr><th>Κατηγορία</th><td>{_e(d['category_label'])} · μέθοδος {_e(d['classification'].get('method'))} · βεβαιότητα {_e(round(100 * d['classification'].get('confidence', 0)))}%<br>
<small>Αρχική επιλογή πολίτη: {_e(d['classification'].get('original_category'))}{(' / ' + _e(d['classification'].get('original_subtype'))) if d['classification'].get('original_subtype') else ''}</small></td></tr>
<tr><th>Υποστηρικτικές αναφορές</th><td>{len(d['supporting'])}<ul>{sup}</ul></td></tr>
</table>
{photo}

<h2>2. Υποψήφιο δημόσιο έργο και αιτιολόγηση αντιστοίχισης</h2>
{('<p><b>' + _e(d['work_id']) + '</b> · ' + _e(c.get('match_type_el')) + ' · βεβαιότητα ' + _e(round(100 * c.get('confidence', 0))) + '% · ~' + _e(c.get('distance_m')) + ' m</p><p>Τεκμήρια:</p><ul>' + ev + '</ul><p>Αβεβαιότητες:</p><ul>' + unc + '</ul>') if d['work_id'] else '<p class="muted">Καμία αποδεκτή αντιστοίχιση.</p>'}
<p class="muted">Η γεωγραφική αντιστοίχιση είναι ένδειξη, όχι απόδειξη ευθύνης του αναδόχου.</p>

<h2>3. Στοιχεία πράξεων και σύμβασης</h2>
{('<table>' + ''.join(rows) + '</table>') if rows else '<p class="muted">—</p>'}
{gblock}
<h2>5. Ελλείποντα στοιχεία</h2><ul>{missing}</ul>
<h2>6. Λόγοι για ανθρώπινο έλεγχο</h2><ul>{review}</ul>
<p><b>Επόμενη ενέργεια (πρόταση):</b> {_e(d['next_action'])}</p>
{draft}
<h2>Παράρτημα τεκμηρίων</h2>
<ol class="apx">{apx or '<li class="muted">—</li>'}</ol>
<p class="muted">Η επιβλέπουσα υπηρεσία και η Νομική Υπηρεσία αποφασίζουν αν ο ανάδοχος υποχρεούται σε αποκατάσταση.
Το σύστημα δεν αποστέλλει αιτήματα, δεν ειδοποιεί αναδόχους και δεν λαμβάνει νομικές αποφάσεις.</p>
</body></html>"""
