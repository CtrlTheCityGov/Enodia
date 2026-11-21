"""Tests for T3: Heat alert banner (GET /api/heat)."""
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ckan, config, main  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
START = {"lat": 37.9667, "lng": 23.7437}


@pytest.fixture(autouse=True)
def _clean_state():
    c.post("/api/admin/reset")
    main._weather.clear()
    yield
    main._weather.clear()


def _fake_open_meteo(monkeypatch, temp_c: float, uv: float = 3.0):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"current": {"temperature_2m": temp_c, "uv_index": uv}}

    monkeypatch.setattr(config, "WEATHER", "on")
    monkeypatch.setattr(main.httpx, "get", lambda *a, **kw: _Resp())


def test_heat_hot_from_station(monkeypatch):
    # Checks that a CKAN station reading >= HEAT_C marks hot=True and reports the station as source.
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
    assert data["temp_c"] == 34.5
    assert "Σταθμός Παγκρατίου" in data["source"]


def test_heat_cool_place_matches(monkeypatch):
    # Checks that the nearest cool_place returned by /api/heat matches the first /api/cool-places item.
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

    first_cool = c.get("/api/cool-places", params=START).json()["items"][0]
    r = c.get("/api/heat", params=START)
    assert r.status_code == 200
    assert r.json()["cool_place"] == first_cool


def test_heat_not_hot(monkeypatch):
    # Checks that a temperature below HEAT_C (25 °C) reports hot=False.
    monkeypatch.setattr(ckan, "nearest_air", lambda lat, lng, max_km=1.5: None)
    _fake_open_meteo(monkeypatch, 25.0)

    r = c.get("/api/heat", params=START)
    assert r.status_code == 200
    data = r.json()
    assert data["hot"] is False
    assert data["temp_c"] == 25.0


def test_heat_force_labelled(monkeypatch):
    # Checks that HEAT_FORCE=1 forces hot=True with forced=True even at 18 °C.
    monkeypatch.setattr(config, "HEAT_FORCE", True, raising=False)
    monkeypatch.setenv("HEAT_FORCE", "1")
    monkeypatch.setattr(ckan, "nearest_air", lambda lat, lng, max_km=1.5: None)
    _fake_open_meteo(monkeypatch, 18.0)

    r = c.get("/api/heat", params=START)
    assert r.status_code == 200
    data = r.json()
    assert data["hot"] is True
    assert data["forced"] is True


def test_heat_no_data(monkeypatch):
    # Checks that with weather off and no station, /api/heat returns hot=False, temp_c=None, source="UNKNOWN" with no error.
    monkeypatch.setattr(config, "WEATHER", "off")
    monkeypatch.setattr(ckan, "nearest_air", lambda lat, lng, max_km=1.5: None)

    r = c.get("/api/heat", params=START)
    assert r.status_code == 200
    data = r.json()
    assert data["hot"] is False
    assert data["temp_c"] is None
    assert data["source"] == "UNKNOWN"
