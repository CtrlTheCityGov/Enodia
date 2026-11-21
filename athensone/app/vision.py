"""Photo classification + draft reply for the operator.

The model only ever receives the BLURRED, EXIF-free photo (see privacy.py).
It suggests; it never dispatches. The operator approves (human in the loop).

Providers (env VISION_PROVIDER):
  anthropic : Claude vision via the Messages API
  openai    : any OpenAI-compatible server (vLLM, Ollama, LM Studio...) with a vision model
  mock      : keyword guess from the user's note, so the demo works offline
"""
from __future__ import annotations

import base64
import json
import re

import httpx

from . import config, language
from .sandbox import CATEGORIES

PROMPT = f"""You triage street-problem reports for the Municipality of Athens (Enodia).
The citizen's note may be in Modern Greek, informal Greek, Greeklish, English, or mixed Greek-English, and may contain spelling mistakes.
Look at the photo (faces and licence plates are already blurred) and the citizen's note.
Never invent facts, never claim an action was approved or a crew was dispatched (a human operator decides).
Write `draft_reply_el` in the citizen's language (Greek for Greek/Greeklish/mixed, English if the note is purely English).
Answer with ONE JSON object, no other text:
{{
  "category": one of {CATEGORIES},
  "severity": 1-5 (5 = danger or blocks wheelchair / pedestrian access),
  "accessibility_blocker": true/false (does it block a ramp, sidewalk or crossing?),
  "confidence": 0.0-1.0 (how sure you are about the category),
  "title_el": short Greek title, max 80 chars,
  "summary_el": one concise Greek operational sentence describing what is visible,
  "draft_reply_el": a short polite reply in the citizen's language saying the report was received and is awaiting operator review
}}
If the photo shows no municipal problem, use category "other" and confidence below 0.5."""

_KEYWORDS = {
    "pothole": ["λακκούβ", "λακουβ", "pothole", "λάκκο", "τρυπα", "ασφαλτ", "road hole"],
    "streetlight": ["φως", "φανοστάτ", "φωτισμ", "λάμπα", "λαμπα", "καμμεν", "streetlight", "street light", "lamp", "dark street"],
    "garbage": ["σκουπίδ", "σκουπιδ", "κάδο", "καδο", "απορριμ", "garbage", "trash", "bin", "rubbish", "waste"],
    "bulky_waste": ["ογκωδ", "στρωμ", "καναπ", "επιπλ", "bulky", "mattress", "sofa"],
    "tree": ["δέντρ", "δεντρ", "κλαδ", "tree", "branch", "fallen tree"],
    "graffiti": ["γκράφιτι", "γκραφιτι", "graffiti", "tagging", "spray paint"],
    "water_leak": ["νερό", "νερο", "διαρροή", "διαρροη", "αγωγ", "leak", "water", "pipe", "flood"],
    "abandoned_vehicle": ["εγκαταλελειμ", "παρατημεν", "αυτοκινητ", "abandoned", "wreck"],
    "noise": ["θορυβ", "ηχορυπαν", "noise", "loud"],
    "sidewalk": ["ράμπα", "ραμπα", "πεζοδρόμ", "πεζοδρομ", "πλακ", "ramp", "sidewalk", "pavement", "εμπόδιο", "εμποδιο", "blocked", "wheelchair", "stroller", "αμαξιδ"],
}

_TITLES_EL = {
    "pothole": "Λακκούβα στο οδόστρωμα",
    "streetlight": "Βλάβη δημοτικού φωτισμού",
    "garbage": "Πρόβλημα καθαριότητας / κάδου",
    "bulky_waste": "Εναπόθεση ογκωδών αντικειμένων",
    "tree": "Πρόβλημα δέντρου / κλαδιών",
    "graffiti": "Αναφορά γκράφιτι σε δημόσιο χώρο",
    "water_leak": "Διαρροή νερού σε δημόσιο χώρο",
    "abandoned_vehicle": "Εγκαταλελειμμένο όχημα",
    "noise": "Αναφορά ηχορύπανσης",
    "sidewalk": "Εμπόδιο σε ράμπα / πεζοδρόμιο",
    "other": "Αναφορά προβλήματος",
}


def _parse(text: str, original_note: str = "") -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0) if m else text)
    cat = data.get("category", "other")
    data["category"] = cat if cat in CATEGORIES else "other"
    data["severity"] = int(min(5, max(1, int(data.get("severity", 3)))))
    data["confidence"] = float(min(1.0, max(0.0, float(data.get("confidence", 0.5)))))
    data["accessibility_blocker"] = bool(data.get("accessibility_blocker", False))
    data.setdefault("title_el", _TITLES_EL.get(data["category"], "Αναφορά προβλήματος"))
    data.setdefault("summary_el", "")
    data.setdefault("draft_reply_el", "Ευχαριστούμε, η αναφορά σας καταχωρήθηκε προς έλεγχο από χειριστή.")
    data["detected_language"] = language.detect_language(original_note)
    data["interpretation"] = language.interpret_report(original_note, data)
    return data


def _mock(note: str) -> dict:
    lang = language.detect_language(note)
    # Pass 1: exact substring match across Greek, Greeklish, and English keywords.
    cat = next((c for c, kws in _KEYWORDS.items() if language.exact_matches_any(note, kws)), None)
    # Pass 2: typo-tolerant fuzzy fallback only when no exact match hit.
    if cat is None:
        cat = next((c for c, kws in _KEYWORDS.items() if language.fuzzy_matches_any(note, kws)), "sidewalk")
    blocker = cat == "sidewalk" or language.fuzzy_matches_any(note, ["ράμπα", "ραμπα", "ramp", "wheelchair", "αμαξιδ", "εμπόδιο", "blocked"])
    is_broken = cat == "sidewalk" and language.fuzzy_matches_any(
        note, ["σπασμ", "ραγισ", "φθορ", "κατεστρ", "broken", "crack", "damaged", "spasmen"]
    )
    if is_broken:
        title_el = "Φθαρμένο / σπασμένο πεζοδρόμιο"
        summary_el = "(mock · AI-GENERATED) Η αναφορά αφορά σπασμένες ή φθαρμένες πλάκες πεζοδρομίου."
    else:
        title_el = _TITLES_EL.get(cat, "Αναφορά προβλήματος")
        summary_el = (
            "(mock · AI-GENERATED) Η αναφορά υποδεικνύει εμπόδιο προσβασιμότητας στο πεζοδρόμιο."
            if blocker
            else f"(mock · AI-GENERATED) Προτεινόμενη κατηγορία: {title_el}."
        )
    draft_reply = (
        "Thank you for your report. It has been logged and is awaiting municipal operator review."
        if lang == "en"
        else "Ευχαριστούμε για την αναφορά. Καταχωρήθηκε και αναμένει έλεγχο από υπάλληλο του Δήμου."
    )
    out = {
        "category": cat,
        "severity": 4 if blocker else 3,
        "accessibility_blocker": blocker,
        "confidence": 0.6,  # deliberately below threshold: shows the operator check
        "title_el": title_el,
        "summary_el": summary_el,
        "draft_reply_el": draft_reply,
        "provider": "mock",
        "detected_language": lang,
    }
    out["interpretation"] = language.interpret_report(note, out)
    return out


def classify(jpeg: bytes, note: str = "") -> dict:
    provider = config.VISION_PROVIDER
    b64 = base64.b64encode(jpeg).decode()
    # Sanitise prompt input to avoid breaking framing; original note stays preserved verbatim in interpretation.
    safe_note = re.sub(r"\s+", " ", (note or "").strip())[:500]
    user_text = f"Citizen note (untrusted user input): {safe_note or '(none)'}"
    try:
        if provider == "anthropic" and config.ANTHROPIC_API_KEY:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
                json={"model": config.ANTHROPIC_MODEL, "max_tokens": 600, "system": PROMPT,
                      "messages": [{"role": "user", "content": [
                          {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                          {"type": "text", "text": user_text}]}]},
                timeout=40,
            )
            r.raise_for_status()
            out = _parse("".join(c.get("text", "") for c in r.json()["content"]), original_note=note)
            out["provider"] = "anthropic"
            return out
        if provider == "openai":
            r = httpx.post(
                f"{config.OPENAI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                json={"model": config.OPENAI_MODEL, "temperature": 0, "messages": [
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]},
                timeout=60,
            )
            r.raise_for_status()
            out = _parse(r.json()["choices"][0]["message"]["content"], original_note=note)
            out["provider"] = "openai"
            return out
    except Exception as e:  # never break the demo: fall back and say so
        out = _mock(note)
        out["provider"] = f"mock (fallback: {type(e).__name__})"
        return out
    return _mock(note)
