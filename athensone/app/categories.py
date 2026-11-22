"""Central category normalisation: one place that turns what a citizen picked into what the city and Stoa use.

Why this exists (FINAL_ENGINEERING_AUDIT.md, finding F-1): the citizen map sends `damage`/`obstacle`, the legacy
photo flow sends sandbox categories (`sidewalk`, `pothole`, ...), and Stoa keyed its lookup on sandbox categories
only. A damaged sidewalk reported from the map became sandbox `other` and never reached Stoa.

Rules, in order (deterministic; an AI label is only ever an input, never the final word):
  1. The citizen's own subtype choice (e.g. damage + sidewalk) wins: confidence 0.9.
  2. A sandbox category sent directly (legacy flow / operator reclassification) is taken as is: 0.85.
  3. Keywords in the citizen's note (Greek + English stems): 0.6 and flagged for review.
  4. Otherwise `other` with no Stoa works types: Stoa is not run and the case is flagged for review.
The original category, subtype and note are always kept next to the result.
"""
from __future__ import annotations

import re
import unicodedata

# Sandbox categories (app/sandbox.py CATEGORIES; from the sandbox OpenAPI spec). Certainty: verified.
SANDBOX = ("pothole", "streetlight", "garbage", "bulky_waste", "graffiti", "tree", "sidewalk",
           "abandoned_vehicle", "noise", "stray_animals", "water_leak", "other")

# Citizen-facing subtypes for «Ζημιά» / «Εμπόδιο» (web/js/ui/report.js SUBTYPES). Our choice, owner-visible.
SUBTYPES = {
    "sidewalk": "Πεζοδρόμιο / πλάκες",
    "ramp": "Ράμπα ΑμεΑ",
    "pothole": "Λακκούβα / οδόστρωμα",
    "streetlight": "Φωτισμός",
    "other": "Άλλο",
}

# Which works types can explain a defect of each sandbox category. A works type is the `works_type` (or one of
# `works_types`) of a record in data/stoa/works.json. Source: engineering judgement, same as the original
# app/works.py CATEGORY_WORKS, widened with `roadworks`. Certainty: reasonable, not legal advice.
STOA_TYPES: dict[str, frozenset[str]] = {
    "sidewalk": frozenset({"sidewalk", "ramp", "paving"}),
    "pothole": frozenset({"asphalt", "paving", "roadworks"}),
    "streetlight": frozenset({"lighting"}),
}

SUBTYPE_TO_SANDBOX = {"sidewalk": "sidewalk", "ramp": "sidewalk", "pothole": "pothole",
                      "streetlight": "streetlight", "other": "other"}

LABEL_EL = {"sidewalk": "Πεζοδρόμιο", "pothole": "Λακκούβα / οδόστρωμα", "streetlight": "Φωτισμός",
            "garbage": "Απορρίμματα", "bulky_waste": "Ογκώδη", "graffiti": "Γκράφιτι", "tree": "Δέντρο",
            "abandoned_vehicle": "Εγκαταλελειμμένο όχημα", "noise": "Θόρυβος", "stray_animals": "Αδέσποτα",
            "water_leak": "Διαρροή νερού", "other": "Άλλο"}

# Keyword stems, accent-free lower case. Certainty: heuristic; anything found this way is flagged for review.
_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sidewalk", ("πεζοδρομ", "πλακ", "πλακακ", "ραμπα", "κρασπεδ", "sidewalk", "pavement", "kerb", "curb")),
    ("pothole", ("λακκουβ", "λακκ", "οδοστρωμ", "ασφαλτ", "pothole", "asphalt")),
    ("streetlight", ("φωτισμ", "λαμπα", "κολων", "σκοταδ", "φανοστατ", "streetlight", "lamp")),
    ("water_leak", ("διαρρο", "νερο", "leak")),
)


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn")


def from_note(note: str) -> str | None:
    """Sandbox category suggested by keywords in a free-text note, or None."""
    t = _fold(note)
    for cat, stems in _KEYWORDS:
        if any(re.search(re.escape(s), t) for s in stems):
            return cat
    return None


def normalise(category: str | None, subtype: str | None = None, note: str = "") -> dict:
    """Normalise a citizen/legacy category. Pure. Returns a dict that is stored with the case."""
    original = (category or "").strip()
    sub = (subtype or "").strip() or None
    reasons: list[str] = []
    method, conf, city = "fallback", 0.3, "other"

    if sub in SUBTYPE_TO_SANDBOX and original in ("damage", "obstacle", ""):
        city, method, conf = SUBTYPE_TO_SANDBOX[sub], "citizen_subtype", 0.9
        reasons.append(f"Ο πολίτης επέλεξε «{SUBTYPES[sub]}».")
    elif original in SANDBOX and original != "other":
        city, method, conf = original, "direct", 0.85
        reasons.append(f"Κατηγορία «{LABEL_EL.get(original, original)}» όπως υποβλήθηκε.")
    else:
        guess = from_note(note)
        if guess:
            city, method, conf = guess, "keywords", 0.6
            reasons.append(f"Λέξεις-κλειδιά στο σχόλιο παραπέμπουν σε «{LABEL_EL[guess]}».")
        elif original == "obstacle":
            # Obstacles are usually objects on the pavement (bins, cars, scaffolding), not a works defect.
            city, method, conf = "sidewalk", "obstacle_default", 0.5
            reasons.append("Εμπόδιο: καταχωρήθηκε ως θέμα πεζοδρομίου· δεν συνδέεται με εγγύηση έργου.")
        else:
            reasons.append("Δεν προκύπτει τεκμηριωμένη κατηγορία· απαιτείται έλεγχος από υπάλληλο.")

    stoa = STOA_TYPES.get(city, frozenset())
    if original == "obstacle" and method != "citizen_subtype":
        stoa = frozenset()
    needs_review = conf < 0.85 or not original
    return {
        "original_category": original or None,
        "original_subtype": sub,
        "city_category": city,
        "label_el": LABEL_EL.get(city, city),
        "stoa_works_types": sorted(stoa),
        "stoa_eligible": bool(stoa),
        "method": method,
        "confidence": conf,
        "needs_review": needs_review,
        "reasons": reasons,
    }
