"""Stoa geospatial matching: which public-works records could be relevant to a citizen report, and why.

Proximity is not responsibility. A contract that covers a whole Δημοτική Κοινότητα or the whole municipality is
not evidence that *this* pavement was worked on. So every candidate gets one of these match types, from strongest
to weakest, and the confidence follows the type, not just the distance:

  EXACT          street-scoped contract, documented geometry, report within EXACT_M of it
  STREET         street-scoped contract (the street is named in the decision), report within STREET_M
  NEIGHBOURHOOD  contract names the Δημοτική Κοινότητα the report is in (no street named)
  MUNICIPALITY   contract covers the whole municipality ("όλες τις Δ.Κ.", "του Δ.Α.")
  PROXIMITY      only near a geometry we drew ourselves; nothing in the text ties it to this spot
  (no candidates) NONE

Scope is read from the decision title. The suffix "(τμήμα X)" in our dataset is an AthensOne annotation (a
representative segment we drew for the map), not text from the decision, and is treated as such.
The matcher is pure: works records, report point, report district and human reviews in; candidates out.
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import date

from . import guarantee

EXACT_M = 15        # our choice: a pin dropped by hand on a phone is usually within ~10-15 m
STREET_M = 40       # our choice: same street, allowing for the width of the road and pin error
SEARCH_M = 300      # candidates beyond this are only considered when their scope covers the district/city

BASE_CONF = {"EXACT": 0.9, "STREET": 0.7, "NEIGHBOURHOOD": 0.4, "MUNICIPALITY": 0.2, "PROXIMITY": 0.15}
TYPE_EL = {
    "EXACT": "Ακριβής γεωγραφική αντιστοίχιση",
    "STREET": "Αντιστοίχιση σε επίπεδο οδού",
    "NEIGHBOURHOOD": "Αντιστοίχιση σε επίπεδο Δημοτικής Κοινότητας",
    "MUNICIPALITY": "Σύμβαση για όλο τον Δήμο",
    "PROXIMITY": "Μόνο γεωγραφική εγγύτητα",
    "NONE": "Καμία αξιόπιστη αντιστοίχιση",
}

_ANNOT = re.compile(r"\s*\((τμήμα|τμ\.)\s+([^)]+)\)\s*$", re.I)
_ORD = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7}


def _fold(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _v(f):
    return f.get("value") if isinstance(f, dict) else f


def scope_of(w: dict) -> dict:
    """Geographic scope stated by the decision title (or by an explicit `scope` override in the record)."""
    if isinstance(w.get("scope"), dict) and w["scope"].get("level"):
        s = dict(w["scope"])
        s.setdefault("districts", [])
        s.setdefault("evidence", "Ορίστηκε ρητά στην εγγραφή.")
        s.setdefault("annotation", None)
        return s
    title = _v(w.get("title")) or ""
    m = _ANNOT.search(title)
    annotation = m.group(2).strip() if m else None
    core = _ANNOT.sub("", title)
    f = _fold(core)
    districts = sorted({_ORD[d] for d in re.findall(r"(?<!\d)([1-7])\s*(?:η|ης)?(?!\d)", f)
                        if re.search(r"δ\.?\s*κ\.?|δημοτικ\w*\s+κοινοτ", f)})
    if re.search(r"ολες\s+τις\s+δ\.?\s*κ|του\s+δ\.?\s*α\.?(\s|$|,)|δημου\s+αθηναιων|1η\s*(εως|-)\s*7η", f) and not \
            re.search(r"οδου\s+\w", f):
        level, ev = "municipality", "Ο τίτλος της πράξης αναφέρεται σε όλο τον Δήμο."
        districts = []
    elif districts:
        level, ev = "district", f"Ο τίτλος της πράξης κατονομάζει Δ.Κ.: {', '.join(str(d) for d in districts)}."
    elif re.search(r"(οδου|οδος|επι\s+της\s+οδου|λεωφ)\s+\w+", f):
        level, ev = "street", "Ο τίτλος της πράξης κατονομάζει οδό."
    elif re.search(r"ελαιων|εμπορικο\s+τριγωνο|πλακα|κουκακι|παγκρατι|κυψελη|πατησια|εξαρχει", f):
        level, ev = "neighbourhood", "Ο τίτλος της πράξης κατονομάζει περιοχή, όχι οδό."
    else:
        level, ev = "unspecified", "Ο τίτλος της πράξης δεν ορίζει σαφή γεωγραφική έκταση."
    return {"level": level, "districts": districts, "evidence": ev, "annotation": annotation}


def geometry_basis(w: dict) -> str:
    """'documented' (geometry from an official source), 'representative' (drawn by us) or 'seed'."""
    if w.get("geometry_basis"):
        return w["geometry_basis"]
    ada = str(_v(w.get("ada")) or "")
    if ada.upper().startswith("SEED") or w.get("seed"):
        return "seed"
    return "representative"


def works_types(w: dict) -> set[str]:
    return set(w.get("works_types") or [w.get("works_type")])


def dist_m(lat: float, lng: float, geometry: dict) -> float:
    """Distance from a point to a LineString/Point geometry, metres (equirectangular; fine at city scale)."""
    k = 111_320.0
    kx = k * math.cos(math.radians(lat))
    coords = geometry.get("coordinates") or []
    if geometry.get("type") == "Point":
        coords = [coords, coords]
    px, py = lng * kx, lat * k
    pts = [(x * kx, y * k) for x, y in coords] or [(px + 1e9, py)]
    if len(pts) == 1:
        pts = pts * 2
    best = float("inf")
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def district_number(name: str | None) -> int | None:
    m = re.match(r"\s*([1-7])", name or "")
    return int(m.group(1)) if m else None


def _classify(w: dict, d: float, district: int | None) -> tuple[str | None, list[str], list[str]]:
    sc, basis = scope_of(w), geometry_basis(w)
    ev, unc = [f"Απόσταση από τη γεωμετρία του έργου: ~{round(d)} m."], []
    if sc["annotation"]:
        unc.append(f"Το τμήμα «{sc['annotation']}» είναι ενδεικτική χάραξη του AthensOne, όχι κείμενο της πράξης.")
    if basis == "representative":
        unc.append("Η γεωμετρία σχεδιάστηκε ενδεικτικά· δεν προέρχεται από τα τεύχη της σύμβασης.")
    ev.append(sc["evidence"])
    lvl = sc["level"]
    if lvl == "street":
        if d <= EXACT_M and basis == "documented":
            return "EXACT", ev, unc
        if d <= STREET_M:
            return "STREET", ev, unc
        if d <= SEARCH_M:
            unc.append("Η αναφορά δεν βρίσκεται πάνω στην οδό του έργου.")
            return "PROXIMITY", ev, unc
        return None, ev, unc
    if lvl == "district":
        if district is not None and district in sc["districts"]:
            ev.append(f"Η αναφορά βρίσκεται στην {district}η Δ.Κ., που κατονομάζεται στην πράξη.")
            unc.append("Η σύμβαση καλύπτει ολόκληρη Δ.Κ.: δεν αποδεικνύει εργασίες σε αυτό το σημείο.")
            return "NEIGHBOURHOOD", ev, unc
        if district is None and d <= SEARCH_M:
            unc.append("Άγνωστη Δ.Κ. της αναφοράς· μόνο εγγύτητα.")
            return "PROXIMITY", ev, unc
        return None, ev, unc
    if lvl == "municipality":
        unc.append("Σύμβαση για όλο τον Δήμο: η εγγύτητα δεν σημαίνει ότι εκτελέστηκαν εργασίες εδώ.")
        return ("MUNICIPALITY" if d <= SEARCH_M else None), ev, unc
    if d <= SEARCH_M:
        unc.append("Η έκταση του έργου δεν είναι σαφής στην πράξη.")
        return "PROXIMITY", ev, unc
    return None, ev, unc


def match(lat: float | None, lng: float | None, types: list[str] | set[str], works: list[dict], today: date,
          district: str | None = None, reviews: dict[str, dict] | None = None) -> dict:
    """Rank works records that could be relevant to a report. Pure."""
    reviews = reviews or {}
    types = set(types or [])
    if lat is None or lng is None:
        return {"match_type": "NONE", "match_type_el": TYPE_EL["NONE"], "candidates": [], "best": None,
                "explanation": "Η αναφορά δεν έχει θέση."}
    if not types:
        return {"match_type": "NONE", "match_type_el": TYPE_EL["NONE"], "candidates": [], "best": None,
                "explanation": "Η κατηγορία της αναφοράς δεν συνδέεται με τύπο δημόσιου έργου· "
                               "αλλάξτε κατηγορία αν πρόκειται για φθορά έργου."}
    dnum = district_number(district)
    cands = []
    for w in works:
        if not (works_types(w) & types):
            continue
        d = dist_m(lat, lng, w.get("geometry") or {})
        mt, ev, unc = _classify(w, d, dnum)
        if not mt:
            continue
        conf = BASE_CONF[mt]
        if geometry_basis(w) == "representative" and mt in ("EXACT", "STREET"):
            conf -= 0.15
        if mt == "PROXIMITY" and d <= STREET_M:
            conf = 0.3  # right on the drawn line: worth a look, still far from proof
        conf -= min(0.1, d / 3000)  # a little less sure the further away
        g = guarantee.evaluate(w, today)
        rv = reviews.get(w["id"])
        cands.append({
            "work_id": w["id"], "distance_m": round(d), "match_type": mt, "match_type_el": TYPE_EL[mt],
            "confidence": round(max(0.05, conf), 2), "evidence": ev, "uncertainty": unc,
            "scope": scope_of(w), "geometry_basis": geometry_basis(w), "guarantee": g,
            "review": rv, "rejected": bool(rv and rv.get("verdict") == "reject"),
            "accepted": bool(rv and rv.get("verdict") == "accept"),
        })
    order = list(BASE_CONF)
    cands.sort(key=lambda c: (not c["accepted"], c["rejected"], -c["confidence"], order.index(c["match_type"]),
                              c["distance_m"]))
    live = [c for c in cands if not c["rejected"]]
    best = live[0] if live else None
    mt = best["match_type"] if best else "NONE"
    if best is None:
        expl = ("Δεν βρέθηκε σχετικό δημόσιο έργο στα δεδομένα της Stoa." if not cands else
                "Όλες οι υποψήφιες αντιστοιχίσεις απορρίφθηκαν από υπάλληλο.")
    else:
        expl = (f"Πιθανώς σχετικό έργο: {best['work_id']} ({TYPE_EL[mt]}, βεβαιότητα {best['confidence']:.0%}). "
                "Η αντιστοίχιση είναι ένδειξη, όχι απόδειξη ευθύνης αναδόχου.")
    return {"match_type": mt, "match_type_el": TYPE_EL[mt], "candidates": cands, "best": best, "explanation": expl}
