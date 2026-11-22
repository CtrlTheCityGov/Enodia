"""Tests for B16: backend backlog fixes (T2 Athens day, B6 bounds, B9 blocked flag, B12 duplicate count)."""
import os
from datetime import datetime, timezone

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ckan, env, main, routing, store, works  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)

# Coordinates from the card / SPEC demo script (certainty: sure).
SYNTAGMA = [23.7348, 37.9755]
MONASTIRAKI = [23.7257, 37.9761]
MID = [(SYNTAGMA[0] + MONASTIRAKI[0]) / 2, (SYNTAGMA[1] + MONASTIRAKI[1]) / 2]
PIRAEUS = {"lon": 23.6470, "lat": 37.9420}
OUTSIDE_MSG = "Η αναφορά είναι εκτός Δήμου Αθηναίων"
W_SEED_001 = (23.7420, 37.9660)

ACTION = "report_approved"
ACCOUNT = "acct-b16"


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


def _seed_ledger(created_at: str, n: int) -> None:
    """Insert n ledger rows for ACCOUNT/ACTION at a fixed UTC timestamp."""
    with store._lock:
        for i in range(n):
            store._conn.execute(
                "INSERT INTO points_ledger (account, district, action, ref_id, points, verified_by, created_at) "
                "VALUES (?, NULL, ?, ?, 10, 'test', ?)",
                (ACCOUNT, ACTION, f"seed-{created_at}-{i}", created_at),
            )
        store._conn.commit()


def _freeze_now(monkeypatch, iso: str) -> None:
    """Make store._now_iso() (the store's clock helper) return a fixed UTC instant."""
    fixed = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    monkeypatch.setattr(store, "_now_iso", lambda: fixed)


def test_daily_cap_uses_athens_day(monkeypatch):
    # Cap reached at 23:30 Athens on 21 Nov; at 00:30 Athens on 22 Nov a new award must be allowed.
    _seed_ledger("2026-11-21 21:30:00", 2)
    _freeze_now(monkeypatch, "2026-11-21T22:30:00Z")
    assert store.insert_points(ACCOUNT, None, ACTION, "new-ref", 10, "test", daily_cap=2) is True


def test_daily_cap_same_athens_day_still_blocks(monkeypatch):
    # Cap reached at 11:00 Athens and it is 23:00 Athens the same day: still refused.
    _seed_ledger("2026-11-21 08:00:00", 2)
    _freeze_now(monkeypatch, "2026-11-21T20:00:00Z")
    assert store.insert_points(ACCOUNT, None, ACTION, "new-ref", 10, "test", daily_cap=2) is False


def _post_report(lon: float, lat: float, category: str = "incident", client: TestClient = c):
    return client.post("/api/map/reports", data={"category": category, "lon": lon, "lat": lat, "note": "δοκιμή"})


def test_report_outside_athens_422():
    # A report at Piraeus is refused with the Greek message; nothing stored and no points.
    client = TestClient(app)
    before = client.get("/api/map/reports").json()["features"]
    r = _post_report(PIRAEUS["lon"], PIRAEUS["lat"], client=client)
    assert r.status_code == 422
    assert OUTSIDE_MSG in str(r.json())
    assert client.get("/api/map/reports").json()["features"] == before
    assert client.get("/api/points/me").json()["balance"] == 0


def test_report_inside_athens_still_ok():
    # The same POST at Syntagma is accepted as before.
    r = _post_report(23.7348, 37.9755)
    assert r.status_code in (200, 201)


@pytest.mark.parametrize("bbox", ["nan,nan,nan,nan", "-inf,0,inf,1"])
def test_reports_bbox_non_finite_422(bbox):
    # A non-finite bbox on the list endpoint is a 422.
    assert c.get("/api/map/reports", params={"bbox": bbox}).status_code == 422


def _blocked_candidates():
    """Two candidates that both run straight through MID (where the obstacle report will be)."""
    def cand(label, dx):
        coords = [SYNTAGMA, [MID[0], MID[1] + dx], MONASTIRAKI]
        return {"source": "fallback", "label": label, "geojson": {"type": "LineString", "coordinates": coords},
                "distance_km": 0.7, "duration_min": 9.0, "steps": [], "avoided_hazards": 0}
    return [cand("a", 0.0), cand("b", 0.0)]


def _route(monkeypatch, profile: str) -> dict:
    cands = _blocked_candidates()
    monkeypatch.setattr(routing, "candidates", lambda *a, **kw: [dict(x) for x in cands])
    r = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": profile})
    assert r.status_code == 200
    return r.json()


def _report_obstacle_on_route() -> None:
    r = _post_report(MID[0], MID[1], category="obstacle")
    assert r.status_code in (200, 201)


def test_routing_blocked_true_when_every_candidate_blocked(monkeypatch):
    # Every wheelchair candidate passes through an obstacle report, so blocked must be True.
    _report_obstacle_on_route()
    assert _route(monkeypatch, "wheelchair")["blocked"] is True


def test_routing_blocked_false_normally():
    # The plain Syntagma -> Monastiraki wheelchair route with no blockers is not blocked.
    r = c.post("/api/map/routing", json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": "wheelchair"})
    assert r.status_code == 200
    assert r.json()["blocked"] is False


def test_routing_blocked_false_for_stroller(monkeypatch):
    # Same blocked candidates, but the stroller profile has no hard blockers, so blocked is False.
    _report_obstacle_on_route()
    assert _route(monkeypatch, "stroller")["blocked"] is False


def test_duplicate_obstacle_not_double_counted_on_work():
    # Two obstacle reports ~10 m apart on W-SEED-001: the work shows one report, not two.
    client = TestClient(app)
    lon, lat = W_SEED_001
    assert _post_report(lon, lat, category="obstacle", client=client).status_code in (200, 201)
    assert _post_report(lon + 0.0001, lat, category="obstacle", client=client).status_code in (200, 201)
    feats = client.get("/api/map/works").json()["features"]
    props = next(f["properties"] for f in feats if f["properties"]["id"] == "W-SEED-001")
    assert props["reports_count"] == 1
