"""Tests for T8: Heat fixes (GET /api/heat)."""
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ckan, config, main, routing  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
START = {"lat": 37.9667, "lng": 23.7437}


@pytest.fixture(autouse=True)
def _clean_state():
    c.post("/api/admin/reset")
    main._weather.clear()
    routing._cache.clear()
    yield
    main._weather.clear()
    routing._cache.clear()


def _fake_open_meteo(monkeypatch, temp_c: float, uv: float = 3.0):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"current": {"temperature_2m": temp_c, "uv_index": uv}}

    monkeypatch.setattr(config, "WEATHER", "on")
    monkeypatch.setattr(main.httpx, "get", lambda *a, **kw: _Resp())


def test_not_hot_no_minutes_no_route(monkeypatch):
    # Checks that when not hot (25 °C), minutes is None and routing is not called.
    monkeypatch.setattr(config, "HEAT_FORCE", False)
    monkeypatch.setattr(ckan, "nearest_air", lambda lat, lng, max_km=1.5: None)
    _fake_open_meteo(monkeypatch, 25.0)

    def _fail_routing(*args, **kwargs):
        pytest.fail("routing should not be called when hot is false")

    monkeypatch.setattr(routing, "candidates", _fail_routing)
    monkeypatch.setattr(routing, "route", _fail_routing)

    r = c.get("/api/heat", params=START)
    assert r.status_code == 200
    data = r.json()
    assert data["hot"] is False
    assert data["minutes"] is None


def test_hot_still_has_minutes(monkeypatch):
    # Checks that when hot (34.5 °C), minutes is still returned as a number.
    station = {
        "station_id": 99,
        "name": "Σταθμός Παγκρατίου",
        "lat": 37.968,
        "lng": 23.745,
        "temp_c": 34.5,
        "aqi": 2,
        "distance_km": 0.19,
    }
    monkeypatch.setattr(ckan, "nearest_air", lambda lat, lng, max_km=1.5: station)

    r = c.get("/api/heat", params=START)
    assert r.status_code == 200
    data = r.json()
    assert data["hot"] is True
    assert isinstance(data["minutes"], (int, float)) and not isinstance(data["minutes"], bool)


def test_inf_lat_is_client_error():
    # Checks that non-finite lat=inf returns a 400 or 422 client error instead of 500.
    r = c.get("/api/heat", params={"lat": "inf", "lng": START["lng"]})
    assert r.status_code in (400, 422)


def test_station_without_name_or_id(monkeypatch):
    # Checks that a station dict with only temp_c=34.5 returns 200, hot=True, and source starting with "AthensGov".
    monkeypatch.setattr(ckan, "nearest_air", lambda lat, lng, max_km=1.5: {"temp_c": 34.5})

    r = c.get("/api/heat", params=START)
    assert r.status_code == 200
    data = r.json()
    assert data["hot"] is True
    assert data["source"].startswith("AthensGov")
