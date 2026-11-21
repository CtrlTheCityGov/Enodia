"""Tests for GET /api/map/transit/arrivals and GET /api/map/works/lookup."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import transit_src
from app.main import app


def test_transit_arrivals_endpoint(monkeypatch):
    transit_src._arrivals_cache.clear()
    monkeypatch.setattr(
        transit_src,
        "fetch_stop_arrivals",
        lambda code: [{"route_code": "3922", "veh_code": "101", "btime2": "4"}],
    )
    client = TestClient(app)
    r = client.get("/api/map/transit/arrivals?stop_code=060001")
    assert r.status_code == 200
    body = r.json()
    assert body["stop_code"] == "060001"
    assert body["source"] == "live"
    assert body["arrivals"] == [{"route_code": "3922", "vehicle_id": "101", "wait_min": 4}]


def test_transit_arrivals_rejects_bad_code():
    client = TestClient(app)
    r = client.get("/api/map/transit/arrivals?stop_code=bad/code")
    assert r.status_code == 400


def test_works_lookup_endpoint(monkeypatch):
    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "ada": "6ΑΒΓ46ΜΝΟΠ-123",
                "subject": "Ανάπλαση πεζοδρομίων",
                "decisionTypeId": "Δ.1",
                "issueDate": 1763683200000,
                "organizationId": "6013",
                "documentUrl": "https://diavgeia.gov.gr/doc/6ΑΒΓ46ΜΝΟΠ-123",
            }

    monkeypatch.setattr("app.routers.works_map.httpx.get", lambda *a, **kw: FakeResp())
    client = TestClient(app)
    r = client.get("/api/map/works/lookup?ada=6ΑΒΓ46ΜΝΟΠ-123")
    assert r.status_code == 200
    body = r.json()
    assert body["ada"] == "6ΑΒΓ46ΜΝΟΠ-123"
    assert body["organization_id"] == "6013"
    assert body["source"] == "live"


def test_works_lookup_rejects_bad_ada():
    client = TestClient(app)
    r = client.get("/api/map/works/lookup?ada=bad/ada")
    assert r.status_code == 400


def test_points_leaderboard_endpoint():
    client = TestClient(app)
    r = client.get("/api/map/points/leaderboard")
    assert r.status_code == 200
    body = r.json()
    assert "target" in body and isinstance(body["districts"], list)


def test_cool_spots_endpoint():
    client = TestClient(app)
    r = client.get("/api/map/cool-spots")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) >= 1
    assert "uv_index" in open("app/envgrid_src.py", encoding="utf-8").read()


def test_map_reports_rejects_nonfinite_bbox():
    client = TestClient(app)
    r = client.get("/api/map/reports?bbox=23.7,37.9,nan,38.0")
    assert r.status_code == 422


def test_reports_export_csv(monkeypatch):
    from app import main as app_main

    monkeypatch.setattr(
        app_main.sb,
        "list_requests",
        lambda mine=True: {
            "items": [
                {
                    "id": "REQ-1",
                    "status": "submitted",
                    "category": "pothole",
                    "lat": 37.975,
                    "lng": 23.734,
                    "created_at": "2026-11-21T20:00:00Z",
                }
            ]
        },
    )
    client = TestClient(app)
    r = client.get("/api/reports/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "id,status,category" in r.text
    assert "REQ-1,submitted,pothole" in r.text


def test_map_reports_syncs_city_request_status(monkeypatch):
    from app import main as app_main, map_reports

    map_reports.clear()
    saved = map_reports.create("acct-1", "obstacle", 23.734, 37.975, "blocked ramp", None, None)
    map_reports.link_city_request(saved["id"], "CITY-99")
    monkeypatch.setattr(
        app_main.sb,
        "list_requests",
        lambda mine=True: {"items": [{"id": "CITY-99", "status": "in_progress"}]},
    )
    client = TestClient(app)
    r = client.get("/api/map/reports")
    assert r.status_code == 200
    feats = r.json()["features"]
    assert feats[0]["properties"]["status"] == "in_progress"
