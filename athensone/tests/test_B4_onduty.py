"""Tests for B4: On-duty pharmacies and hospitals (/api/map/health).

Expected adapter interface in app/onduty_src.py (implementer builds to match):
  - CACHE_DIR: Path for runtime caches (pharmacies-<date>.json, geocode.json, last.json);
    curated hospitals stay in data/onduty/hospitals.json (HOSPITALS_PATH).
  - clear_cache() -> None: clear in-memory caches.
  - fetch_pharmacies_page(date_str: str) -> str: HTTP fetch for ΦΣΑ on-duty list.
  - fetch_hospitals_announcement(date_str: str) -> str: HTTP fetch for Ministry announcement.
  - fetch_geocode(address: str) -> tuple[float, float] | None: HTTP geocoder returning (lat, lon).
  - parse_pharmacies(raw: str) -> list[dict]: rows with name, address, hours.
  - parse_hospital_announcement(raw: str) -> list[dict]: rows with name, specialties.
  - geocode(address: str) -> tuple[float, float] | None: cached geocode wrapper.
Fixtures saved by the implementer live under tests/fixtures/B4/ as
pharmacies.* and hospitals.* (any extension such as .html or .json).
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "B4"
CONTRACT_PROPS = {"kind", "name", "address", "phone", "hours", "specialties", "on_duty"}
ALLOWED_KINDS = {"φαρμακείο", "νοσοκομείο"}
ALLOWED_SOURCES = {"live", "cache", "snapshot"}


def _read_fixture(stem: str) -> str:
    matches = sorted(p for p in FIXTURES.glob(f"{stem}.*") if p.is_file())
    assert matches, f"Missing fixture {FIXTURES / (stem + '.*')}"
    return matches[0].read_text(encoding="utf-8")


@pytest.fixture
def onduty_env(monkeypatch, tmp_path):
    from app import onduty_src

    monkeypatch.setattr(onduty_src, "CACHE_DIR", tmp_path)
    onduty_src.clear_cache()
    yield onduty_src
    onduty_src.clear_cache()


def _patch_sources(monkeypatch, onduty_src, *, pharmacies_raw: str | None = None, hospitals_raw: str | None = None):
    p_raw = pharmacies_raw if pharmacies_raw is not None else _read_fixture("pharmacies")
    h_raw = hospitals_raw if hospitals_raw is not None else _read_fixture("hospitals")
    monkeypatch.setattr(onduty_src, "fetch_pharmacies_page", lambda date_str: p_raw)
    monkeypatch.setattr(onduty_src, "fetch_hospitals_announcement", lambda date_str: h_raw)
    monkeypatch.setattr(onduty_src, "fetch_geocode", lambda address: (37.9755, 23.7348))


def test_onduty_contract(monkeypatch, onduty_env):
    # Checks that GET /api/map/health returns a valid GeoJSON FeatureCollection with all SPEC contract fields.
    _patch_sources(monkeypatch, onduty_env)

    r = c.get("/api/map/health")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["source"] in ALLOWED_SOURCES
    assert isinstance(body.get("updated_at"), str) and body["updated_at"]
    datetime.fromisoformat(body["updated_at"].replace("Z", "+00:00"))

    features = body["features"]
    assert isinstance(features, list) and len(features) > 0
    kinds_seen = set()
    for feat in features:
        assert feat["type"] == "Feature"
        geom = feat["geometry"]
        assert geom["type"] == "Point"
        lon, lat = geom["coordinates"]
        assert 23.60 <= lon <= 23.90
        assert 37.85 <= lat <= 38.15
        props = feat["properties"]
        assert CONTRACT_PROPS.issubset(props.keys())
        assert props["kind"] in ALLOWED_KINDS
        kinds_seen.add(props["kind"])
        assert isinstance(props["name"], str) and props["name"].strip()
        assert isinstance(props["address"], str)
        assert props["phone"] is None or isinstance(props["phone"], str)
        assert props["hours"] is None or isinstance(props["hours"], str)
        assert isinstance(props["specialties"], list)
        assert props["on_duty"] in (True, False, None)

    assert kinds_seen == ALLOWED_KINDS


def test_api_health_unchanged():
    # Checks that GET /api/health still returns the existing server-status payload, not on-duty GeoJSON.
    r = c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["mock"], bool)
    assert "persona" in body and "vision" in body and "valhalla" in body
    assert "features" not in body


def test_pharmacy_parser_fixture(onduty_env):
    # Checks that parse_pharmacies extracts pharmacies with non-empty name, address, and hours from the saved page.
    raw = _read_fixture("pharmacies")
    items = onduty_env.parse_pharmacies(raw)
    assert isinstance(items, list) and len(items) >= 1
    for item in items:
        assert isinstance(item.get("name"), str) and item["name"].strip()
        assert isinstance(item.get("address"), str) and item["address"].strip()
        assert isinstance(item.get("hours"), str) and item["hours"].strip()


def test_hospital_announcement_parser_fixture(monkeypatch, onduty_env):
    # Checks that the saved announcement parser and matcher mark the announced hospitals on_duty=True with specialties.
    h_raw = _read_fixture("hospitals")
    parsed = onduty_env.parse_hospital_announcement(h_raw)
    assert isinstance(parsed, list) and len(parsed) >= 1
    for entry in parsed:
        assert isinstance(entry.get("name"), str) and entry["name"].strip()
        assert isinstance(entry.get("specialties"), list) and len(entry["specialties"]) >= 1

    _patch_sources(monkeypatch, onduty_env, pharmacies_raw=None, hospitals_raw=h_raw)
    r = c.get("/api/map/health")
    assert r.status_code == 200
    hospitals = [f["properties"] for f in r.json()["features"] if f["properties"]["kind"] == "νοσοκομείο"]
    assert len(hospitals) >= 1
    on_duty = [h for h in hospitals if h["on_duty"] is True]
    off_duty = [h for h in hospitals if h["on_duty"] is False]
    assert len(on_duty) >= 1
    assert all(isinstance(h["specialties"], list) and len(h["specialties"]) >= 1 for h in on_duty)
    assert all(h["specialties"] == [] for h in off_duty)


def test_geocode_cached(monkeypatch, onduty_env):
    # Checks that geocoding the same address twice calls the upstream geocoder only once.
    calls = 0

    def spy_geocode(address: str):
        nonlocal calls
        calls += 1
        return (37.9755, 23.7348)

    monkeypatch.setattr(onduty_env, "fetch_geocode", spy_geocode)
    first = onduty_env.geocode("Σταδίου 10, Αθήνα")
    second = onduty_env.geocode("Σταδίου 10, Αθήνα")
    assert first == (37.9755, 23.7348)
    assert second == first
    assert calls == 1


def test_source_down_on_duty_null(monkeypatch, onduty_env):
    # Checks that when the pharmacy source raises, cached pharmacies return with on_duty=None and the failed source is named.
    _patch_sources(monkeypatch, onduty_env)
    prime = c.get("/api/map/health", params={"date": "2026-11-21"})
    assert prime.status_code == 200
    assert any(f["properties"]["kind"] == "φαρμακείο" for f in prime.json()["features"])

    onduty_env.clear_cache()

    def boom(date_str: str):
        raise httpx.ConnectError("pharmacy upstream unreachable")

    monkeypatch.setattr(onduty_env, "fetch_pharmacies_page", boom)
    r = c.get("/api/map/health", params={"date": "2026-11-22"})
    assert r.status_code == 200
    body = r.json()
    pharmacies = [f["properties"] for f in body["features"] if f["properties"]["kind"] == "φαρμακείο"]
    assert len(pharmacies) >= 1
    assert all(p["on_duty"] is None for p in pharmacies)
    failed = body.get("failed_sources")
    assert isinstance(failed, list) and len(failed) >= 1
    assert any("pharmac" in s.lower() or "φαρμακ" in s.lower() or "fsa" in s.lower() for s in failed)


def test_date_param(monkeypatch, onduty_env):
    # Checks that ?date=2026-11-22 forwards "2026-11-22" to both upstream source fetchers.
    asked_pharm: list[str] = []
    asked_hosp: list[str] = []
    p_raw = _read_fixture("pharmacies")
    h_raw = _read_fixture("hospitals")

    def fake_pharm(date_str: str) -> str:
        asked_pharm.append(date_str)
        return p_raw

    def fake_hosp(date_str: str) -> str:
        asked_hosp.append(date_str)
        return h_raw

    monkeypatch.setattr(onduty_env, "fetch_pharmacies_page", fake_pharm)
    monkeypatch.setattr(onduty_env, "fetch_hospitals_announcement", fake_hosp)
    monkeypatch.setattr(onduty_env, "fetch_geocode", lambda address: (37.9755, 23.7348))

    r = c.get("/api/map/health", params={"date": "2026-11-22"})
    assert r.status_code == 200
    assert asked_pharm == ["2026-11-22"]
    assert asked_hosp == ["2026-11-22"]
