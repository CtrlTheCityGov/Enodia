"""Tests for B13: service guide from the sandbox registry (GET /api/map/services)."""
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import categories, main  # noqa: E402
from app.main import app  # noqa: E402
from app.sandbox import SandboxError  # noqa: E402

c = TestClient(app)
URL = "/api/map/services"


@pytest.fixture(autouse=True)
def _clean_state():
    c.post("/api/admin/reset")
    yield
    c.post("/api/admin/reset")


def _spy(monkeypatch, name, result=None, exc=None):
    """Replace main.sb.<name>; returns the list of recorded calls."""
    calls = []

    def fake(*a, **kw):
        calls.append((a, kw))
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(main.sb, name, fake)
    return calls


# A bulky_waste question gets the official bulky-waste service from the mock registry.
def test_services_bulky_waste_returns_official_service():
    r = c.get(URL, params={"category": "bulky_waste"})
    assert r.status_code == 200
    body = r.json()
    assert "ογκωδ" in body["service"]["title"].lower()
    assert isinstance(body["service"]["documents"], list)
    assert body["source"] == "mock"
    assert body["label_el"] == "Ογκώδη"


# QUERIES covers exactly the sandbox categories; only «other» has no query.
def test_services_every_category_has_query_except_other():
    from app import service_guide
    assert set(service_guide.QUERIES) == set(categories.SANDBOX)
    for key, value in service_guide.QUERIES.items():
        if key == "other":
            assert value is None
        else:
            assert isinstance(value, str) and value.strip()


# «other» has no registry query: null service and the registry is never asked.
def test_services_other_returns_null_service(monkeypatch):
    calls = _spy(monkeypatch, "services", {"items": []})
    r = c.get(URL, params={"category": "other"})
    assert r.status_code == 200
    assert r.json()["service"] is None
    assert calls == []


# A category outside the sandbox list is rejected.
def test_services_unknown_category_422():
    assert c.get(URL, params={"category": "spaceship"}).status_code == 422


# Registry finds nothing: service is null, not an error.
def test_services_no_match_returns_null(monkeypatch):
    _spy(monkeypatch, "services", {"items": []})
    r = c.get(URL, params={"category": "pothole"})
    assert r.status_code == 200
    assert r.json()["service"] is None


# A hit with score 0 is not a match; the detail call is never made.
def test_services_zero_score_ignored(monkeypatch):
    _spy(monkeypatch, "services", {"items": [{"id": "z", "title": "Z", "score": 0}]})
    detail = _spy(monkeypatch, "service", {"id": "z", "title": "Z"})
    r = c.get(URL, params={"category": "pothole"})
    assert r.status_code == 200
    assert r.json()["service"] is None
    assert detail == []


# A sparse registry record is filled with None / [] defaults.
def test_services_missing_fields_default(monkeypatch):
    _spy(monkeypatch, "services", {"items": [{"id": "x", "title": "T", "score": 1.0}]})
    _spy(monkeypatch, "service", {"id": "x", "title": "T"})
    r = c.get(URL, params={"category": "bulky_waste"})
    assert r.status_code == 200
    assert r.json()["service"] == {"id": "x", "title": "T", "documents": [], "cost_eur": None,
                                   "online_url": None, "where": None, "when": None, "faq": []}


# Sandbox down: 503 so api.js falls back to the mock file.
def test_services_sandbox_error_503(monkeypatch):
    _spy(monkeypatch, "services", exc=SandboxError("503 down"))
    assert c.get(URL, params={"category": "pothole"}).status_code == 503


# The existing POST /api/ask keeps returning the mock service for an unmatched query.
def test_ask_still_returns_mock_service():
    r = c.post("/api/ask", json={"text": "βεβαίωση μόνιμης κατοικίας"})
    assert r.status_code == 200
    assert r.json()["service"]["id"] == "svc-mock-1"
