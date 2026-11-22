"""Stoa layer: public-works memory and guarantee clock, joined to citizen reports.

Serving side only. It reads precomputed works records (the Stoa build pipeline's
output: Diavgeia + ΚΗΜΔΗΣ -> AI extraction -> quote verifier -> street match) and
applies deterministic rules. The AI never sets a date, tier or claim here.

Data file (first one found):
  1. $STOA_WORKS_PATH
  2. data/stoa/works.json      <- drop the pipeline output here (source "LIVE-CACHE")
  3. data/works_seed.json      <- fictional demo records (source "SEED", always labelled)

Every field is an evidence-wrapped value:
  {"value": ..., "label": "CITED|INFERRED|UNKNOWN", "source": {"ada": ..., "page": ...}, "quote": ...}

Guarantee rule (ν. 4412/2016 art. 171, general rule 15 months from certified completion;
confirm wording with Legal Services). Wording is always "possibly within the guarantee period".
"""
from __future__ import annotations

import json
import math
import os
from datetime import date
from pathlib import Path

from . import config

DEFAULT_TERM_MONTHS = 15
REPORT_MATCH_M = 25  # a report this close to a works line is linked to it

# Which report categories can be a defect of which works type
CATEGORY_WORKS = {
    "sidewalk": {"sidewalk", "ramp", "paving"},
    "pothole": {"asphalt", "paving"},
    "streetlight": {"lighting"},
    "water_leak": set(),  # usually a utility (ΕΥΔΑΠ): out of scope in v1
}
WORKS_EL = {"sidewalk": "Ανακατασκευή πεζοδρομίου", "ramp": "Ράμπες ΑμεΑ", "paving": "Πλακόστρωση",
            "asphalt": "Ασφαλτόστρωση", "lighting": "Ηλεκτροφωτισμός", "roadworks": "Οδοποιία / δίκτυα",
            "traffic_control": "Σύστημα ελέγχου πρόσβασης οχημάτων"}

_cache: dict = {}


def _path() -> Path:
    for p in (os.getenv("STOA_WORKS_PATH"), config.DATA_DIR / "stoa" / "works.json",
              config.DATA_DIR / "works_seed.json"):
        if p and Path(p).exists():
            return Path(p)
    raise FileNotFoundError("no works data (data/works_seed.json missing)")


def dataset() -> dict:
    p = _path()
    mtime = p.stat().st_mtime
    if _cache.get("key") != (str(p), mtime):
        _cache["key"] = (str(p), mtime)
        _cache["data"] = json.loads(p.read_text(encoding="utf-8"))
    return _cache["data"]


def today() -> date:
    t = os.getenv("STOA_TODAY")  # pin the date for tests and rehearsals
    return date.fromisoformat(t) if t else date.today()


# ------------------------------------------------------------------ rules
def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    days = [31, 29 if (y % 4 == 0 and (y % 100 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(y, m, min(d.day, days[m - 1]))


def _v(field):
    return (field or {}).get("value")


def clock(w: dict) -> dict:
    """Deterministic guarantee clock + tier for one works record."""
    comp, term = w.get("completion_date") or {}, w.get("guarantee_months") or {}
    street = w.get("street") or {}
    out = {"until": None, "status": "UNKNOWN", "tier": "?", "formula": None, "days_left": None,
           "term_label": None, "anchor_label": comp.get("label", "UNKNOWN")}
    if not comp.get("value") or comp.get("label") == "UNKNOWN":
        out["formula"] = "Δεν βρέθηκε βεβαιωμένη περάτωση: ελέγξτε τις αποφάσεις χειροκίνητα"
        return out
    anchor = date.fromisoformat(comp["value"])
    if term.get("value") and term.get("label") == "CITED":
        months, out["term_label"] = int(term["value"]), "CITED"
        src = "όρος σύμβασης"
    else:
        months, out["term_label"] = DEFAULT_TERM_MONTHS, "INFERRED"
        src = "γενικός κανόνας άρθ. 171 ν. 4412/2016"
    until = add_months(anchor, months)
    out["until"] = until.isoformat()
    out["days_left"] = (until - today()).days
    out["formula"] = f"{anchor:%d/%m/%Y} + {months} μήνες ({src}) = {until:%d/%m/%Y}"
    ended = out["days_left"] < 0 or bool(w.get("final_acceptance"))
    out["status"] = "ENDED" if ended else "ACTIVE"
    street_ok = street.get("label") in ("CITED",) and w.get("resolution", "street") == "street"
    if street_ok and comp.get("label") == "CITED" and out["term_label"] == "CITED":
        out["tier"] = "A"
    elif street.get("label") in ("CITED", "INFERRED"):
        out["tier"] = "B"
    return out


def card(w: dict) -> dict:
    c = clock(w)
    return {**w, "clock": c, "works_type_el": WORKS_EL.get(w.get("works_type"), w.get("works_type")),
            "headline_el": headline(w, c)}


def headline(w: dict, c: dict) -> str:
    if c["status"] == "UNKNOWN":
        return "Άγνωστη ημερομηνία περάτωσης: δεν υπολογίζεται εγγύηση"
    until = date.fromisoformat(c["until"])
    if c["status"] == "ENDED":
        return f"Η περίοδος εγγύησης έληξε στις {until:%d/%m/%Y}"
    if c["tier"] == "A":
        return f"Πιθανώς εντός περιόδου εγγύησης έως {until:%d/%m/%Y}"
    return f"Πιθανώς εντός εγγύησης έως {until:%d/%m/%Y} · επιβεβαιώστε στη σύμβαση"


# ------------------------------------------------------------------ geometry
def _dist_m(lat, lng, line) -> float:
    """Distance from a point to a [[lng,lat],...] polyline, metres (equirectangular, fine at city scale)."""
    k = 111_320.0
    kx = k * math.cos(math.radians(lat))
    px, py = lng * kx, lat * k
    best = float("inf")
    pts = [(x * kx, y * k) for x, y in line]
    for (ax, ay), (bx, by) in zip(pts, pts[1:] or pts):
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


# ------------------------------------------------------------------ queries
def meta() -> dict:
    d = dataset()
    return {"source": d.get("source", "SEED"), "snapshot": d.get("snapshot"),
            "organisation": d.get("organisation"), "count": len(d.get("works", [])), "note": d.get("note")}


def all_cards() -> list[dict]:
    """All works records as cards (clock + headline), cached per (data file, mtime, today).

    The cache lives in `_cache` so tests that call `works._cache.clear()` also drop it. `today()` is part
    of the key because the guarantee clock (days_left, ACTIVE/ENDED) depends on the date.
    Shallow copies are returned so a caller adding a top-level key never leaks into the cache.
    """
    p = _path()
    key = (str(p), p.stat().st_mtime, today().isoformat())
    if _cache.get("cards_key") != key or "cards" not in _cache:
        _cache["cards"] = [card(w) for w in dataset().get("works", [])]
        _cache["cards_key"] = key
    return [dict(c) for c in _cache["cards"]]


def near(lat: float, lng: float, radius_m: float = 300) -> list[dict]:
    out = []
    for c in all_cards():
        dm = _dist_m(lat, lng, c["geometry"]["coordinates"])
        if dm <= radius_m:
            out.append({**c, "distance_m": round(dm)})
    return sorted(out, key=lambda c: c["distance_m"])


def for_report(lat, lng, category) -> dict | None:
    """Best works record that could explain this report, or None."""
    from .categories import STOA_TYPES  # central mapping (audit F-1); CATEGORY_WORKS kept for old importers

    types = STOA_TYPES.get(category) or CATEGORY_WORKS.get(category)
    if not types or lat is None:
        return None
    cands = [c for c in near(lat, lng, REPORT_MATCH_M)
             if set(c.get("works_types") or [c.get("works_type")]) & set(types)]
    if not cands:
        return None
    order = {"ACTIVE": 0, "UNKNOWN": 1, "ENDED": 2}
    cands.sort(key=lambda c: (order[c["clock"]["status"]], c["distance_m"]))
    return cands[0]


def radar(days: int = 90) -> dict:
    items = [c for c in all_cards() if c["clock"]["status"] == "ACTIVE" and c["clock"]["days_left"] <= days]
    items.sort(key=lambda c: (c["clock"]["until"], -(_v(c.get("amount_paid_eur")) or 0)))
    cards = all_cards()
    usable = sum(1 for c in cards if c["clock"]["status"] != "UNKNOWN")
    return {"window_days": days, "items": items,
            "total_eur": round(sum(_v(c.get("amount_paid_eur")) or 0 for c in items), 2),
            "coverage": {"usable": usable, "total": len(cards)}, **meta()}


def geojson() -> dict:
    feats = []
    for c in all_cards():
        props = {k: c[k] for k in ("id", "works_type", "works_type_el", "headline_el")}
        props.update(street=_v(c.get("street")), contractor=_v(c.get("contractor")),
                     amount_paid_eur=_v(c.get("amount_paid_eur")), year=(_v(c.get("completion_date")) or "")[:4],
                     ada=(c.get("completion_date") or {}).get("source", {}).get("ada"),
                     status=c["clock"]["status"], tier=c["clock"]["tier"], until=c["clock"]["until"])
        feats.append({"type": "Feature", "geometry": c["geometry"], "properties": props})
    return {"type": "FeatureCollection", "features": feats, "meta": meta()}


def dossier(report: dict, w: dict) -> str:
    """Draft for an engineer to review and sign. Facts are injected from data; nothing is sent."""
    c = w["clock"]

    def ev(name, label_el, fmt=lambda x: x):
        f = w.get(name) or {}
        if f.get("value") in (None, ""):
            return f"- {label_el}: ΑΓΝΩΣΤΟ"
        s = f.get("source") or {}
        q = f" · «{f['quote']}»" if f.get("quote") else ""
        return f"- {label_el}: {fmt(f['value'])} [{f.get('label')}, ΑΔΑ {s.get('ada', '-')}, σελ. {s.get('page', '-')}]{q}"

    src = meta()
    lines = [
        "ΠΡΟΣΧΕΔΙΟ · ΠΡΟΣ ΕΛΕΓΧΟ ΚΑΙ ΥΠΟΓΡΑΦΗ ΑΠΟ ΤΗΝ ΕΠΙΒΛΕΠΟΥΣΑ ΥΠΗΡΕΣΙΑ · ΔΕΝ ΕΧΕΙ ΑΠΟΣΤΑΛΕΙ",
        f"Πηγή δεδομένων: {src['source']} (στιγμιότυπο {src.get('snapshot') or '-'})",
        "",
        f"Θέμα: Αίτημα αποκατάστασης βλάβης πιθανώς εντός περιόδου εγγύησης · {_v(w.get('street'))}",
        "",
        f"Αναφορά πολίτη: {report.get('id')} · {report.get('title')} · {report.get('address')}",
        f"Απόσταση αναφοράς από το έργο: ~{w.get('distance_m', '?')} m",
        "",
        f"Έργο: {w['works_type_el']} · {_v(w.get('title')) or ''}".rstrip(" ·"),
        ev("contractor", "Ανάδοχος"),
        ev("amount_paid_eur", "Ποσό πληρωμών (€)", lambda x: f"{x:,.2f}"),
        ev("completion_date", "Βεβαιωμένη περάτωση"),
        ev("guarantee_months", "Χρόνος εγγύησης (μήνες)") if (w.get("guarantee_months") or {}).get("value")
        else f"- Χρόνος εγγύησης: {DEFAULT_TERM_MONTHS} μήνες [INFERRED: γενικός κανόνας άρθ. 171 ν. 4412/2016]",
        f"- Υπολογισμός: {c['formula']}",
        "",
        f"Συμπέρασμα (προς επιβεβαίωση): {w['headline_el']}.",
        "Η επιβλέπουσα υπηρεσία και η Νομική Υπηρεσία αποφασίζουν αν ο ανάδοχος υποχρεούται σε αποκατάσταση.",
        "Πριν την αποστολή: επιβεβαιώστε ότι πρόκειται για κακοτεχνία/φθορά του έργου και όχι για εμπόδιο,",
        "βανδαλισμό ή εκσκαφή οργανισμού κοινής ωφέλειας.",
        "",
        "Ο/Η μηχανικός: ____________________   Ημερομηνία: ____________",
    ]
    return "\n".join(lines)
