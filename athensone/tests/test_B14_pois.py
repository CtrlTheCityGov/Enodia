"""Tests for B14: official POI layer, GET /api/map/pois (card B14 in docs/TASKS_B.md)."""
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
from app.sandbox import SandboxError  # noqa: E402

c = TestClient(main.app)

# ~200 m box around Σύνταγμα (the card: mock POIs are in Παγκράτι, > 1 km away).
SYNTAGMA_BBOX = "23.7338,37.9746,23.7358,37.9764"


# Default call on the mock sandbox returns all 3 mock POIs as official GeoJSON.
def test_pois_default_returns_feature_collection():
    r = c.get("/api/map/pois")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 3
    for f in body["features"]:
        assert f["properties"]["official"] is True
        assert f["properties"]["source"] == "mock"


# GeoJSON order: coordinates are [lng, lat].
def test_pois_feature_coordinates_are_lng_lat():
    feats = {f["id"]: f for f in c.get("/api/map/pois").json()["features"]}
    assert feats["poi-mock-1"]["geometry"]["coordinates"] == [23.7476, 37.9689]


# A single category filter keeps only that category.
def test_pois_single_category_filter():
    feats = c.get("/api/map/pois?categories=library").json()["features"]
    assert feats
    assert {f["properties"]["category"] for f in feats} == {"library"}


# A tiny bbox at Σύνταγμα gives a small radius, so the far mock POIs are excluded.
def test_pois_bbox_radius_excludes_far():
    r = c.get(f"/api/map/pois?bbox={SYNTAGMA_BBOX}")
    assert r.status_code == 200
    assert r.json()["features"] == []


# A huge bbox must never ask the sandbox for more than 5 km.
def test_pois_bbox_radius_capped_5km(monkeypatch):
    radii = []

    def spy(category=None, lat=None, lng=None, radius_km=2.0, size=20):
        radii.append(radius_km)
        return {"total": 0, "page": 1, "size": size, "items": []}

    monkeypatch.setattr(main.sb, "pois", spy)
    r = c.get("/api/map/pois?bbox=23.0,37.5,24.5,38.5")
    assert r.status_code == 200
    assert radii and all(x <= 5 for x in radii)


# Bad bbox: not 4 floats, or min > max.
def test_pois_bad_bbox_422():
    assert c.get("/api/map/pois?bbox=1,2,3").status_code == 422
    assert c.get("/api/map/pois?bbox=23.8,37.9,23.7,38.0").status_code == 422


# One failing category is skipped and listed; the others still answer.
def test_pois_one_category_error_listed(monkeypatch):
    real = main.sb.pois

    def flaky(category=None, **kw):
        if category == "library":
            raise SandboxError("down")
        return real(category=category, **kw)

    monkeypatch.setattr(main.sb, "pois", flaky)
    r = c.get("/api/map/pois")
    assert r.status_code == 200
    body = r.json()
    assert body["errors"] == ["library"]
    assert any(f["properties"]["category"] == "friendship_club" for f in body["features"])


# Every category failing means 503.
def test_pois_all_categories_error_503(monkeypatch):
    def boom(*a, **kw):
        raise SandboxError("down")

    monkeypatch.setattr(main.sb, "pois", boom)
    assert c.get("/api/map/pois").status_code == 503


# Same id twice and an item without lat give exactly one feature.
def test_pois_drops_missing_coordinates_and_duplicates(monkeypatch):
    item = {"id": "dup-1", "name": "X", "category": "library", "lat": 37.9755, "lng": 23.7348,
            "address": "a", "open_now": True, "distance_km": 0.1}
    items = [dict(item), dict(item), {"id": "nolat", "name": "Y", "category": "library", "lng": 23.7}]

    def fake(category=None, **kw):
        return {"total": 3, "page": 1, "size": 50, "items": [dict(i) for i in items]}

    monkeypatch.setattr(main.sb, "pois", fake)
    feats = c.get("/api/map/pois?categories=library").json()["features"]
    assert [f["id"] for f in feats] == ["dup-1"]
