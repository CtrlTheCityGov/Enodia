"""Fix-round tests for B6: rounded coordinates to sandbox and no duplicate City requests."""
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.main import app  # noqa: E402


def test_city_request_receives_rounded_coords(monkeypatch):
    # Verify _city_request passes 4-decimal (~10 m) rounded coordinates and address to the sandbox.
    TestClient(app).post("/api/admin/reset")
    client = TestClient(app)

    calls = []
    orig_create = main.sb.create_request

    def spy_create(*args, **kwargs):
        calls.append(kwargs)
        return orig_create(*args, **kwargs)

    monkeypatch.setattr(main.sb, "create_request", spy_create)

    res = client.post(
        "/api/map/reports",
        data={"category": "obstacle", "lon": 23.7275123, "lat": 37.9838123, "note": "εμπόδιο"},
    )
    assert res.status_code == 200
    assert len(calls) == 1
    kw = calls[0]
    assert kw["lng"] == 23.7275
    assert kw["lat"] == 37.9838
    assert "37.9838123" not in kw["address"]
    assert "23.7275123" not in kw["address"]
    assert kw["address"] == "37.9838, 23.7275"


def test_duplicate_obstacle_no_second_city_request(monkeypatch):
    # Verify a duplicate obstacle within 50 m and 30 min does not create a second sandbox City request.
    TestClient(app).post("/api/admin/reset")
    client = TestClient(app)

    calls = []
    orig_create = main.sb.create_request

    def spy_create(*args, **kwargs):
        calls.append(kwargs)
        return orig_create(*args, **kwargs)

    monkeypatch.setattr(main.sb, "create_request", spy_create)

    r1 = client.post(
        "/api/map/reports",
        data={"category": "obstacle", "lon": 23.7348, "lat": 37.9755, "note": "πρώτο"},
    )
    assert r1.status_code == 200
    assert r1.json()["points_awarded"] == 5

    r2 = client.post(
        "/api/map/reports",
        data={"category": "obstacle", "lon": 23.7348, "lat": 37.97568, "note": "δεύτερο"},
    )
    assert r2.status_code == 200
    assert r2.json()["points_awarded"] == 0
    assert len(calls) == 1
