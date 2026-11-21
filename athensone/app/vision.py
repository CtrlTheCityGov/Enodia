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

from . import config
from .sandbox import CATEGORIES

PROMPT = f"""You triage street-problem reports for the Municipality of Athens.
Look at the photo (faces are already blurred) and the citizen's note.
Answer with ONE JSON object, no other text:
{{
  "category": one of {CATEGORIES},
  "severity": 1-5 (5 = danger or blocks wheelchair / pedestrian access),
  "accessibility_blocker": true/false (does it block a ramp, sidewalk or crossing?),
  "confidence": 0.0-1.0 (how sure you are about the category),
  "title_el": short Greek title, max 80 chars,
  "summary_el": one Greek sentence describing what is visible,
  "draft_reply_el": a short polite Greek reply to the citizen saying the report was received and what happens next
}}
If the photo shows no municipal problem, use category "other" and confidence below 0.5."""

_KEYWORDS = {
    "pothole": ["λακκούβ", "pothole", "λάκκο"],
    "streetlight": ["φως", "φανοστάτ", "λάμπα", "streetlight", "light"],
    "garbage": ["σκουπίδ", "κάδο", "garbage", "trash", "bin"],
    "tree": ["δέντρ", "κλαδ", "tree"],
    "graffiti": ["γκράφιτι", "graffiti"],
    "water_leak": ["νερό", "διαρροή", "leak"],
    "abandoned_vehicle": ["εγκαταλελειμ", "abandoned"],
    "sidewalk": ["ράμπα", "πεζοδρόμ", "ramp", "sidewalk", "εμπόδιο"],
}


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0) if m else text)
    cat = data.get("category", "other")
    data["category"] = cat if cat in CATEGORIES else "other"
    data["severity"] = int(min(5, max(1, int(data.get("severity", 3)))))
    data["confidence"] = float(min(1.0, max(0.0, float(data.get("confidence", 0.5)))))
    data["accessibility_blocker"] = bool(data.get("accessibility_blocker", False))
    data.setdefault("title_el", "Αναφορά προβλήματος")
    data.setdefault("summary_el", "")
    data.setdefault("draft_reply_el", "Ευχαριστούμε, η αναφορά σας καταχωρήθηκε.")
    return data


def _mock(note: str) -> dict:
    note_l = (note or "").lower()
    cat = next((c for c, kws in _KEYWORDS.items() if any(k in note_l for k in kws)), "sidewalk")
    blocker = cat == "sidewalk"
    if cat == "sidewalk" and any(k in note_l for k in ("σπασμ", "ραγισ", "φθορ", "κατεστρ", "broken", "crack")):
        return {"category": cat, "severity": 4, "accessibility_blocker": True, "confidence": 0.6,
                "title_el": "Φθαρμένο / σπασμένο πεζοδρόμιο",
                "summary_el": "(mock) Η φωτογραφία δείχνει σπασμένες πλάκες στο πεζοδρόμιο.",
                "draft_reply_el": "Ευχαριστούμε για την αναφορά. Ελέγχουμε το σημείο και θα σας ενημερώσουμε.",
                "provider": "mock"}
    return {
        "category": cat,
        "severity": 4 if blocker else 3,
        "accessibility_blocker": blocker,
        "confidence": 0.6,  # deliberately below threshold: shows the operator check
        "title_el": "Εμπόδιο σε ράμπα πεζοδρομίου" if blocker else "Αναφορά προβλήματος",
        "summary_el": "(mock) Η φωτογραφία δείχνει εμπόδιο στη ράμπα του πεζοδρομίου.",
        "draft_reply_el": ("Ευχαριστούμε για την αναφορά. Το συνεργείο ενημερώθηκε και θα "
                           "σας ενημερώσουμε μόλις αποκατασταθεί."),
        "provider": "mock",
    }


def classify(jpeg: bytes, note: str = "") -> dict:
    provider = config.VISION_PROVIDER
    b64 = base64.b64encode(jpeg).decode()
    user_text = f"Citizen note: {note or '(none)'}"
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
            out = _parse("".join(c.get("text", "") for c in r.json()["content"]))
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
            out = _parse(r.json()["choices"][0]["message"]["content"])
            out["provider"] = "openai"
            return out
    except Exception as e:  # never break the demo: fall back and say so
        out = _mock(note)
        out["provider"] = f"mock (fallback: {type(e).__name__})"
        return out
    return _mock(note)
