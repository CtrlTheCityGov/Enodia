"""B14 fix round: findings of the B14 review (non-finite bbox, category cap, untrusted POI fields)."""
from __future__ import annotations

import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402

c = TestClient(main.app)


# inf / nan in the bbox are rejected (was: 500 from haversine, or a NaN radius sent to the sandbox).
def test_pois_non_finite_bbox_422():
    for bbox in ("-inf,0,inf,1", "nan,nan,nan,nan"):
        assert c.get("/api/map/pois", params={"bbox": bbox}).status_code == 422


# The shared _bbox helper also guards /api/map/works.
def test_works_non_finite_bbox_422():
    assert c.get("/api/map/works", params={"bbox": "nan,nan,nan,nan"}).status_code == 422


# Each category costs one sandbox call: more than 5 is refused before any call.
def test_pois_more_than_five_categories_422(monkeypatch):
    calls = []
    monkeypatch.setattr(main.sb, "pois", lambda **kw: calls.append(kw) or {"items": []})
    r = c.get("/api/map/pois", params={"categories": "a,b,c,d,e,f"})
    assert r.status_code == 422
    assert calls == []


# Repeated categories count once and cost one call.
def test_pois_duplicate_categories_called_once(monkeypatch):
    calls = []
    monkeypatch.setattr(main.sb, "pois", lambda **kw: calls.append(kw["category"]) or {"items": []})
    assert c.get("/api/map/pois", params={"categories": "library,library"}).status_code == 200
    assert calls == ["library"]


# Untrusted POI fields: non-numeric coordinates are skipped, a non-numeric distance is recomputed (no 500).
def test_pois_bad_upstream_fields_skipped(monkeypatch):
    items = [
        {"id": "bad", "name": "x", "category": "library", "lat": "abc", "lng": 23.73},
        {"id": "ok", "name": "y", "category": "library", "lat": 37.9755, "lng": 23.7348, "distance_km": "near"},
    ]
    monkeypatch.setattr(main.sb, "pois", lambda **kw: {"items": items})
    r = c.get("/api/map/pois", params={"categories": "library"})
    assert r.status_code == 200
    feats = r.json()["features"]
    assert [f["id"] for f in feats] == ["ok"]
    assert isinstance(feats[0]["properties"]["distance_km"], float)
