"""Tests for B5: Env grid — temperature and AQI (GET /api/map/env)."""
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ckan, config  # noqa: E402
from app.geo import haversine_km  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)

# Municipality of Athens bbox from docs/TASKS_B.md (B0).
DIMOS_MIN_LON, DIMOS_MIN_LAT = 23.68, 37.95
DIMOS_MAX_LON, DIMOS_MAX_LAT = 23.80, 38.03

_CLOCK = [1_795_255_200.0]  # deterministic virtual Unix time (~2026-11-21)
_MONOTONIC = [10_000.0]


@pytest.fixture(scope="module", autouse=True)
def _cleanup_snapshot_dir():
    envgrid_dir = config.DATA_DIR / "envgrid"
    existed = envgrid_dir.exists()
    yield
    if not existed and envgrid_dir.exists():
        shutil.rmtree(envgrid_dir)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    # Advance virtual clock by 1 h between tests so any 15-min TTL cache starts expired.
    _CLOCK[0] += 3600.0
    _MONOTONIC[0] += 3600.0
    monkeypatch.setattr(time, "time", lambda: _CLOCK[0])
    monkeypatch.setattr(time, "monotonic", lambda: _MONOTONIC[0])
    monkeypatch.setattr(config, "WEATHER", "on")
    monkeypatch.setattr(config, "CKAN_MODE", "off")
    monkeypatch.setattr(ckan, "nearest_air", lambda lat, lng, max_km=1.5: None)


def _mock_open_meteo(monkeypatch, *, temp_base: float = 19.0, fail: bool = False):
    calls: list[dict] = []

    def _build_payload(request: httpx.Request) -> list[dict] | dict:
        url = str(request.url)
        lat_raw = request.url.params.get("latitude", "")
        lon_raw = request.url.params.get("longitude", "")
        lats = [float(x) for x in lat_raw.split(",") if x.strip()]
        lons = [float(x) for x in lon_raw.split(",") if x.strip()]
        assert lats and len(lats) == len(lons), f"expected multi-coordinate query, got {url}"

        if "air-quality" in url:
            kind = "air_quality"
            rows = [
                {
                    "latitude": lat,
                    "longitude": lon,
                    "timezone": "Europe/Athens",
                    "current": {
                        "time": "2026-11-21T12:00",
                        "european_aqi": 20 + (i % 4) * 5,
                        "pm2_5": round(8.0 + (i % 4) * 2.0, 2),
                    },
                }
                for i, (lat, lon) in enumerate(zip(lats, lons))
            ]
        elif "forecast" in url:
            kind = "forecast"
            rows = [
                {
                    "latitude": lat,
                    "longitude": lon,
                    "timezone": "Europe/Athens",
                    "current": {
                        "time": "2026-11-21T12:00",
                        "temperature_2m": round(temp_base + (i % 5) * 0.5, 2),
                    },
                }
                for i, (lat, lon) in enumerate(zip(lats, lons))
            ]
        else:
            raise AssertionError(f"unexpected external URL: {url}")

        calls.append({"kind": kind, "url": url, "count": len(rows)})
        return rows[0] if len(rows) == 1 else rows

    def fake_handle(self, request: httpx.Request) -> httpx.Response:
        if fail:
            raise httpx.ConnectError("mock upstream down", request=request)
        payload = _build_payload(request)
        return httpx.Response(200, content=json.dumps(payload).encode("utf-8"), headers={"content-type": "application/json"}, request=request)

    async def fake_async_handle(self, request: httpx.Request) -> httpx.Response:
        return fake_handle(self, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fake_handle)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_async_handle)
    return calls


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def test_env_contract(monkeypatch):
    # Checks GET /api/map/env returns a GeoJSON FeatureCollection of Points with temp_c, aqi, pm25, updated_at and source.
    _mock_open_meteo(monkeypatch)

    r = c.get("/api/map/env")
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "FeatureCollection"
    assert data["source"] in ("live", "cache", "snapshot")
    assert isinstance(data.get("updated_at"), str) and data["updated_at"]
    datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
    assert isinstance(data["features"], list) and len(data["features"]) > 0

    for feat in data["features"]:
        assert feat["type"] == "Feature"
        geom = feat["geometry"]
        assert geom["type"] == "Point"
        assert len(geom["coordinates"]) == 2 and all(_is_number(x) for x in geom["coordinates"])
        props = feat["properties"]
        assert _is_number(props["temp_c"])
        assert _is_number(props["aqi"])
        assert _is_number(props["pm25"])
        assert isinstance(props["updated_at"], str) and props["updated_at"]
        datetime.fromisoformat(props["updated_at"].replace("Z", "+00:00"))


def test_grid_covers_dimos(monkeypatch):
    # Checks that the default grid has at least 20 distinct points, all within the Athens Municipality bbox.
    _mock_open_meteo(monkeypatch)

    r = c.get("/api/map/env")
    assert r.status_code == 200
    feats = r.json()["features"]
    assert len(feats) >= 20
    coords = set()
    for feat in feats:
        lon, lat = feat["geometry"]["coordinates"]
        assert DIMOS_MIN_LON <= lon <= DIMOS_MAX_LON
        assert DIMOS_MIN_LAT <= lat <= DIMOS_MAX_LAT
        coords.add((round(lon, 5), round(lat, 5)))
    assert len(coords) >= 20


def test_bbox_param_spec_format(monkeypatch):
    # Checks that ?bbox=minLon,minLat,maxLon,maxLat keeps only grid points inside the requested box.
    _mock_open_meteo(monkeypatch)

    r_full = c.get("/api/map/env")
    assert r_full.status_code == 200
    full = r_full.json()["features"]
    r = c.get("/api/map/env", params={"bbox": "23.72,37.97,23.74,37.98"})
    assert r.status_code == 200
    filtered = r.json()["features"]
    assert 0 < len(filtered) < len(full)
    for feat in filtered:
        lon, lat = feat["geometry"]["coordinates"]
        assert 23.72 <= lon <= 23.74
        assert 37.97 <= lat <= 37.98


def test_single_upstream_call_per_kind(monkeypatch):
    # Checks that building the full grid makes one Open-Meteo forecast call and one air-quality call.
    calls = _mock_open_meteo(monkeypatch)

    r = c.get("/api/map/env")
    assert r.status_code == 200
    kinds = [call["kind"] for call in calls]
    assert kinds.count("forecast") == 1
    assert kinds.count("air_quality") == 1
    assert all(call["count"] >= 20 for call in calls)


def test_cache_15min(monkeypatch):
    # Checks that two calls 10 minutes apart only hit Open-Meteo once per kind within the 15-min TTL.
    calls = _mock_open_meteo(monkeypatch)

    r1 = c.get("/api/map/env")
    assert r1.status_code == 200
    _CLOCK[0] += 600.0
    _MONOTONIC[0] += 600.0
    r2 = c.get("/api/map/env")
    assert r2.status_code == 200

    kinds = [call["kind"] for call in calls]
    assert kinds.count("forecast") == 1
    assert kinds.count("air_quality") == 1
    assert r2.json()["features"] == r1.json()["features"]


def test_station_overrides_model(monkeypatch):
    # Checks that a CKAN station 100 m from a grid point overrides that point's values and sets station.
    _mock_open_meteo(monkeypatch, temp_base=19.0)

    r1 = c.get("/api/map/env")
    assert r1.status_code == 200
    feats1 = r1.json()["features"]
    target_lon, target_lat = feats1[0]["geometry"]["coordinates"]

    # Place station ~100 m north of the first grid point (within 300 m threshold, >500 m from neighbors).
    station_lat = target_lat + 100.0 / 111_320.0
    station_lng = target_lon

    def fake_nearest_air(lat, lng, max_km=1.5):
        d = haversine_km(lat, lng, station_lat, station_lng)
        if d <= max_km:
            return {
                "station_id": "101",
                "name": "Σταθμός Συντάγματος",
                "lat": station_lat,
                "lng": station_lng,
                "temp_c": 29.5,
                "aqi": 4,
                "pm25": 31.0,
                "time": "2026-11-21T12:00:00",
                "distance_km": round(d, 2),
            }
        return None

    monkeypatch.setattr(config, "CKAN_MODE", "live")
    monkeypatch.setattr(ckan, "nearest_air", fake_nearest_air)
    _CLOCK[0] += 1200.0
    _MONOTONIC[0] += 1200.0

    r2 = c.get("/api/map/env")
    assert r2.status_code == 200
    feats2 = r2.json()["features"]

    near_feat = min(
        feats2,
        key=lambda f: haversine_km(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0], target_lat, target_lon),
    )
    far_feat = max(
        feats2,
        key=lambda f: haversine_km(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0], station_lat, station_lng),
    )

    near_props = near_feat["properties"]
    assert near_props["temp_c"] == 29.5
    assert near_props["aqi"] == 4
    assert near_props["pm25"] == 31.0
    assert near_props.get("station")

    assert not far_feat["properties"].get("station")
    assert far_feat["properties"]["temp_c"] != 29.5


def test_open_meteo_down_snapshot(monkeypatch):
    # Checks that when Open-Meteo fails after a successful fetch, the last good grid is served with source="snapshot".
    _mock_open_meteo(monkeypatch, temp_base=24.0, fail=False)
    r1 = c.get("/api/map/env")
    assert r1.status_code == 200
    good = r1.json()
    assert good["source"] == "live"
    assert len(good["features"]) >= 20

    # Expire the 15-min memory cache so the next request must try upstream and fall back to snapshot.
    _CLOCK[0] += 1200.0
    _MONOTONIC[0] += 1200.0
    _mock_open_meteo(monkeypatch, fail=True)

    r2 = c.get("/api/map/env")
    assert r2.status_code == 200
    snap = r2.json()
    assert snap["source"] == "snapshot"
    assert snap["features"] == good["features"]
