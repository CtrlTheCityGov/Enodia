"""Tests for B12: Cross-module backend wiring (works_map + routing_map + map_reports)."""
import json
import math
import os
from pathlib import Path

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ckan, config, env, main, routing, works  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)

SEED_PATH = config.DATA_DIR / "works_seed.json"
SYNTAGMA = [23.7348, 37.9755]
MONASTIRAKI = [23.7257, 37.9761]
DIRECT_MID = [23.73025, 37.9758]


@pytest.fixture(autouse=True)
def _clean_state():
    c.post("/api/admin/reset")
    routing._cache.clear()
    works._cache.clear()
    env._cache.clear()
    main._weather.clear()
    ckan._mem.clear()
    yield
    c.post("/api/admin/reset")
    routing._cache.clear()
    works._cache.clear()
    env._cache.clear()
    main._weather.clear()
    ckan._mem.clear()


def _use_seed(monkeypatch) -> None:
    monkeypatch.setenv("STOA_WORKS_PATH", str(SEED_PATH))
    works._cache.clear()


def _min_dist_to_point_m(coords: list[list[float]], lon: float, lat: float) -> float:
    """Minimum distance in metres from a polyline [[lon, lat], ...] to a point."""
    k = 111_320.0
    kx = k * math.cos(math.radians(lat))
    px, py = lon * kx, lat * k
    best = float("inf")
    pts = [(x * kx, y * k) for x, y in coords]
    for (ax, ay), (bx, by) in zip(pts, pts[1:] or pts):
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def test_work_progress_map_report_increments_works_reports_count(monkeypatch):
    # Checks that a work_progress map report within 30 m of W-SEED-001 increments its reports_count in GET /api/map/works.
    _use_seed(monkeypatch)
    rep = c.post(
        "/api/map/reports",
        data={
            "category": "work_progress",
            "lon": 23.7420,
            "lat": 37.9660,
            "work_id": "W-SEED-001",
            "note": "πρόοδος έργου",
        },
    )
    assert rep.status_code == 200

    res = c.get("/api/map/works")
    assert res.status_code == 200
    by_id = {f["properties"]["id"]: f["properties"] for f in res.json()["features"]}
    assert by_id["W-SEED-001"]["reports_count"] == 1


def test_obstacle_map_report_not_double_counted_on_work(monkeypatch):
    # Checks that an obstacle map report near W-SEED-001 is counted once (not double-counted from sandbox + SQLite).
    _use_seed(monkeypatch)
    rep = c.post(
        "/api/map/reports",
        data={
            "category": "obstacle",
            "lon": 23.7420,
            "lat": 37.9660,
            "work_id": "W-SEED-001",
            "note": "εμπόδιο στο πεζοδρόμιο",
        },
    )
    assert rep.status_code == 200

    res = c.get("/api/map/works")
    assert res.status_code == 200
    by_id = {f["properties"]["id"]: f["properties"] for f in res.json()["features"]}
    assert by_id["W-SEED-001"]["reports_count"] == 1


def test_wheelchair_routing_avoids_map_report_obstacle():
    # Checks that wheelchair routing avoids an obstacle created via POST /api/map/reports and cites its MR-... id.
    rep = c.post(
        "/api/map/reports",
        data={
            "category": "obstacle",
            "lon": DIRECT_MID[0],
            "lat": DIRECT_MID[1],
            "note": "εμπόδιο στη ράμπα",
        },
    )
    assert rep.status_code == 200
    report_id = rep.json()["id"]
    assert report_id.startswith("MR-")

    res = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": "wheelchair"})
    assert res.status_code == 200
    data = res.json()
    coords = data["geometry"]["coordinates"]
    assert _min_dist_to_point_m(coords, DIRECT_MID[0], DIRECT_MID[1]) > 20.0
    assert any(r.get("layer") == "reports" and r.get("feature_id") == report_id for r in data["reasons"])


def test_wheelchair_routing_avoids_b2_evidence_wrapped_in_progress_work(monkeypatch, tmp_path: Path):
    # Checks that wheelchair routing avoids a B2-schema work with evidence-wrapped dates and no top-level status key.
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    work_id = "W-B2-WRAPPED-001"
    base = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    base["works"].append({
        "id": work_id,
        "works_type": "sidewalk",
        "resolution": "street",
        "title": {"value": "Έργο Β2 στη διαδρομή", "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-B12", "page": 1}},
        "street": {"value": "Ερμού", "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-B12", "page": 1}},
        "contractor": {"value": "Ανάδοχος Δοκιμής", "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-B12", "page": 1}},
        "amount_contract_eur": {"value": 50000.0, "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-B12", "page": 1}},
        "amount_paid_eur": {"value": 10000.0, "label": "INFERRED", "source": {"ada": "TEST-ΑΔΑ-B12", "page": 1}},
        "start_date": {"value": "2026-10-01", "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-B12", "page": 1}},
        "end_date": {"value": "2026-12-31", "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-B12", "page": 1}},
        "completion_date": {"value": None, "label": "UNKNOWN"},
        "guarantee_months": {"value": None, "label": "UNKNOWN"},
        "final_acceptance": False,
        "ada": {"value": "TEST-ΑΔΑ-B12", "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-B12", "page": 1}},
        "adam": {"value": "26SYMV000000001", "label": "CITED", "source": {"ada": "TEST-ΑΔΑ-B12", "page": 1}},
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [DIRECT_MID[0] - 0.0002, DIRECT_MID[1] - 0.0002],
                [DIRECT_MID[0] + 0.0002, DIRECT_MID[1] + 0.0002],
            ],
        },
    })
    p = tmp_path / "works_b12.json"
    p.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("STOA_WORKS_PATH", str(p))
    works._cache.clear()

    res = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": "wheelchair"})
    assert res.status_code == 200
    data = res.json()
    coords = data["geometry"]["coordinates"]
    assert _min_dist_to_point_m(coords, DIRECT_MID[0], DIRECT_MID[1]) > 20.0
    assert any(r.get("layer") == "works" and r.get("feature_id") == work_id for r in data["reasons"])
