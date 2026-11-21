"""Tests for B8: Stoa AI with citations + flyTo (POST /api/map/stoa_ask).

Expected backend interface (implementer builds to match):
  - app/routers/stoa_map.py: FastAPI APIRouter exposing `POST /api/map/stoa_ask`
    accepting JSON `{"question": str, "center": [lon, lat], "history": list}` and
    returning `{"answer_md": str, "citations": [{"label": str, "lon": float, "lat": float, "kind": str}]}`.
  - app/stoa_map.py:
    - `onduty_provider() -> list[dict]`: returns on-duty pharmacy/hospital items
      (`{kind, name, address, phone, hours, specialties, on_duty, lon, lat}`) from
      `app.onduty_src` when available, or `[]` until B4 is merged.
    - `city_ask(question: str, center: list[float] | None = None) -> dict`: calls
      the City `/api/ask` logic and returns `{answer, sources, source_kind, service, cool_places}`.
"""
from __future__ import annotations

import os
import re

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
SYNTAGMA = [23.7348, 37.9755]
REFUSAL_PREFIX = "Δεν βρήκα τεκμηριωμένα στοιχεία"


# Checks that a works query on «Δείγμα Οδός Α» returns answer_md with [ΑΔΑ …] and a work citation with numeric lon/lat.
def test_stoa_map_contract(monkeypatch):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    r = c.post(
        "/api/map/stoa_ask",
        json={"question": "Τι έργα έγιναν στη Δείγμα Οδός Α;", "center": SYNTAGMA, "history": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("answer_md"), str)
    assert re.search(r"\[ΑΔΑ\s+[^\]]+\]", body["answer_md"])
    citations = body.get("citations")
    assert isinstance(citations, list) and len(citations) >= 1
    work_cits = [cit for cit in citations if cit.get("kind") == "work"]
    assert len(work_cits) >= 1
    for cit in work_cits:
        assert isinstance(cit.get("label"), str) and cit["label"].strip()
        assert isinstance(cit.get("lon"), (int, float)) and not isinstance(cit["lon"], bool)
        assert isinstance(cit.get("lat"), (int, float)) and not isinstance(cit["lat"], bool)
        assert 23.60 <= cit["lon"] <= 23.90
        assert 37.85 <= cit["lat"] <= 38.15


# Checks that every citation label returned for an answered question appears in answer_md.
def test_citation_labels_in_answer(monkeypatch):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    for question in ("Δείγμα Οδός Α", "Δείγμα Οδός Β"):
        r = c.post(
            "/api/map/stoa_ask",
            json={"question": question, "center": SYNTAGMA, "history": []},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["citations"], f"Expected citations for {question!r}"
        for cit in body["citations"]:
            assert isinstance(cit.get("label"), str) and cit["label"]
            assert cit["label"] in body["answer_md"]


# Checks that an on-duty pharmacy query uses the provider and puts the pharmacy closest to center first with kind="pharmacy".
def test_pharmacy_question_uses_provider(monkeypatch):
    from app import stoa_map

    far_pharmacy = {
        "kind": "φαρμακείο",
        "name": "Φαρμακείο Βαρνάβα",
        "address": "Πλ. Βαρνάβα 5",
        "phone": "2107510000",
        "hours": "08:00-08:00",
        "specialties": [],
        "on_duty": True,
        "lon": 23.7437,
        "lat": 37.9667,
    }
    near_pharmacy = {
        "kind": "φαρμακείο",
        "name": "Φαρμακείο Συντάγματος",
        "address": "Καραγιώργη Σερβίας 4",
        "phone": "2103220000",
        "hours": "08:00-23:00",
        "specialties": [],
        "on_duty": True,
        "lon": 23.7340,
        "lat": 37.97638,
    }
    monkeypatch.setattr(stoa_map, "onduty_provider", lambda: [far_pharmacy, near_pharmacy])

    r = c.post(
        "/api/map/stoa_ask",
        json={"question": "Ποιο φαρμακείο εφημερεύει κοντά μου;", "center": SYNTAGMA, "history": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["citations"]) >= 1
    first = body["citations"][0]
    assert first["kind"] == "pharmacy"
    assert abs(first["lon"] - 23.7340) < 1e-4
    assert abs(first["lat"] - 37.97638) < 1e-4
    assert first["label"] in body["answer_md"]


# Checks that an on-duty pharmacy query refuses with empty citations when the provider returns nothing.
def test_pharmacy_no_provider_refuses(monkeypatch):
    from app import stoa_map

    monkeypatch.setattr(stoa_map, "onduty_provider", lambda: [])

    r = c.post(
        "/api/map/stoa_ask",
        json={"question": "Ποιο φαρμακείο εφημερεύει κοντά μου;", "center": SYNTAGMA, "history": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert REFUSAL_PREFIX in body["answer_md"]
    assert body["citations"] == []


# Checks that a general City question formats sandbox sources with their URLs inside answer_md.
def test_city_question_has_source_links(monkeypatch):
    from app import stoa_map

    monkeypatch.setattr(
        stoa_map,
        "city_ask",
        lambda question, center=None: {
            "answer": "Για βεβαίωση μόνιμης κατοικίας κάντε αίτηση στο ΚΕΠ.",
            "sources": [
                {"title": "Βεβαίωση μόνιμης κατοικίας", "url": "https://www.cityofathens.gr/residence-cert"},
                {"title": "ΚΕΠ Δήμου Αθηναίων", "url": "https://www.cityofathens.gr/kep"},
            ],
            "source_kind": "mock",
            "service": None,
            "cool_places": [],
        },
    )

    r = c.post(
        "/api/map/stoa_ask",
        json={"question": "Πώς βγάζω βεβαίωση μόνιμης κατοικίας;", "center": SYNTAGMA, "history": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert "https://www.cityofathens.gr/residence-cert" in body["answer_md"]
    assert "https://www.cityofathens.gr/kep" in body["answer_md"]


# Checks that a question with no matching works, on-duty items, or City sources refuses with no citations.
def test_unknown_refuses_no_invented_place(monkeypatch):
    from app import stoa_map

    monkeypatch.setattr(stoa_map, "onduty_provider", lambda: [])
    monkeypatch.setattr(
        stoa_map,
        "city_ask",
        lambda question, center=None: {
            "answer": "",
            "sources": [],
            "source_kind": "mock",
            "service": None,
            "cool_places": [],
        },
    )

    r = c.post(
        "/api/map/stoa_ask",
        json={"question": "Πού βρίσκεται η ανύπαρκτη πλατεία ΧΨΩ;", "center": SYNTAGMA, "history": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert REFUSAL_PREFIX in body["answer_md"]
    assert body["citations"] == []


# Checks that the existing POST /api/stoa/ask route still returns the exact same response keys.
def test_existing_stoa_route_unchanged():
    r = c.post("/api/stoa/ask", json={"q": "Δείγμα Οδός Α"})
    assert r.status_code == 200
    assert set(r.json().keys()) == {"q", "answer", "cards", "sources", "rephrased", "data_source", "snapshot"}
