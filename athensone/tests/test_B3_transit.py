"""Tests for B3: /api/map/transit (metro, suburban, OASA buses)."""
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)

SYNTAGMA_BBOX = (23.728, 37.970, 23.742, 37.981)
SYNTAGMA_BBOX_PARAM = ",".join(str(v) for v in SYNTAGMA_BBOX)
LAST_JSON_PATH = config.DATA_DIR / "transit" / "last.json"

# Strictly monotonic clock base > real wall-clock time so TTL caches from earlier tests never leak.
_CLOCK_BASE = 3_000_000_000.0


def _norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").lower()


def _extract_route_code(url: str, kwargs: dict) -> str:
    params = kwargs.get("params") or {}
    if isinstance(params, dict) and params.get("p1"):
        return str(params["p1"])
    qs = parse_qs(urlparse(str(url)).query)
    if qs.get("p1"):
        return str(qs["p1"][0])
    return "2040"


def _is_stop_arrivals(url: str, kwargs: dict) -> bool:
    params = kwargs.get("params") or {}
    if isinstance(params, dict) and params.get("act") == "getStopArrivals":
        return True
    return "getStopArrivals" in str(url)


def _oasa_bus_payload(route_code: str) -> list[dict]:
    # Sample OASA telematics getBusLocation response: one bus at Syntagma, one in Piraeus.
    return [
        {
            "VEH_NO": "30214",
            "CS_DATE": "Nov 21 2026 08:15:00:000PM",
            "CS_LAT": "37.9755",
            "CS_LNG": "23.7348",
            "ROUTE_CODE": route_code,
        },
        {
            "VEH_NO": "30519",
            "CS_DATE": "Nov 21 2026 08:15:05:000PM",
            "CS_LAT": "37.9480",
            "CS_LNG": "23.6420",
            "ROUTE_CODE": route_code,
        },
    ]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _patch_oasa(monkeypatch, payload_fn=None, exc: Exception | None = None) -> list[tuple[str, dict]]:
    calls: list[tuple[str, dict]] = []

    def fake_http(url, *args, **kwargs):
        calls.append((str(url), kwargs))
        if exc is not None:
            raise exc
        if _is_stop_arrivals(str(url), kwargs):
            return _FakeResponse([])
        route_code = _extract_route_code(str(url), kwargs)
        data = payload_fn(route_code) if payload_fn else _oasa_bus_payload(route_code)
        return _FakeResponse(data)

    monkeypatch.setattr(httpx, "get", fake_http)
    monkeypatch.setattr(httpx, "post", fake_http)
    return calls


def _patch_clock(monkeypatch, start: float | None = None) -> list[float]:
    global _CLOCK_BASE
    if start is None:
        _CLOCK_BASE += 100_000.0
        start = _CLOCK_BASE
    now = [start]
    monkeypatch.setattr(time, "time", lambda: now[0])
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    return now


def _clear_transit_mem_cache():
    mod = sys.modules.get("app.transit_src")
    if not mod:
        return
    for name in ("_cache", "_mem", "CACHE", "_bus_cache"):
        obj = getattr(mod, name, None)
        if isinstance(obj, dict):
            obj.clear()


@pytest.fixture(autouse=True)
def _isolate_transit_state():
    existed = LAST_JSON_PATH.exists()
    backup = LAST_JSON_PATH.read_bytes() if existed else None
    _clear_transit_mem_cache()
    yield
    _clear_transit_mem_cache()
    if existed and backup is not None:
        LAST_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_JSON_PATH.write_bytes(backup)
    elif LAST_JSON_PATH.exists():
        LAST_JSON_PATH.unlink()


def test_transit_contract(monkeypatch):
    # Checks that GET /api/map/transit returns FeatureCollections for lines, stations, and buses plus source.
    _patch_clock(monkeypatch)
    _patch_oasa(monkeypatch)

    r = c.get("/api/map/transit")
    assert r.status_code == 200
    data = r.json()
    for key in ("lines", "stations", "buses"):
        assert isinstance(data.get(key), dict)
        assert data[key].get("type") == "FeatureCollection"
        assert isinstance(data[key].get("features"), list)
        assert len(data[key]["features"]) >= 1
    assert data.get("source") in ("live", "cache", "snapshot")


def test_transit_bbox_filters_stations_and_buses(monkeypatch):
    # Checks that a Syntagma bbox keeps Syntagma, excludes Piraeus, and drops buses outside the bbox.
    _patch_clock(monkeypatch)
    _patch_oasa(monkeypatch)

    r = c.get("/api/map/transit", params={"bbox": SYNTAGMA_BBOX_PARAM})
    assert r.status_code == 200
    data = r.json()

    min_lon, min_lat, max_lon, max_lat = SYNTAGMA_BBOX
    stations = data["stations"]["features"]
    assert len(stations) >= 1
    station_names = [_norm((f.get("properties") or {}).get("name", "")) for f in stations]
    assert any("συνταγμα" in n or "syntagma" in n for n in station_names)
    assert not any("πειραια" in n or "piraeus" in n for n in station_names)
    for feat in stations:
        lon, lat = feat["geometry"]["coordinates"]
        assert min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

    buses = data["buses"]["features"]
    assert len(buses) >= 1
    for feat in buses:
        lon, lat = feat["geometry"]["coordinates"]
        assert min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def test_line_colours_hex(monkeypatch):
    # Checks that every static transit line feature carries a #rrggbb hex color property.
    _patch_clock(monkeypatch)
    _patch_oasa(monkeypatch)

    r = c.get("/api/map/transit")
    assert r.status_code == 200
    lines = r.json()["lines"]["features"]
    assert len(lines) >= 1
    for feat in lines:
        color = (feat.get("properties") or {}).get("color")
        assert isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)


def test_bus_location_parser_fixture(monkeypatch):
    # Checks that a getBusLocation JSON fixture parses into bus Point features with float lon/lat, line, and bearing.
    _patch_clock(monkeypatch)
    _patch_oasa(
        monkeypatch,
        payload_fn=lambda rc: [
            {
                "VEH_NO": "30214",
                "CS_DATE": "Nov 21 2026 08:15:00:000PM",
                "CS_LAT": "37.9755",
                "CS_LNG": "23.7348",
                "ROUTE_CODE": rc,
            }
        ],
    )

    r = c.get("/api/map/transit")
    assert r.status_code == 200
    buses = r.json()["buses"]["features"]
    assert len(buses) >= 1
    for feat in buses:
        assert feat["geometry"]["type"] == "Point"
        coords = feat["geometry"]["coordinates"]
        assert len(coords) == 2
        assert isinstance(coords[0], float) and isinstance(coords[1], float)
        props = feat["properties"]
        assert isinstance(props.get("line"), str) and props["line"]
        assert "bearing" in props
        assert props["bearing"] is None or isinstance(props["bearing"], (int, float))
    assert any(
        abs(f["geometry"]["coordinates"][0] - 23.7348) < 1e-6
        and abs(f["geometry"]["coordinates"][1] - 37.9755) < 1e-6
        for f in buses
    )


def test_bus_cache_20s(monkeypatch):
    # Checks that two requests 5 s apart hit the OASA upstream only on the first call within the 20 s TTL.
    now = _patch_clock(monkeypatch)
    calls = _patch_oasa(monkeypatch)

    r1 = c.get("/api/map/transit")
    assert r1.status_code == 200
    first_call_count = len(calls)
    assert first_call_count >= 1

    now[0] += 5.0
    r2 = c.get("/api/map/transit")
    assert r2.status_code == 200
    assert len(calls) == first_call_count


def test_oasa_down_serves_snapshot(monkeypatch):
    # Checks that when OASA raises after a good call and cache expires, last good buses are served with source="snapshot".
    now = _patch_clock(monkeypatch)
    _patch_oasa(monkeypatch)

    r1 = c.get("/api/map/transit")
    assert r1.status_code == 200
    good_buses = r1.json()["buses"]["features"]
    assert len(good_buses) >= 1

    now[0] += 60.0
    _clear_transit_mem_cache()
    _patch_oasa(monkeypatch, exc=httpx.ConnectError("OASA down"))

    r2 = c.get("/api/map/transit")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2.get("source") == "snapshot"
    assert len(data2["buses"]["features"]) == len(good_buses)


def test_nothing_available_empty_200(monkeypatch, tmp_path):
    # Checks that when OASA raises and no snapshot exists, HTTP 200 is returned with empty buses and source="unavailable".
    _patch_clock(monkeypatch)
    _clear_transit_mem_cache()
    if LAST_JSON_PATH.exists():
        LAST_JSON_PATH.unlink()
    mod = sys.modules.get("app.transit_src")
    if mod:
        for attr in ("LAST_PATH", "SNAPSHOT_PATH"):
            if isinstance(getattr(mod, attr, None), Path):
                monkeypatch.setattr(mod, attr, tmp_path / "last.json")
    _patch_oasa(monkeypatch, exc=httpx.ConnectError("OASA down"))

    r = c.get("/api/map/transit")
    assert r.status_code == 200
    data = r.json()
    assert data["buses"]["type"] == "FeatureCollection"
    assert data["buses"]["features"] == []
    assert data.get("source") == "unavailable"
