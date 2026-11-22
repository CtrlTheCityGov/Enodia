"""B15 fix round: findings of the B15 review (bad coordinates, negative hours, missing source label)."""
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, sb  # noqa: E402

c = TestClient(app)
URL = "/api/map/resolved"


def _req(rid, lat=37.9755, lng=23.7348, created="2026-11-20T10:00:00Z", resolved="2026-11-21T16:30:00Z"):
    return {"id": rid, "category": "pothole", "status": "resolved", "lat": lat, "lng": lng,
            "created_at": created, "updated_at": resolved,
            "history": [{"status": "submitted", "at": created}, {"status": "resolved", "at": resolved}]}


# Non-numeric or non-finite coordinates from the sandbox are skipped (was: unhandled ValueError, 500).
def test_resolved_bad_coordinates_skipped(monkeypatch):
    items = [_req("bad", lat="abc"), _req("nan", lat=float("nan")), _req("ok")]
    monkeypatch.setattr(sb, "list_requests", lambda **kw: {"items": items})
    r = c.get(URL, params={"days": 30})
    assert r.status_code == 200
    assert [f["id"] for f in r.json()["features"]] == ["ok"]


# resolved_at before created_at is inconsistent: hours unknown (None), not negative, and left out of the median.
def test_resolved_negative_hours_become_none(monkeypatch):
    items = [_req("neg", created="2026-11-21T10:00:00Z", resolved="2026-11-20T10:00:00Z"), _req("ok")]
    monkeypatch.setattr(sb, "list_requests", lambda **kw: {"items": items})
    body = c.get(URL, params={"days": 30}).json()
    hours = {f["id"]: f["properties"]["hours_to_resolve"] for f in body["features"]}
    assert hours == {"neg": None, "ok": 30.5}
    assert body["summary"]["median_hours_to_resolve"] == 30.5


# The answer says whether the City sandbox itself is the mock (A-39), so the UI can show «δοκιμαστικό».
def test_resolved_has_source_label(monkeypatch):
    monkeypatch.setattr(sb, "list_requests", lambda **kw: {"items": []})
    assert c.get(URL).json()["source"] == "mock"
    monkeypatch.setattr(sb, "mock", False)
    assert c.get(URL).json()["source"] == "sandbox"
