"""Public notices & civic events router: GET /api/announcements.

Combines protest/strike notices from apergia.gr (live fetch with 10-min cache + safe offline fallback)
with Municipality of Athens civic/cultural events.
"""
from __future__ import annotations

import html
import re
import time

import httpx
from fastapi import APIRouter

from .. import config

router = APIRouter()

_CACHE: dict = {"ts": 0.0, "protests": None, "source": "snapshot"}
_TTL_S = 600.0

_FALLBACK_PROTESTS = [
    {
        "id": "apg-1",
        "kind": "protest",
        "title": "Συγκέντρωση διαμαρτυρίας & πορεία στο κέντρο (Σύνταγμα)",
        "date": "2026-11-22",
        "time": "12:00",
        "location": "Πλατεία Συντάγματος → Πανεπιστημίου",
        "lat": 37.9755,
        "lng": 23.7348,
        "summary": "Ενδέχονται κυκλοφοριακές ρυθμίσεις στις οδούς Σταδίου, Πανεπιστημίου και Βασ. Αμαλίας.",
        "url": "https://apergia.gr/",
        "source_label": "apergia.gr",
    },
    {
        "id": "apg-2",
        "kind": "protest",
        "title": "Στάση εργασίας & ενημερωτική παράσταση στα Προπύλαια",
        "date": "2026-11-23",
        "time": "11:30",
        "location": "Προπύλαια (Πανεπιστημίου)",
        "lat": 37.9806,
        "lng": 23.7336,
        "summary": "Προσωρινή διακοπή κυκλοφορίας στην οδό Πανεπιστημίου κατά τη διέλευση της πορείας.",
        "url": "https://apergia.gr/",
        "source_label": "apergia.gr",
    },
]

_MUNICIPAL_EVENTS = [
    {
        "id": "ath-ev-1",
        "kind": "event",
        "title": "Athens Digital & Green Week — Τεχνόπολις Δήμου Αθηναίων",
        "date": "2026-11-22",
        "time": "10:00 - 20:00",
        "location": "Τεχνόπολις, Πειραιώς 100 (Γκάζι)",
        "lat": 37.9781,
        "lng": 23.7140,
        "summary": "Ανοιχτές δράσεις, εργαστήρια αστικής βιωσιμότητας και εκθέσεις για πολίτες.",
        "url": "https://www.cityofathens.gr/",
        "source_label": "Δήμος Αθηναίων",
    },
    {
        "id": "ath-ev-2",
        "kind": "event",
        "title": "Κυριακάτικος Περίπατος Πολιτισμού & Ξενάγηση στον Εθνικό Κήπο",
        "date": "2026-11-22",
        "time": "11:00",
        "location": "Εθνικός Κήπος (Είσοδος Βασ. Αμαλίας)",
        "lat": 37.9729,
        "lng": 23.7372,
        "summary": "Δωρεάν περιβαλλοντική και ιστορική ξενάγηση από τις υπηρεσίες πρασίνου του Δήμου.",
        "url": "https://www.cityofathens.gr/",
        "source_label": "Δήμος Αθηναίων",
    },
    {
        "id": "ath-ev-3",
        "kind": "event",
        "title": "Κοινοτική Συνάντηση Προσβασιμότητας & ΚΑΠΗ στο Σεράφειο",
        "date": "2026-11-24",
        "time": "17:30",
        "location": "Σεράφειο Δήμου Αθηναίων (Εχελιδών & Πειραιώς)",
        "lat": 37.9746,
        "lng": 23.7107,
        "summary": "Διαβούλευση με δημότες για βελτιώσεις ραμπών, πεζοδρομίων και φωτισμού στις γειτονιές.",
        "url": "https://www.cityofathens.gr/",
        "source_label": "Δήμος Αθηναίων",
    },
    {
        "id": "ath-ev-4",
        "kind": "event",
        "title": "Βραδιά Μουσικής της Φιλαρμονικής Δήμου Αθηναίων",
        "date": "2026-11-25",
        "time": "19:00",
        "location": "Πλατεία Κοτζιά (Δημαρχείο Αθηνών)",
        "lat": 37.9806,
        "lng": 23.7276,
        "summary": "Ανοιχτή συναυλία στην Πλατεία Κοτζιά με ελεύθερη είσοδο.",
        "url": "https://www.cityofathens.gr/",
        "source_label": "Δήμος Αθηναίων",
    },
]

_TAG_RE = re.compile(r"<[^>]+>")
_ITEM_RE = re.compile(r"<(?:h2|h3|a)[^>]*class=\"[^\"]*(?:title|post|event|strike)[^\"]*\"[^>]*>(.*?)</(?:h2|h3|a)>", re.I | re.S)


def _fetch_apergia() -> tuple[list[dict], str]:
    if config.MOCK:
        return list(_FALLBACK_PROTESTS), "snapshot"
    now = time.time()
    if _CACHE["protests"] is not None and now - _CACHE["ts"] < _TTL_S:
        return list(_CACHE["protests"]), str(_CACHE["source"])
    try:
        resp = httpx.get("https://apergia.gr/", headers={"User-Agent": "EnodiaAthens/1.0"}, timeout=3.5, follow_redirects=True)
        resp.raise_for_status()
        matches = _ITEM_RE.findall(resp.text)
        parsed = []
        for idx, raw in enumerate(matches[:6]):
            title = html.unescape(_TAG_RE.sub("", raw)).strip()
            title = re.sub(r"\s+", " ", title)
            if len(title) < 8:
                continue
            parsed.append({
                "id": f"apg-live-{idx + 1}",
                "kind": "protest",
                "title": title[:160],
                "date": "Τρέχουσα ενημέρωση",
                "time": "",
                "location": "Κέντρο Αθήνας",
                "lat": 37.9755,
                "lng": 23.7348,
                "summary": "Ανακοίνωση από apergia.gr — ελέγξτε πιθανές κυκλοφοριακές ρυθμίσεις.",
                "url": "https://apergia.gr/",
                "source_label": "apergia.gr (Live)",
            })
        if parsed:
            _CACHE.update({"ts": now, "protests": parsed, "source": "live"})
            return parsed, "live"
    except Exception:
        pass
    _CACHE.update({"ts": now, "protests": _FALLBACK_PROTESTS, "source": "snapshot"})
    return list(_FALLBACK_PROTESTS), "snapshot"


@router.get("/api/announcements")
def get_announcements() -> dict:
    """Return protests/strikes (apergia.gr) and Municipality of Athens civic events."""
    protests, source = _fetch_apergia()
    items = protests + _MUNICIPAL_EVENTS
    return {
        "source": source,
        "items": items,
        "counts": {
            "protests": len(protests),
            "events": len(_MUNICIPAL_EVENTS),
        },
    }
