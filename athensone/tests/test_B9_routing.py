"""Tests for B9: Route cost per profile (POST /api/map/routing)."""
import io
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
from PIL import Image  # noqa: E402

from app import ckan, config, env, main, routing, store, works  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)

# Demo endpoints from SPEC.md ("Demo script" & TASKS_B.md B0/B9; certainty: sure).
SYNTAGMA = [23.7348, 37.9755]
MONASTIRAKI = [23.7257, 37.9761]
DIRECT_MID = [(SYNTAGMA[0] + MONASTIRAKI[0]) / 2, (SYNTAGMA[1] + MONASTIRAKI[1]) / 2]

# Pangrati route from tests/test_smoke.py NAV where data/env_seed.json has trees/busy_road (certainty: sure).
PANGRATI_FROM = [23.7437, 37.9667]
PANGRATI_TO = [23.7476, 37.9689]
NAV = {"from_lat": 37.9667, "from_lng": 23.7437, "to_lat": 37.9689, "to_lng": 23.7476}


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


def _jpeg_bytes() -> bytes:
    img = Image.new("RGB", (320, 240), (90, 90, 120))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


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


def _write_seed_with_in_progress_work(monkeypatch, tmp_path: Path, work_id: str = "W-SEED-INPROG") -> str:
    """Create a temporary SEED works file adding an in-progress work across SYNTAGMA->MONASTIRAKI."""
    base = json.loads((config.DATA_DIR / "works_seed.json").read_text(encoding="utf-8"))
    base["works"].append({
        "id": work_id,
        "works_type": "sidewalk",
        "resolution": "street",
        "status": "in_progress",
        "start_date": "2026-11-01",
        "end_date": "2026-12-31",
        "title": {"value": "Έργο επί της διαδρομής (δείγμα)", "label": "CITED", "source": {"ada": "SEED-ΑΔΑ-099", "page": 1}},
        "street": {"value": "Ερμού (δείγμα)", "label": "CITED", "source": {"ada": "SEED-ΑΔΑ-099", "page": 1}},
        "contractor": {"value": "Ανάδοχος Δείγμα (SEED)", "label": "CITED", "source": {"ada": "SEED-ΑΔΑ-099", "page": 1}},
        "amount_paid_eur": {"value": 15000.0, "label": "CITED", "source": {"ada": "SEED-ΑΔΑ-099", "page": 1}},
        "completion_date": {"value": None, "label": "UNKNOWN"},
        "guarantee_months": {"value": None, "label": "UNKNOWN"},
        "final_acceptance": False,
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [DIRECT_MID[0] - 0.0002, DIRECT_MID[1] - 0.0002],
                [DIRECT_MID[0] + 0.0002, DIRECT_MID[1] + 0.0002],
            ],
        },
    })
    p = tmp_path / "works_seed_b9.json"
    p.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("STOA_WORKS_PATH", str(p))
    works._cache.clear()
    return work_id


def test_routing_contract():
    # Checks that POST /api/map/routing returns all SPEC keys, a LineString geometry, and walk legs offline.
    r = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": "wheelchair"})
    assert r.status_code == 200
    data = r.json()
    assert {"geometry", "distance_m", "duration_s", "legs", "reasons"} <= set(data)
    assert data["geometry"]["type"] == "LineString"
    coords = data["geometry"]["coordinates"]
    assert isinstance(coords, list) and len(coords) >= 2
    assert all(isinstance(pt, list) and len(pt) == 2 for pt in coords)
    assert isinstance(data["distance_m"], (int, float)) and data["distance_m"] > 0
    assert isinstance(data["duration_s"], (int, float)) and data["duration_s"] > 0
    assert data["legs"] == [{"mode": "walk"}]
    assert isinstance(data["reasons"], list)


def test_wheelchair_avoids_in_progress_work(monkeypatch, tmp_path):
    # Checks that wheelchair routing avoids a SEED in-progress work on the direct path and cites its id.
    work_id = _write_seed_with_in_progress_work(monkeypatch, tmp_path)

    r = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": "wheelchair"})
    assert r.status_code == 200
    data = r.json()
    coords = data["geometry"]["coordinates"]
    assert _min_dist_to_point_m(coords, DIRECT_MID[0], DIRECT_MID[1]) > 20.0
    assert any(reason.get("layer") == "works" and reason.get("feature_id") == work_id for reason in data["reasons"])


def test_wheelchair_avoids_obstacle_report():
    # Checks that wheelchair routing avoids an open obstacle report on the direct path and cites its id.
    rep = c.post(
        "/api/report",
        files={"photo": ("obs.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"lat": DIRECT_MID[1], "lng": DIRECT_MID[0], "note": "εμπόδιο στη ράμπα"},
    )
    assert rep.status_code == 200
    rid = rep.json()["request"]["id"]

    r = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": "wheelchair"})
    assert r.status_code == 200
    data = r.json()
    coords = data["geometry"]["coordinates"]
    assert _min_dist_to_point_m(coords, DIRECT_MID[0], DIRECT_MID[1]) > 20.0
    assert any(reason.get("layer") == "reports" and reason.get("feature_id") == rid for reason in data["reasons"])


def test_stroller_avoids_congestion_soft(monkeypatch):
    # Checks that stroller routing keeps the direct path when the only congestion detour is 3x longer, with no reason.
    store.save(
        "REP-CONG-1",
        "",
        DIRECT_MID[1],
        DIRECT_MID[0],
        {"category": "congestion", "severity": 3, "confidence": 0.9, "accessibility_blocker": False},
        0,
    )
    direct_coords = [SYNTAGMA, MONASTIRAKI]
    long_coords = [SYNTAGMA, [DIRECT_MID[0], DIRECT_MID[1] + 0.01], MONASTIRAKI]
    cands = [
        {
            "source": "fallback",
            "label": "direct",
            "geojson": {"type": "LineString", "coordinates": direct_coords},
            "distance_km": 0.8,
            "duration_min": 10.0,
            "steps": [],
            "avoided_hazards": 0,
        },
        {
            "source": "fallback",
            "label": "long-detour",
            "geojson": {"type": "LineString", "coordinates": long_coords},
            "distance_km": 2.4,
            "duration_min": 30.0,
            "steps": [],
            "avoided_hazards": 0,
        },
    ]
    monkeypatch.setattr(routing, "candidates", lambda *a, **kw: [dict(x) for x in cands])

    r = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": "stroller"})
    assert r.status_code == 200
    data = r.json()
    assert data["geometry"]["coordinates"] == direct_coords
    assert data["reasons"] == []


def test_cool_prefers_shade(monkeypatch):
    # Checks that cool routing picks the shadier candidate over the direct sunny one and adds an env reason.
    sunny_coords = [PANGRATI_FROM, PANGRATI_TO]
    shady_coords = [PANGRATI_FROM, [23.7448, 37.9687], PANGRATI_TO]
    cands = [
        {
            "source": "fallback",
            "label": "sunny-direct",
            "geojson": {"type": "LineString", "coordinates": sunny_coords},
            "distance_km": 0.42,
            "duration_min": 5.0,
            "steps": [],
            "avoided_hazards": 0,
        },
        {
            "source": "fallback",
            "label": "shady-detour",
            "geojson": {"type": "LineString", "coordinates": shady_coords},
            "distance_km": 0.47,
            "duration_min": 5.6,
            "steps": [],
            "avoided_hazards": 0,
        },
    ]
    monkeypatch.setattr(routing, "candidates", lambda *a, **kw: [dict(x) for x in cands])

    r = c.post("/api/map/routing", json={"from": PANGRATI_FROM, "to": PANGRATI_TO, "profile": "cool"})
    assert r.status_code == 200
    data = r.json()
    assert data["geometry"]["coordinates"] == shady_coords
    assert any(reason.get("layer") == "env" for reason in data["reasons"])


def test_profiles_differ(monkeypatch, tmp_path):
    # Checks that wheelchair and cool return different geometries for the same origin/destination with a work on the direct path.
    _write_seed_with_in_progress_work(monkeypatch, tmp_path)

    r_wc = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": "wheelchair"})
    r_cool = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": "cool"})
    assert r_wc.status_code == 200
    assert r_cool.status_code == 200
    assert r_wc.json()["geometry"]["coordinates"] != r_cool.json()["geometry"]["coordinates"]


def test_bad_profile_422():
    # Checks that an unsupported profile like 'car' returns HTTP 422.
    r = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": "car"})
    assert r.status_code == 422


def test_reasons_point_at_real_features(monkeypatch, tmp_path):
    # Checks that every reason's feature_id resolves to a real feature in its corresponding layer's data.
    _write_seed_with_in_progress_work(monkeypatch, tmp_path)
    rep = c.post(
        "/api/report",
        files={"photo": ("obs.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"lat": DIRECT_MID[1], "lng": DIRECT_MID[0], "note": "εμπόδιο στη ράμπα"},
    )
    assert rep.status_code == 200

    r = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": "wheelchair"})
    assert r.status_code == 200
    reasons = r.json()["reasons"]
    assert len(reasons) >= 1

    work_ids = {w["id"] for w in works.all_cards()}
    report_ids = {row["request_id"] for row in store.all_reports()}
    for reason in reasons:
        assert {"text", "layer", "feature_id"} <= set(reason)
        assert isinstance(reason["text"], str) and reason["text"]
        if reason["layer"] == "works":
            assert reason["feature_id"] in work_ids
        elif reason["layer"] == "reports":
            assert reason["feature_id"] in report_ids
        elif reason["layer"] == "env":
            assert isinstance(reason["feature_id"], str) and reason["feature_id"]
        else:
            pytest.fail(f"unexpected reason layer: {reason['layer']}")


def test_existing_navigate_unchanged():
    # Checks that GET /api/navigate keeps the exact response, prefs, and candidate keys unchanged.
    r = c.get("/api/navigate", params={**NAV, "shade": True, "air": True, "rest": True})
    assert r.status_code == 200
    data = r.json()
    assert {
        "chosen",
        "candidates",
        "explanation_el",
        "air_quality",
        "prefs",
        "weather",
        "env",
        "routing",
        "avoided_hazards",
    } <= set(data)
    assert {"profile", "shade", "air", "rest", "heat", "heat_auto"} <= set(data["prefs"])
    assert data["candidates"]
    for cand in data["candidates"]:
        assert {
            "source",
            "label",
            "geojson",
            "distance_km",
            "duration_min",
            "steps",
            "avoided_hazards",
            "metrics",
            "score",
            "too_long",
            "chosen",
            "fastest",
        } <= set(cand)
