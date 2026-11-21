"""Greek, informal Greek, Greeklish, typo-tolerant & English NLU helpers (Priority 3).

Pure, zero-external-dependency linguistic layer used by vision.py, stoa_ask.py, and stoa_map.py:
  - Language detection: Greek ('el'), English ('en'), or mixed ('mixed')
  - Greeklish -> Greek transliteration (handles Athens neighbourhoods, streets, civic terms, digraphs)
  - Typo-tolerant keyword matching (SequenceMatcher fuzzy matching)
  - Structured citizen report interpretation (preserves original_note verbatim, marks AI-GENERATED,
    suggests municipal department, urgency, and clarification questions without inventing facts)
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Any

_GREEK_RE = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# High-value Greeklish vocabulary & Athens place/civic dictionary (applied before character digraph rules).
_GREEKLISH_WORDS: dict[str, str] = {
    "syntagma": "συνταγμα",
    "monastiraki": "μοναστηρακι",
    "omonoia": "ομονοια",
    "omonia": "ομονοια",
    "pagkrati": "παγκρατι",
    "pangrati": "παγκρατι",
    "pankrati": "παγκρατι",
    "kypseli": "κυψελη",
    "kipseli": "κυψελη",
    "kolonaki": "κολωνακι",
    "exarcheia": "εξαρχεια",
    "exarchia": "εξαρχεια",
    "petralona": "πετραλωνα",
    "koukaki": "κουκακι",
    "ermou": "ερμου",
    "patision": "πατησιων",
    "stadiou": "σταδιου",
    "panepistimiou": "πανεπιστημιου",
    "akadimias": "ακαδημιασ",
    "vasilissis": "βασιλισσησ",
    "sofias": "σοφιασ",
    "athinas": "αθηνασ",
    "farmakeio": "φαρμακειο",
    "farmakio": "φαρμακειο",
    "farmakeia": "φαρμακεια",
    "nosokomeio": "νοσοκομειο",
    "nosokomio": "νοσοκομειο",
    "efimerevei": "εφημερευει",
    "efimereuei": "εφημερευει",
    "efimeria": "εφημερια",
    "efimeries": "εφημεριεσ",
    "erga": "εργα",
    "ergo": "εργο",
    "ergasies": "εργασιεσ",
    "pezodromio": "πεζοδρομιο",
    "pezodromia": "πεζοδρομια",
    "rampa": "ραμπα",
    "rampes": "ραμπεσ",
    "lakouva": "λακκουβα",
    "lakkouva": "λακκουβα",
    "lakouves": "λακκουβεσ",
    "asfaltostrosi": "ασφαλτοστρωση",
    "plakostrosi": "πλακοστρωση",
    "fotismos": "φωτισμοσ",
    "fanostatis": "φανοστατησ",
    "skoupidia": "σκουπιδια",
    "kados": "καδοσ",
    "kadoi": "καδοι",
    "diarroi": "διαρροη",
    "diaroi": "διαρροη",
    "nero": "νερο",
    "empodio": "εμποδιο",
    "spasmeno": "σπασμενο",
    "spasmeni": "σπασμενη",
    "spasmenes": "σπασμενεσ",
    "kleisto": "κλειστο",
    "klisto": "κλειστο",
    "amaksidio": "αμαξιδιο",
    "amaxidio": "αμαξιδιο",
    "karotsi": "καροτσι",
    "eggyisi": "εγγυηση",
    "eggiisi": "εγγυηση",
    "anadoxos": "αναδοχοσ",
    "anadohos": "αναδοχοσ",
    "kostos": "κοστοσ",
    "poio": "ποιο",
    "poios": "ποιοσ",
    "pou": "που",
    "ti": "τι",
    "pote": "ποτε",
    "stin": "στην",
    "sto": "στο",
    "ston": "στον",
    "sti": "στη",
}

# Athens place names written in Latin script are bilingual (used in both English and Greeklish),
# so they must NOT alone classify an English sentence like "Water leak near Syntagma square" as Greeklish.
_BILINGUAL_PLACE_NAMES = frozenset({
    "syntagma", "monastiraki", "omonoia", "omonia", "pagkrati", "pangrati", "pankrati",
    "kypseli", "kipseli", "kolonaki", "exarcheia", "exarchia", "petralona", "koukaki",
    "ermou", "patision", "stadiou", "panepistimiou", "akadimias", "vasilissis", "sofias", "athinas",
})

_GREEKLISH_MARKERS = (frozenset(_GREEKLISH_WORDS.keys()) - _BILINGUAL_PLACE_NAMES) | frozenset({
    "kalimera", "kalispera", "geia", "parakalo", "efxaristo", "eyxaristo", "einai", "ine",
    "exei", "ehei", "mporei", "thelo", "telo", "dromo", "dromos", "plateia", "platia",
})

_DIGRAPHS: tuple[tuple[str, str], ...] = (
    ("th", "θ"), ("ch", "χ"), ("ps", "ψ"), ("ks", "ξ"), ("ou", "ου"),
    ("ai", "αι"), ("ei", "ει"), ("oi", "οι"), ("mp", "μπ"), ("nt", "ντ"),
)
_CHAR_MAP = str.maketrans({
    "a": "α", "b": "β", "g": "γ", "d": "δ", "e": "ε", "z": "ζ", "h": "η",
    "i": "ι", "k": "κ", "l": "λ", "m": "μ", "n": "ν", "x": "ξ", "o": "ο",
    "p": "π", "r": "ρ", "s": "σ", "t": "τ", "u": "υ", "y": "υ", "f": "φ",
    "v": "β", "w": "ω", "c": "κ", "j": "ζ", "q": "κ",
})

# English civic terms mapped to Greek stems for unified retrieval/classification.
_EN_TO_EL_TERMS: dict[str, str] = {
    "pharmacy": "φαρμακειο",
    "pharmacies": "φαρμακεια",
    "hospital": "νοσοκομειο",
    "hospitals": "νοσοκομεια",
    "duty": "εφημερια",
    "onduty": "εφημερια",
    "sidewalk": "πεζοδρομιο",
    "pavement": "πεζοδρομιο",
    "ramp": "ραμπα",
    "wheelchair": "αμαξιδιο",
    "pothole": "λακκουβα",
    "potholes": "λακκουβεσ",
    "streetlight": "φανοστατησ",
    "lighting": "φωτισμοσ",
    "garbage": "σκουπιδια",
    "trash": "σκουπιδια",
    "bin": "καδοσ",
    "works": "εργα",
    "work": "εργο",
    "roadwork": "εργα",
    "construction": "εργα",
    "asphalt": "ασφαλτοστρωση",
    "paving": "πλακοστρωση",
    "contractor": "αναδοχοσ",
    "guarantee": "εγγυηση",
    "warranty": "εγγυηση",
    "leak": "διαρροη",
    "water": "νερο",
    "blocked": "εμποδιο",
    "obstacle": "εμποδιο",
    "broken": "σπασμενο",
    "cracked": "ραγισμενο",
    "tree": "δεντρο",
    "graffiti": "γκραφιτι",
    "abandoned": "εγκαταλελειμμενο",
}

# Department routing table for structured citizen report interpretation (Municipality of Athens).
DEPARTMENT_MAP: dict[str, str] = {
    "sidewalk": "Διεύθυνση Οδοποιίας, Αποχέτευσης & Κοινοχρήστων Χώρων",
    "pothole": "Διεύθυνση Οδοποιίας & Συντήρησης Οδικού Δικτύου",
    "streetlight": "Διεύθυνση Ηλεκτρολογικού & Δημοτικού Φωτισμού",
    "garbage": "Διεύθυνση Καθαριότητας & Ανακύκλωσης",
    "bulky_waste": "Διεύθυνση Καθαριότητας & Ανακύκλωσης",
    "tree": "Διεύθυνση Πρασίνου & Αστικής Πανίδας",
    "water_leak": "Συντονισμός με ΕΥΔΑΠ / Τεχνικές Υπηρεσίες Δήμου",
    "graffiti": "Διεύθυνση Καθαριότητας (Συνεργεία Αντι-γκράφιτι)",
    "abandoned_vehicle": "Δημοτική Αστυνομία / Τμήμα Εγκαταλελειμμένων Οχημάτων",
    "noise": "Δημοτική Αστυνομία",
    "stray_animals": "Τμήμα Αστικής Πανίδας Δήμου Αθηναίων",
    "other": "Κέντρο Εξυπηρέτησης & Διαλογής Αναφορών Δήμου Αθηναίων",
}

_ATHENS_LOCATION_HINTS: tuple[str, ...] = (
    "συνταγμα", "μοναστηρακι", "ομονοια", "παγκρατι", "κυψελη", "κολωνακι",
    "εξαρχεια", "πετραλωνα", "κουκακι", "ερμου", "πατησιων", "σταδιου",
    "πανεπιστημιου", "ακαδημιασ", "αθηνασ", "βαρναβα", "σεραφειο", "ακροπολη",
    "μετσ", "γκαζι", "θησειο", "πλακα", "αμπελοκηποι", "γουδι", "πατησια",
)


def fold_greek(text: str) -> str:
    """Lowercase, strip diacritics, unify final sigma, collapse spaces."""
    nfd = unicodedata.normalize("NFD", str(text or ""))
    no_marks = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return " ".join(no_marks.lower().replace("ς", "σ").split())


def is_greeklish(text: str) -> bool:
    """True when Latin-script text contains recognisable Greeklish civic/Athens tokens."""
    if _GREEK_RE.search(text or ""):
        return False
    tokens = re.findall(r"[a-z]+", (text or "").lower())
    return any(t in _GREEKLISH_MARKERS for t in tokens)


def detect_language(text: str) -> str:
    """Return 'el', 'en', or 'mixed'. Greeklish is treated as 'el' (user expects Greek reply)."""
    sample = str(text or "").strip()
    if not sample:
        return "el"
    gr = len(_GREEK_RE.findall(sample))
    lat = len(_LATIN_RE.findall(sample))
    if gr > 0 and lat > 0:
        ratio = gr / (gr + lat)
        if 0.2 <= ratio <= 0.8:
            return "mixed"
        return "el" if gr >= lat else "en"
    if gr > 0:
        return "el"
    if is_greeklish(sample):
        return "el"
    return "en"


def greeklish_to_greek(text: str) -> str:
    """Convert Greeklish words and common English civic terms into accent-free Greek tokens."""
    tokens = re.findall(r"[0-9A-Za-z\u0370-\u03ff\u1f00-\u1fff]+", str(text or ""))
    out: list[str] = []
    for raw_tok in tokens:
        folded = fold_greek(raw_tok)
        if _GREEK_RE.search(folded):
            out.append(folded)
            continue
        if folded in _GREEKLISH_WORDS:
            out.append(_GREEKLISH_WORDS[folded])
            continue
        if folded in _EN_TO_EL_TERMS:
            out.append(_EN_TO_EL_TERMS[folded])
            continue
        # Only transliterate Latin tokens when the sentence looks Greeklish (avoid mangling English words).
        if is_greeklish(text):
            converted = folded
            for dg, gr in _DIGRAPHS:
                converted = converted.replace(dg, gr)
            out.append(converted.translate(_CHAR_MAP))
        else:
            out.append(folded)
    return " ".join(out)


def exact_matches_any(text: str, keywords: list[str] | tuple[str, ...]) -> bool:
    """Exact substring match across accent-folded Greek and Greeklish/English-expanded text."""
    folded = fold_greek(text)
    gl = greeklish_to_greek(text)
    combined = f"{folded} {gl}"
    return any(fold_greek(kw) in combined for kw in keywords if kw)


def fuzzy_matches_any(text: str, keywords: list[str] | tuple[str, ...], cutoff: float = 0.84) -> bool:
    """Exact substring match, or high-precision fuzzy match for typos in longer words (len >= 6)."""
    folded = fold_greek(text)
    gl = greeklish_to_greek(text)
    combined = f"{folded} {gl}"
    tokens = [t for t in re.findall(r"[a-z\u0370-\u03ff]{5,}", combined)]
    for kw in keywords:
        k = fold_greek(kw)
        if not k:
            continue
        if k in combined:
            return True
        # Only fuzzy-match longer stems (>= 6 chars) so distinct short words like ράμπα/λάμπα never collide.
        if len(k) >= 6:
            for tok in tokens:
                if abs(len(tok) - len(k)) <= 2 and difflib.SequenceMatcher(None, tok, k).ratio() >= cutoff:
                    return True
    return False


def extract_location_hint(text: str) -> str | None:
    """Extract an Athens street/neighbourhood hint if mentioned in the citizen's note."""
    gl = greeklish_to_greek(text)
    for place in _ATHENS_LOCATION_HINTS:
        if place in gl:
            return place
    m = re.search(r"(?:οδ[οό]ς?|λεωφ\.?|πλατε[ιί]α)\s+([^\n,.;]{3,35})", str(text or ""), re.IGNORECASE)
    if m:
        return m.group(0).strip()
    return None


def interpret_report(note: str, ai_result: dict[str, Any]) -> dict[str, Any]:
    """Build a structured, clearly AI-GENERATED interpretation while preserving the original note verbatim."""
    original = str(note or "")
    lang = detect_language(original)
    category = str(ai_result.get("category") or "other")
    severity = int(ai_result.get("severity") or 3)
    blocker = bool(ai_result.get("accessibility_blocker", False))
    confidence = float(ai_result.get("confidence") or 0.5)
    location_hint = extract_location_hint(original)

    if blocker or severity >= 5:
        urgency = "critical"
    elif severity >= 4:
        urgency = "high"
    elif severity == 3:
        urgency = "medium"
    else:
        urgency = "low"

    clarifications: list[str] = []
    if not original.strip():
        clarifications.append("Προσθέστε σύντομη περιγραφή του προβλήματος." if lang != "en" else "Please add a short description of the issue.")
    if confidence < 0.75:
        clarifications.append(
            "Επιβεβαιώστε την ακριβή κατηγορία βλάβης πριν την έγκριση."
            if lang != "en"
            else "Please confirm the exact issue category before operator approval."
        )

    dept = DEPARTMENT_MAP.get(category, DEPARTMENT_MAP["other"])
    urgency_el = {"critical": "Κρίσιμη", "high": "Υψηλή", "medium": "Μέτρια", "low": "Χαμηλή"}[urgency]
    op_summary = (
        f"[AI-GENERATED] Κατηγορία: {category} · Επείγον: {urgency_el}"
        + (" · Εμπόδιο προσβασιμότητας (ΑμεΑ)" if blocker else "")
        + (f" · Σημείο αναφοράς: {location_hint}" if location_hint else "")
        + f" · Προτεινόμενη διεύθυνση: {dept}. Απαιτείται έγκριση χειριστή."
    )

    return {
        "original_note": original,
        "detected_language": lang,
        "issue_type": category,
        "department_el": dept,
        "urgency": urgency,
        "location_hint": location_hint,
        "needs_clarification": len(clarifications) > 0,
        "clarification_questions": clarifications,
        "operator_summary_el": op_summary,
        "suggested_action_el": f"Έλεγχος από χειριστή και προώθηση σε: {dept} (δεν έχει εγκριθεί ακόμη).",
        "provenance": "AI-GENERATED",
        "verified": False,
    }
