"""B15: GET /api/map/resolved, the «Διορθώθηκαν κοντά σου» layer. Offline, TestClient only."""
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, sb  # noqa: E402
from app.sandbox import SandboxError  # noqa: E402

c = TestClient(app)
URL = "/api/map/resolved"
SYNTAGMA = (37.9755, 23.7348)
KEYS = {"id", "category", "label_el", "resolved_at", "hours_to_resolve", "district_name"}


def _req(rid="R-1", lat=37.975512, lng=23.734871, created="2026-11-20T10:00:00Z",
         resolved="2026-11-21T16:30:00Z", updated=None, **extra):
    """A sandbox request dict as list_requests returns it; `resolved=None` means no resolved history entry."""
    history = [{"status": "submitted", "at": created, "note": "x"}]
    if resolved:
        history.append({"status": "resolved", "at": resolved, "note": "done"})
    r = {"id": rid, "category": "pothole", "status": "resolved", "lat": lat, "lng": lng,
         "district": "Δήμος Αθηναίων", "created_at": created, "updated_at": updated or resolved or created,
         "history": history}
    r.update(extra)
    return r


def _patch(monkeypatch, items):
    monkeypatch.setattr(sb, "list_requests", lambda **kw: {"items": items})


def _mock_request(resolve):
    """Create a request in the mock sandbox at Σύνταγμα; PATCH it to resolved when asked."""
    r = sb.create_request("pothole", "Λακκούβα", "Σύνταγμα", "d", lat=SYNTAGMA[0], lng=SYNTAGMA[1])
    if resolve:
        sb.update_request(r["id"], status="resolved")
    return r["id"]


def test_resolved_lists_resolved_request(monkeypatch):
    # A request PATCHed to resolved in the mock sandbox shows up with its id, category, label and resolved_at.
    monkeypatch.delenv("STOA_TODAY", raising=False)
    c.post("/api/admin/reset")
    rid = _mock_request(True)
    feats = c.get(URL).json()["features"]
    assert len(feats) == 1
    p = feats[0]["properties"]
    assert p["id"] == rid and p["category"] and p["label_el"] and p["resolved_at"]


def test_resolved_excludes_open_requests(monkeypatch):
    # Only the resolved request appears; the submitted one does not.
    monkeypatch.delenv("STOA_TODAY", raising=False)
    c.post("/api/admin/reset")
    _mock_request(False)
    done = _mock_request(True)
    ids = [f["properties"]["id"] for f in c.get(URL).json()["features"]]
    assert ids == [done]


def test_resolved_hours_to_resolve(monkeypatch):
    # 2026-11-20T10:00Z to 2026-11-21T16:30Z = 30.5 h, and the median of one value is that value.
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    _patch(monkeypatch, [_req()])
    j = c.get(URL).json()
    assert j["features"][0]["properties"]["hours_to_resolve"] == 30.5
    assert j["summary"]["median_hours_to_resolve"] == 30.5


def test_resolved_falls_back_to_updated_at(monkeypatch):
    # No resolved history entry: resolved_at is the request's updated_at.
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    _patch(monkeypatch, [_req(resolved=None, updated="2026-11-21T08:00:00Z")])
    p = c.get(URL).json()["features"][0]["properties"]
    assert p["resolved_at"] == "2026-11-21T08:00:00Z"


def test_resolved_days_window(monkeypatch):
    # Today 2026-11-21, days=30: the one resolved on 11-19 stays, the one from 09-01 is dropped.
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    _patch(monkeypatch, [_req("new", created="2026-11-18T10:00:00Z", resolved="2026-11-19T10:00:00Z"),
                         _req("old", created="2026-08-31T10:00:00Z", resolved="2026-09-01T10:00:00Z")])
    ids = [f["properties"]["id"] for f in c.get(URL + "?days=30").json()["features"]]
    assert ids == ["new"]


def test_resolved_days_out_of_range_422(monkeypatch):
    # days must be 1-365.
    _patch(monkeypatch, [])
    assert c.get(URL + "?days=0").status_code == 422
    assert c.get(URL + "?days=400").status_code == 422


def test_resolved_no_personal_fields(monkeypatch):
    # Properties are exactly the six allowed keys, even if the request carries personal fields.
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    _patch(monkeypatch, [_req(title="Λακκούβα", description="κάτω από το σπίτι μου", address="Αιόλου 5",
                              note="τηλ 6900000000", created_by_you=True, photo_url="/photos/x.jpg")])
    f = c.get(URL).json()["features"][0]
    assert set(f["properties"]) == KEYS


def test_resolved_coordinates_rounded(monkeypatch):
    # SPEC privacy: ~10 m, 4 decimals, [lng, lat].
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    _patch(monkeypatch, [_req(lat=37.975512, lng=23.734871)])
    assert c.get(URL).json()["features"][0]["geometry"]["coordinates"] == [23.7349, 37.9755]


def test_resolved_bad_bbox_422(monkeypatch):
    # A bbox that is not four numbers is rejected.
    _patch(monkeypatch, [])
    assert c.get(URL + "?bbox=a,b,c,d").status_code == 422


def test_resolved_sandbox_error_503(monkeypatch):
    # A failing City sandbox answers 503, not a made-up empty layer.
    def boom(**kw):
        raise SandboxError("down")

    monkeypatch.setattr(sb, "list_requests", boom)
    assert c.get(URL).status_code == 503


def test_resolved_median_none_when_empty(monkeypatch):
    # No resolved requests: count 0 and median None (never 0).
    _patch(monkeypatch, [])
    r = c.get(URL)
    assert r.status_code == 200
    assert r.json()["summary"] == {"count": 0, "median_hours_to_resolve": None}
