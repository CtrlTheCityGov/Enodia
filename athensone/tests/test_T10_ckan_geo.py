"""Tests for T10: City districts and air stations from CKAN."""
import json
import os
from pathlib import Path

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ckan, config  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ckan"
VARNAVA = (37.9667, 23.7437)


@pytest.fixture(autouse=True)
def _clean_ckan_cache():
    ckan._mem.clear()
    yield
    ckan._mem.clear()


def _load_fixture(slug: str) -> dict:
    return json.loads((FIXTURES / f"{slug}.json").read_text(encoding="utf-8"))


def _patch_ckan_fixtures(monkeypatch, overrides: dict[str, dict] | None = None):
    datasets = {
        slug: (overrides[slug] if overrides and slug in overrides else _load_fixture(slug))
        for slug in (
            "municipal-districts-athens",
            "neighbourhoods-athens",
            "env-stations-registry",
            "env-all-stations",
        )
    }

    def fake_call(action: str, ttl: int = 600, **params) -> dict:
        if action == "package_show":
            slug = params["id"]
            if slug not in datasets:
                raise ckan.Unavailable(f"unknown fixture slug {slug}")
            return {
                "result": {"resources": [{"id": f"res-{slug}", "format": "CSV", "datastore_active": True}]},
                "source": "live",
                "at": "2026-11-21T12:00:00+00:00",
            }
        if action == "datastore_search":
            rid = params["resource_id"]
            slug = rid.removeprefix("res-")
            if slug not in datasets:
                raise ckan.Unavailable(f"unknown fixture resource {rid}")
            recs = list(datasets[slug]["records"])
            filters = params.get("filters") or {}
            if filters:
                recs = [r for r in recs if all(str(r.get(k)) == str(v) for k, v in filters.items())]
            sort = params.get("sort")
            if sort:
                col, _, direction = sort.partition(" ")
                recs.sort(key=lambda r: str(r.get(col, "")), reverse=(direction.lower() == "desc"))
            limit = params.get("limit")
            if limit is not None:
                recs = recs[:limit]
            return {"result": {"records": recs}, "source": "live", "at": "2026-11-21T12:00:00+00:00"}
        raise AssertionError(f"unexpected CKAN action: {action}")

    def fake_fetch_url(url: str) -> dict:
        raise AssertionError(f"unexpected network fetch: {url}")

    monkeypatch.setattr(config, "CKAN_MODE", "live")
    monkeypatch.setattr(ckan, "_call", fake_call)
    monkeypatch.setattr(ckan, "_fetch_url", fake_fetch_url)


def test_wkt_polygon_parsed():
    # Checks that _geom() parses a WKT POLYGON string into a GeoJSON Polygon with matching rings.
    wkt = "POLYGON ((23.74 37.96, 23.75 37.96, 23.75 37.97, 23.74 37.96))"
    got = ckan._geom(wkt)
    assert got == {
        "type": "Polygon",
        "coordinates": [[[23.74, 37.96], [23.75, 37.96], [23.75, 37.97], [23.74, 37.96]]],
    }


def test_wkt_multipolygon_parsed():
    # Checks that _geom() parses a 2-part WKT MULTIPOLYGON string into a GeoJSON MultiPolygon with 2 parts.
    wkt = (
        "MULTIPOLYGON (((23.74 37.96, 23.75 37.96, 23.75 37.97, 23.74 37.96)), "
        "((23.76 37.98, 23.77 37.98, 23.77 37.99, 23.76 37.98)))"
    )
    got = ckan._geom(wkt)
    assert got == {
        "type": "MultiPolygon",
        "coordinates": [
            [[[23.74, 37.96], [23.75, 37.96], [23.75, 37.97], [23.74, 37.96]]],
            [[[23.76, 37.98], [23.77, 37.98], [23.77, 37.99], [23.76, 37.98]]],
        ],
    }


def test_district_of_point_in_neighbourhood(monkeypatch):
    # Checks that a point inside a fixture neighbourhood resolves via municipal_district_id to the district name.
    _patch_ckan_fixtures(monkeypatch)
    assert ckan.district_of(*VARNAVA) == "2ο Δημοτικό Διαμέρισμα Αθήνας"


def test_district_of_point_outside(monkeypatch):
    # Checks that a point outside every fixture neighbourhood polygon returns None without error.
    _patch_ckan_fixtures(monkeypatch)
    assert ckan.district_of(38.05, 23.80) is None


def test_station_placed_at_neighbourhood_centre(monkeypatch):
    # Checks that a registry station without coordinates gets its neighbourhood's centre and location="neighbourhood_centre".
    _patch_ckan_fixtures(monkeypatch)
    stations, _ = ckan.env_stations()
    assert len(stations) >= 1
    st = next(s for s in stations if str(s["station_id"]) == "101")
    assert st["lat"] == pytest.approx(37.9712)
    assert st["lng"] == pytest.approx(23.7437)
    assert st["location"] == "neighbourhood_centre"


def test_air_latest_has_items(monkeypatch):
    # Checks that 2 stations and 4 measurement rows yield 2 items with newest rows and numeric temp_c and aqi.
    _patch_ckan_fixtures(monkeypatch)
    r = c.get("/api/city/air")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    by_id = {str(item["station_id"]): item for item in items}
    assert by_id["101"]["time"] == "2026-11-21T12:00:00"
    assert by_id["101"]["temp_c"] == 24.5 and isinstance(by_id["101"]["temp_c"], float)
    assert by_id["101"]["aqi"] == 3 and isinstance(by_id["101"]["aqi"], int)
    assert by_id["102"]["time"] == "2026-11-21T12:00:00"
    assert by_id["102"]["temp_c"] == 26.0 and isinstance(by_id["102"]["temp_c"], float)
    assert by_id["102"]["aqi"] == 4 and isinstance(by_id["102"]["aqi"], int)


def test_nearest_air_varnava(monkeypatch):
    # Checks that nearest_air() at Plateia Varnava picks the station placed 0.5 km away with distance_km ≈ 0.5.
    _patch_ckan_fixtures(monkeypatch)
    got = ckan.nearest_air(*VARNAVA)
    assert got is not None
    assert str(got["station_id"]) == "101"
    assert got["distance_km"] == pytest.approx(0.5, abs=0.05)


def test_station_without_neighbourhood_skipped(monkeypatch):
    # Checks that a station registry row with an unknown neighbourhood_id is skipped with no error.
    reg = _load_fixture("env-stations-registry")
    reg["records"].append(
        {
            "_id": 3,
            "station_id": "999",
            "name": "Άγνωστος Σταθμός",
            "address": "Άγνωστη Οδός",
            "neighbourhood_id": "999",
            "municipal_district_id": "9",
        }
    )
    _patch_ckan_fixtures(monkeypatch, overrides={"env-stations-registry": reg})
    r = c.get("/api/city/air")
    assert r.status_code == 200
    items = r.json()["items"]
    assert "999" not in {str(item["station_id"]) for item in items}
