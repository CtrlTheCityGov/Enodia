"""B8: Stoa AI for the map (SPEC F6, contract `POST /stoa_ask`).

A plain rule-based router (not AI) picks one of three answerers:
  1. on-duty pharmacy/hospital questions -> the on-duty provider (B4), nearest to `center` first;
  2. works questions (a street that `stoa_ask.retrieve()` matches) -> `stoa_ask.ask()`, keeping its `[ΑΔΑ …]`;
  3. anything else -> the City answer of `/api/ask`, its sources as Markdown links.
Every answer is `{answer_md, citations:[{label, lon, lat, kind}]}`; every citation label occurs in `answer_md`.
No source -> the refusal text; a place is never invented.
"""
from __future__ import annotations

import math
from typing import Any

from . import language, stoa_ask
from .geo import haversine_km

# Same wording as the Stoa refusal (CLAUDE.md "A source on every answer"; app/stoa_ask.py REFUSAL_TEXT). Sure.
REFUSAL_MD = stoa_ask.REFUSAL_TEXT
REFUSAL_MD_EN = "No verified municipal records were found for this query."

# How many on-duty places to list, nearest first. Implementer's choice to keep the panel short (owner may change).
MAX_ONDUTY = 3

# Question words that send a question to the on-duty provider (Greek + Greeklish/English mapped via language.py).
PHARMACY_STEMS = ("φαρμακ", "pharmac")
HOSPITAL_STEMS = ("νοσοκομ", "hospit")
ONDUTY_STEMS = ("εφημερ", "onduty", "duty")  # «εφημερεύει», «εφημερία», "on duty"

# B4 names the kinds in Greek (SPEC `GET /health`: kind φαρμακείο/νοσοκομείο); the contract's citation kind is English.
KIND_EN = {"φαρμακείο": "pharmacy", "νοσοκομείο": "hospital", "pharmacy": "pharmacy", "hospital": "hospital"}

# Data sources that are not live: their answers carry a label (CLAUDE.md "Mock data is labelled").
NOT_LIVE_SOURCES = {"SEED", "mock"}


# ------------------------------------------------------------------ seams (patched in tests)
def onduty_provider() -> list[dict]:
    """On-duty pharmacies/hospitals as flat dicts `{kind, name, address, phone, hours, specialties, on_duty, lon, lat}`.

    Reads `app.onduty_src.get_onduty()` (B4) when it exists; returns [] until B4 is merged or if it fails.
    """
    try:
        from . import onduty_src  # type: ignore[attr-defined]  # B4, not merged yet
        fc = onduty_src.get_onduty()
    except Exception:
        return []
    items = []
    for f in fc.get("features") or []:
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        items.append({**(f.get("properties") or {}), "lon": coords[0], "lat": coords[1]})
    return items


def city_ask(question: str, center: list[float] | None = None) -> dict:
    """The City answer of `POST /api/ask`: `{answer, sources, source_kind, service, cool_places}`.

    `center` is not forwarded: the map centre stays on our server (no location sent to the sandbox).
    """
    from .main import AskIn, ask  # imported here: app.main includes this module's router at import time

    return ask(AskIn(text=question))


# ------------------------------------------------------------------ helpers
def _has_stem(qn: str, stems: tuple[str, ...]) -> bool:
    return any(tok.startswith(stem) for tok in qn.split() for stem in stems)


def _md_text(text: Any) -> str:
    """Plain text for the answer: brackets would start a Markdown link (ui/stoa.js renders links only)."""
    return " ".join(str(text or "").replace("[", "(").replace("]", ")").split())


def line_midpoint(coords: list[list[float]]) -> tuple[float, float] | None:
    """The point halfway along a [[lon,lat],...] line (equirectangular, fine at city scale), as (lon, lat)."""
    pts = [p for p in coords or [] if isinstance(p, (list, tuple)) and len(p) >= 2]
    if not pts:
        return None
    if len(pts) == 1:
        return float(pts[0][0]), float(pts[0][1])
    kx = math.cos(math.radians(pts[0][1]))  # shrink longitude to the same scale as latitude
    seg = [math.hypot((b[0] - a[0]) * kx, b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    half = sum(seg) / 2
    for (a, b), length in zip(zip(pts, pts[1:]), seg):
        if half <= length and length > 0:
            t = half / length
            return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
        half -= length
    return float(pts[-1][0]), float(pts[-1][1])


def _refusal(lang: str = "el") -> dict:
    return {"answer_md": REFUSAL_MD_EN if lang == "en" else REFUSAL_MD, "citations": [], "language": lang}


# ------------------------------------------------------------------ answerers
def answer_onduty(qn: str, center: list[float], lang: str = "el") -> dict:
    """Nearest on-duty pharmacies/hospitals to `center`. Only rows with `on_duty: true` (null = unknown, not shown)."""
    want = set()
    if _has_stem(qn, PHARMACY_STEMS):
        want.add("pharmacy")
    if _has_stem(qn, HOSPITAL_STEMS):
        want.add("hospital")
    if not want:
        want = {"pharmacy", "hospital"}

    lon0, lat0 = center
    rows = []
    for it in onduty_provider():
        kind = KIND_EN.get(it.get("kind"))
        lon, lat = it.get("lon"), it.get("lat")
        if kind not in want or it.get("on_duty") is not True or not it.get("name"):
            continue
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            continue
        rows.append((haversine_km(lat0, lon0, lat, lon), kind, it))
    if not rows:
        return _refusal(lang)
    rows.sort(key=lambda r: r[0])

    is_en = lang == "en"
    lines = ["On-duty nearby:" if is_en else "Εφημερεύουν κοντά σας:"]
    citations = []
    for dist_km, kind, it in rows[:MAX_ONDUTY]:
        label = _md_text(it["name"])
        parts = [label]
        if it.get("address"):
            parts.append(_md_text(it["address"]))
        if it.get("phone"):
            parts.append((f"tel. {_md_text(it['phone'])}") if is_en else f"τηλ. {_md_text(it['phone'])}")
        if it.get("hours"):
            parts.append((f"hours {_md_text(it['hours'])}") if is_en else f"ώρες {_md_text(it['hours'])}")
        parts.append(f"~{round(dist_km * 1000)} m")
        if it.get("source"):
            parts.append((f"source: {_md_text(it['source'])}") if is_en else f"πηγή: {_md_text(it['source'])}")
        lines.append("- " + ", ".join(parts))
        citations.append({"label": label, "lon": float(it["lon"]), "lat": float(it["lat"]), "kind": kind})
    return {"answer_md": "\n".join(lines), "citations": citations, "language": lang}


def answer_works(question: str) -> dict | None:
    """`stoa_ask.ask()` with a `work` citation per matched works line at its midpoint; None when nothing matches."""
    res = stoa_ask.ask(question)
    if not res["cards"]:
        return None
    answer_md = res["answer"]
    citations = []
    missing = []
    for card in res["cards"]:
        street = _md_text(stoa_ask._field_val(card, "street"))
        mid = line_midpoint((card.get("geometry") or {}).get("coordinates") or [])
        if not street or mid is None or any(c["label"] == street for c in citations):
            continue
        citations.append({"label": street, "lon": round(mid[0], 6), "lat": round(mid[1], 6), "kind": "work"})
        if street not in answer_md:  # a rephrased answer may have dropped the street name
            missing.append(street)
    if missing:
        answer_md += "\n\nΣτον χάρτη: " + ", ".join(missing)
    if res.get("data_source") in NOT_LIVE_SOURCES:
        answer_md += f"\n\nΔεδομένα: {res['data_source']} (δοκιμαστικά, στιγμιότυπο)"
    return {"answer_md": answer_md, "citations": citations}


def answer_city(question: str, center: list[float]) -> dict:
    """The City answer with its sources as Markdown links; citations only for results with coordinates."""
    try:
        res = city_ask(question, center) or {}
    except Exception:
        return _refusal()
    links = [s for s in res.get("sources") or [] if (s or {}).get("url")]
    if not links:
        return _refusal()
    lines = [str(res.get("answer") or "").strip(), "", "Πηγές:"]
    for s in links:
        lines.append(f"- [{_md_text(s.get('title') or s['url'])}]({s['url']})")
    citations = []
    places = []
    for p in res.get("cool_places") or []:
        lat, lon = p.get("lat"), p.get("lng", p.get("lon"))
        if p.get("name") and isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            label = _md_text(p["name"])
            places.append(f"- {label}")
            citations.append({"label": label, "lon": float(lon), "lat": float(lat), "kind": "place"})
    if places:
        lines += ["", "Δροσερά μέρη κοντά:", *places]
    if res.get("source_kind") == "mock":
        lines += ["", "Δεδομένα: mock (δοκιμαστικά)"]
    return {"answer_md": "\n".join(lines).strip(), "citations": citations}


def answer(question: str, center: list[float], history: list | None = None) -> dict:
    """Route one question (Greek, Greeklish, typos, or English) to its verified answerer."""
    question = (question or "").strip()
    if not question:
        return _refusal("el")
    lang = language.detect_language(question)
    qn = stoa_ask.normalize(question)
    q_expanded = stoa_ask.normalize(language.greeklish_to_greek(question))
    combined_qn = f"{qn} {q_expanded}".strip()
    if _has_stem(combined_qn, PHARMACY_STEMS + HOSPITAL_STEMS + ONDUTY_STEMS):
        return answer_onduty(combined_qn, center, lang=lang)
    works_answer = answer_works(question)
    if works_answer is None and q_expanded and q_expanded != qn:
        works_answer = answer_works(q_expanded)
    if works_answer is not None:
        works_answer["language"] = lang
        return works_answer
    city = answer_city(question, center)
    city.setdefault("language", lang)
    return city
