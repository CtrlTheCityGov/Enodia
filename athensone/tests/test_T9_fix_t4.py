"""Tests for task T9: Ask Stoa verify and retrieval fixes (offline with TestClient)."""
import json
import os
import re

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

from fastapi.testclient import TestClient  # noqa: E402

from app import stoa_ask  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)

REFUSAL_TEXT = "Δεν βρήκα τεκμηριωμένα στοιχεία για αυτό."


# Checks that a rephraser swapping day and month in 15/12/2026 to 12/15/2026 falls back to the template.
def test_swapped_date_falls_back(monkeypatch):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    r1 = c.post("/api/stoa/ask", json={"q": "Δείγμα Οδός Α"})
    assert r1.status_code == 200
    template_answer = r1.json()["answer"]
    assert "15/12/2026" in template_answer

    def fake_rephrase(text: str, cards: list[dict]) -> str:
        return text.replace("15/12/2026", "12/15/2026")

    monkeypatch.setattr(stoa_ask, "rephrase", fake_rephrase)
    r2 = c.post("/api/stoa/ask", json={"q": "Δείγμα Οδός Α"})
    assert r2.status_code == 200
    data = r2.json()
    assert data["answer"] == template_answer
    assert data["rephrased"] is False


# Checks that a rephraser changing 48.200 € to 2.026 € (whose pieces exist in the card) falls back to the template.
def test_changed_amount_falls_back(monkeypatch):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    r1 = c.post("/api/stoa/ask", json={"q": "Δείγμα Οδός Α"})
    assert r1.status_code == 200
    template_answer = r1.json()["answer"]
    assert "48.200" in template_answer

    def fake_rephrase(text: str, cards: list[dict]) -> str:
        return text.replace("48.200", "2.026")

    monkeypatch.setattr(stoa_ask, "rephrase", fake_rephrase)
    r2 = c.post("/api/stoa/ask", json={"q": "Δείγμα Οδός Α"})
    assert r2.status_code == 200
    data = r2.json()
    assert data["answer"] == template_answer
    assert data["rephrased"] is False


# Checks that a rephraser removing "πιθανώς εντός" wording falls back to the template.
def test_dropped_guarantee_wording_falls_back(monkeypatch):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    r1 = c.post("/api/stoa/ask", json={"q": "Δείγμα Οδός Α"})
    assert r1.status_code == 200
    template_answer = r1.json()["answer"]
    assert "Πιθανώς εντός" in template_answer

    def fake_rephrase(text: str, cards: list[dict]) -> str:
        return text.replace("Πιθανώς εντός", "Είναι εντός")

    monkeypatch.setattr(stoa_ask, "rephrase", fake_rephrase)
    r2 = c.post("/api/stoa/ask", json={"q": "Δείγμα Οδός Α"})
    assert r2.status_code == 200
    data = r2.json()
    assert data["answer"] == template_answer
    assert data["rephrased"] is False


# Checks that a contractor name containing "Α.Ε." is not split mid-sentence so every sentence ends with [ΑΔΑ …].
def test_abbreviation_not_split(monkeypatch, tmp_path):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    works_data = {
        "source": "SEED",
        "snapshot": "2026-11-21",
        "organisation": "Δήμος Αθηναίων (test)",
        "works": [
            {
                "id": "W-ABBR-001",
                "works_type": "sidewalk",
                "resolution": "street",
                "title": {"value": "Ανακατασκευή πεζοδρομίων", "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-001", "page": 1}},
                "street": {"value": "Οδός Δοκιμής Α", "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-001", "page": 1}},
                "contractor": {"value": "Τεχνική Α.Ε. Ελλάδος", "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-001", "page": 1}},
                "amount_paid_eur": {"value": 25000.0, "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-001", "page": 1}},
                "completion_date": {"value": "2025-10-01", "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-001", "page": 1}},
                "guarantee_months": {"value": 15, "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-001", "page": 1}},
                "final_acceptance": False,
                "geometry": {"type": "LineString", "coordinates": [[23.74, 37.96], [23.741, 37.961]]},
            }
        ],
    }
    works_file = tmp_path / "works_abbr.json"
    works_file.write_text(json.dumps(works_data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("STOA_WORKS_PATH", str(works_file))

    r = c.post("/api/stoa/ask", json={"q": "Οδός Δοκιμής Α"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["cards"]) == 1
    assert "Τεχνική Α.Ε. Ελλάδος" in data["answer"]
    sents = stoa_ask._sentences(data["answer"])
    assert sents
    for s in sents:
        assert re.search(r"\[ΑΔΑ\s+[^\]]+\]\.?$", s), f"Uncited sentence: {s!r}"
    assert stoa_ask.verify(data["answer"], data["cards"]) is True


# Checks that a query with an unknown street name and a known works type refuses instead of matching on type alone.
def test_unknown_street_with_known_type_refuses(monkeypatch):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    r = c.post("/api/stoa/ask", json={"q": "Οδός Ανύπαρκτη πεζοδρόμιο"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == REFUSAL_TEXT
    assert data["cards"] == []
    assert "ΑΔΑ" not in data["answer"]
