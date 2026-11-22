"""Deterministic guarantee (maintenance-period) engine for one public-works record.

Legal basis, checked 22 Nov 2026 (see docs/KNOWN_LIMITATIONS.md; confirm with Legal Services before any use):
  ν. 4412/2016 άρθ. 171 «Χρόνος υποχρεωτικής συντήρησης των έργων», as replaced by ν. 4782/2021 άρθ. 85:
  - the guarantee period is generally 15 months;
  - for works with a tender budget up to €250,000 excl. VAT the contract documents MAY set a shorter period
    (when the nature of the works allows, or where long maintenance makes no sense);
  - the period starts the day after the certificate of completion (βεβαίωση περάτωσης) is issued;
  - final acceptance (οριστική παραλαβή) follows the period; a returned performance guarantee is a strong sign the
    period is over.
Sources: e-nomothesia.gr consolidated ν. 4782/2021 (art. 85) and ELINYAE's copy of ΦΕΚ 36/Α/9.3.2021.

Hard rules implemented here:
  * No completion certificate date → no expiry date. State UNKNOWN. Never a made-up date.
  * The contract's own term beats the legal default. The legal default is labelled as such and "subject to
    applicability".
  * Conflicting source values → REQUIRES_HUMAN_REVIEW, and the conflicting values are listed.
  * The engine never says a contractor is liable. It reports whether a period is *possibly* running.
"""
from __future__ import annotations

from datetime import date, timedelta

LEGAL_DEFAULT_MONTHS = 15
SHORTER_ALLOWED_BELOW_EUR = 250_000  # excl. VAT, tender budget (art. 171 as replaced by ν. 4782/2021)
LEGAL_REF = "άρθ. 171 ν. 4412/2016 (όπως αντικ. με άρθ. 85 ν. 4782/2021)"

# Period-basis and state vocabulary (mission brief, Part III 3.5).
CONTRACTUALLY_VERIFIED = "CONTRACTUALLY_VERIFIED"
OFFICIALLY_DOCUMENTED = "OFFICIALLY_DOCUMENTED"
LEGAL_DEFAULT = "LEGAL_DEFAULT"
INFERRED = "INFERRED"
UNKNOWN = "UNKNOWN"
ACTIVE, EXPIRED, REQUIRES_HUMAN_REVIEW = "ACTIVE", "EXPIRED", "REQUIRES_HUMAN_REVIEW"

LABELS_EL = {
    CONTRACTUALLY_VERIFIED: "Επαληθευμένο από σύμβαση",
    OFFICIALLY_DOCUMENTED: "Τεκμηριωμένο σε επίσημη πράξη",
    LEGAL_DEFAULT: "Νόμιμος γενικός κανόνας · υπό την επιφύλαξη εφαρμογής",
    INFERRED: "Συμπέρασμα · όχι επαληθευμένο",
    UNKNOWN: "Άγνωστο",
    ACTIVE: "Πιθανώς εντός περιόδου εγγύησης",
    EXPIRED: "Η περίοδος πιθανώς έχει λήξει",
    REQUIRES_HUMAN_REVIEW: "Απαιτείται ανθρώπινος έλεγχος",
}


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    feb = 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    days = [31, feb, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(y, m, min(d.day, days[m - 1]))


def _field(w: dict, name: str) -> dict:
    f = w.get(name)
    return f if isinstance(f, dict) else {}


def _is_seed(w: dict) -> bool:
    ada = (_field(w, "ada").get("value") or "")
    return bool(w.get("seed")) or str(ada).upper().startswith("SEED")


def _src(f: dict) -> dict | None:
    s = f.get("source")
    return dict(s) if isinstance(s, dict) else None


def _conflicts(w: dict) -> list[dict]:
    """Fields that carry conflicting values from different sources (`conflicts: [{value, source}]`)."""
    out = []
    for name in ("completion_date", "guarantee_months", "contractor", "final_acceptance_evidence"):
        f = _field(w, name)
        alts = [c for c in (f.get("conflicts") or []) if c.get("value") != f.get("value")]
        if alts:
            out.append({"field": name, "value": f.get("value"), "alternatives": alts})
    return out


def evaluate(w: dict, today: date) -> dict:
    """Guarantee status of one works record on `today`. Pure and deterministic."""
    limitations: list[str] = []
    review: list[str] = []
    seed = _is_seed(w)
    if seed:
        limitations.append("Δοκιμαστική εγγραφή SEED: δεν είναι πραγματικό έργο του Δήμου.")

    # ---------- period
    term = _field(w, "guarantee_months")
    amount = _field(w, "amount_contract_eur").get("value")
    if term.get("value") is not None and term.get("label") == "CITED":
        months, basis = int(term["value"]), CONTRACTUALLY_VERIFIED
        p_source, p_note = _src(term), "Όρος της σύμβασης."
    elif term.get("value") is not None and term.get("label") == "INFERRED":
        months, basis = int(term["value"]), INFERRED
        p_source, p_note = _src(term), "Τιμή που συνάχθηκε, όχι παράθεμα σύμβασης."
        review.append("Ο χρόνος εγγύησης δεν προέρχεται από παράθεμα της σύμβασης.")
    else:
        months, basis, p_source = LEGAL_DEFAULT_MONTHS, LEGAL_DEFAULT, {"law": LEGAL_REF}
        p_note = (f"Γενικός κανόνας {LEGAL_DEFAULT_MONTHS} μηνών ({LEGAL_REF}). Η σύμβαση μπορεί να ορίζει άλλον "
                  "χρόνο· για έργα προϋπολογισμού έως 250.000 € χωρίς ΦΠΑ επιτρέπεται και μικρότερος.")
        if amount is None or amount <= SHORTER_ALLOWED_BELOW_EUR:
            limitations.append("Το ποσό της σύμβασης είναι άγνωστο ή ≤ 250.000 €: η σύμβαση μπορεί να ορίζει "
                               "χρόνο εγγύησης μικρότερο των 15 μηνών.")
    period = {"months": months, "basis": basis, "basis_el": LABELS_EL[basis], "source": p_source, "note": p_note}

    # ---------- start (completion certificate)
    comp = _field(w, "completion_date")
    if comp.get("value") and comp.get("label") in ("CITED", "INFERRED"):
        cert = date.fromisoformat(comp["value"])
        s_basis = OFFICIALLY_DOCUMENTED if comp.get("label") == "CITED" else INFERRED
        start = {"certificate_date": cert.isoformat(), "date": (cert + timedelta(days=1)).isoformat(),
                 "basis": s_basis, "basis_el": LABELS_EL[s_basis], "source": _src(comp), "quote": comp.get("quote")}
        if s_basis == INFERRED:
            review.append("Η ημερομηνία περάτωσης είναι συμπέρασμα, όχι παράθεμα επίσημης πράξης.")
        if not comp.get("quote"):
            limitations.append("Δεν υπάρχει αυτούσιο απόσπασμα της βεβαίωσης περάτωσης· ελέγξτε το έγγραφο.")
    else:
        cert, start = None, {"certificate_date": None, "date": None, "basis": UNKNOWN, "basis_el": LABELS_EL[UNKNOWN],
                             "source": None, "quote": None}

    # ---------- evidence that the period is already over
    fa = _field(w, "final_acceptance_evidence")
    ended_evidence = bool(w.get("final_acceptance") is True or fa.get("value") is True)
    if fa.get("value") is True:
        limitations.append(fa.get("note") or "Υπάρχει ένδειξη οριστικής παραλαβής / επιστροφής εγγυήσεων.")

    conflicts = _conflicts(w)
    for c in conflicts:
        review.append(f"Αντικρουόμενες τιμές για «{c['field']}» από διαφορετικές πηγές.")

    out = {"period": period, "start": start, "expiry": None, "days_remaining": None, "formula_el": None,
           "conflicts": conflicts, "limitations": limitations, "review_reasons": review, "seed": seed}

    if cert is None:
        out["state"] = REQUIRES_HUMAN_REVIEW if ended_evidence else UNKNOWN
        out["formula_el"] = ("Δεν βρέθηκε βεβαίωση περάτωσης: δεν υπολογίζεται ημερομηνία λήξης. "
                             "Ζητήστε τη βεβαίωση από την επιβλέπουσα υπηρεσία.")
        if ended_evidence:
            review.append("Υπάρχει ένδειξη ότι η περίοδος έχει λήξει, αλλά λείπει η ημερομηνία περάτωσης.")
    else:
        expiry = add_months(cert, months)
        out["expiry"] = expiry.isoformat()
        out["days_remaining"] = (expiry - today).days
        src = "όρος σύμβασης" if basis == CONTRACTUALLY_VERIFIED else (
            "γενικός κανόνας" if basis == LEGAL_DEFAULT else "συμπέρασμα")
        out["formula_el"] = (f"Βεβαίωση περάτωσης {cert:%d/%m/%Y} → έναρξη {cert + timedelta(days=1):%d/%m/%Y} + "
                             f"{months} μήνες ({src}) = λήξη {expiry:%d/%m/%Y}")
        if ended_evidence or out["days_remaining"] < 0:
            out["state"] = EXPIRED
        elif conflicts or start["basis"] == INFERRED:
            out["state"] = REQUIRES_HUMAN_REVIEW
        else:
            out["state"] = ACTIVE
    out["state_el"] = LABELS_EL[out["state"]]
    out["requires_review"] = bool(review) or out["state"] in (REQUIRES_HUMAN_REVIEW, UNKNOWN) or basis != CONTRACTUALLY_VERIFIED
    return out
