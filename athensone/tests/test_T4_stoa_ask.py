"""Tests for task T4: Ask Stoa, cited answers (offline with TestClient)."""
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

from app.main import app  # noqa: E402

c = TestClient(app)

REFUSAL_TEXT = "Δεν βρήκα τεκμηριωμένα στοιχεία για αυτό."
_ABBREV = ("άρθ", "σελ", "αρ", "ν")


def _sentences(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        start = 0
        for i, ch in enumerate(line):
            if ch != ".":
                continue
            if i > 0 and line[i - 1].isdigit() and i + 1 < len(line) and line[i + 1].isdigit():
                continue
            if i + 1 < len(line) and not line[i + 1].isspace():
                continue
            word = re.findall(r"([A-Za-zΑ-Ωα-ωάέήίόύώϊϋΐΰ]+)$", line[:i])
            if word and word[0].lower() in _ABBREV:
                continue
            seg = line[start : i + 1].strip()
            if seg:
                out.append(seg)
            start = i + 1
        tail = line[start:].strip()
        if tail:
            out.append(tail)
    return out


# Checks that asking about sample street "Δείγμα Οδός Α" cites SEED-ΑΔΑ-003 and guarantee end 15/12/2026.
def test_ask_sample_street_cites_ada(monkeypatch):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    r = c.post("/api/stoa/ask", json={"q": "Δείγμα Οδός Α"})
    assert r.status_code == 200
    data = r.json()
    assert "SEED-ΑΔΑ-003" in data["answer"]
    assert "15/12/2026" in data["answer"]


# Checks that unaccented and uppercase queries retrieve the same cards as the accented query.
def test_ask_accent_insensitive(monkeypatch):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    r1 = c.post("/api/stoa/ask", json={"q": "Δείγμα Οδός Α"})
    r2 = c.post("/api/stoa/ask", json={"q": "δειγμα οδος α"})
    r3 = c.post("/api/stoa/ask", json={"q": "ΔΕΙΓΜΑ ΟΔΟΣ Α"})
    assert r1.status_code == 200 and r2.status_code == 200 and r3.status_code == 200
    d1, d2, d3 = r1.json(), r2.json(), r3.json()
    assert len(d1["cards"]) >= 1
    assert [x["id"] for x in d2["cards"]] == [x["id"] for x in d1["cards"]]
    assert [x["id"] for x in d3["cards"]] == [x["id"] for x in d1["cards"]]


# Checks that asking about a street with no works records returns the refusal text and no ΑΔΑ.
def test_ask_unknown_street_refuses():
    r = c.post("/api/stoa/ask", json={"q": "Οδός Ανύπαρκτη 12"})
    assert r.status_code == 200
    data = r.json()
    assert REFUSAL_TEXT in data["answer"]
    assert "ΑΔΑ" not in data["answer"]
    assert data["cards"] == []


# Checks that every sentence in any matched answer ends with an [ΑΔΑ …] citation.
def test_every_sentence_cited(monkeypatch):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    for query in ("Δείγμα Οδός Α", "Δείγμα Οδός Β"):
        r = c.post("/api/stoa/ask", json={"q": query})
        assert r.status_code == 200
        answer = r.json()["answer"]
        sents = _sentences(answer)
        assert sents
        for s in sents:
            assert re.search(r"\[ΑΔΑ\s+[^\]]+\]\.?$", s), f"Uncited sentence: {s!r}"


# Checks that a fake rephraser introducing a number absent from the cards falls back to the template answer.
def test_rephrase_with_bad_number_falls_back(monkeypatch):
    from app import stoa_ask

    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    r1 = c.post("/api/stoa/ask", json={"q": "Δείγμα Οδός Α"})
    assert r1.status_code == 200
    template_answer = r1.json()["answer"]

    def fake_rephrase(text: str, cards: list[dict]) -> str:
        return f"{text}\nΕπιπλέον κόστος 987654 ευρώ [ΑΔΑ SEED-ΑΔΑ-001]."

    monkeypatch.setattr(stoa_ask, "rephrase", fake_rephrase)
    r2 = c.post("/api/stoa/ask", json={"q": "Δείγμα Οδός Α"})
    assert r2.status_code == 200
    assert r2.json()["answer"] == template_answer


# Checks that a works-type query matching more than three cards returns at most 3 cards.
def test_max_three_cards(monkeypatch, tmp_path):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    many_works = {
        "source": "SEED",
        "snapshot": "2026-11-21",
        "organisation": "Δήμος Αθηναίων (test)",
        "works": [
            {
                "id": f"W-MANY-{i:03d}",
                "works_type": "asphalt",
                "resolution": "street",
                "title": {"value": f"Ασφαλτόστρωση {i}", "label": "CITED", "source": {"ada": f"TEST-ΑΔΑ-{i:03d}", "page": 1}},
                "street": {"value": f"Οδός Δοκιμής {i}", "label": "CITED", "source": {"ada": f"TEST-ΑΔΑ-{i:03d}", "page": 1}},
                "contractor": {"value": f"Ανάδοχος {i}", "label": "CITED", "source": {"ada": f"TEST-ΑΔΑ-{i:03d}", "page": 1}},
                "amount_paid_eur": {"value": 10000.0 + i, "label": "CITED", "source": {"ada": f"TEST-ΑΔΑ-{i:03d}", "page": 1}},
                "completion_date": {"value": "2025-10-01", "label": "CITED", "source": {"ada": f"TEST-ΑΔΑ-{i:03d}", "page": 1}},
                "guarantee_months": {"value": 15, "label": "CITED", "source": {"ada": f"TEST-ΑΔΑ-{i:03d}", "page": 1}},
                "final_acceptance": False,
                "geometry": {"type": "LineString", "coordinates": [[23.74, 37.96], [23.741, 37.961]]},
            }
            for i in range(1, 6)
        ],
    }
    works_file = tmp_path / "works_many.json"
    works_file.write_text(json.dumps(many_works, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("STOA_WORKS_PATH", str(works_file))

    r = c.post("/api/stoa/ask", json={"q": "ασφαλτόστρωση"})
    assert r.status_code == 200
    data = r.json()
    assert 1 <= len(data["cards"]) <= 3
