"""Tests for T6: Fix confirmation points and reopen history."""
import io
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import ckan  # noqa: E402
from app.main import app  # noqa: E402


def _jpeg_bytes() -> bytes:
    img = Image.new("RGB", (320, 240), (90, 90, 120))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _create_and_resolve(client: TestClient, lat: float = 37.9678, lng: float = 23.7457) -> str:
    rep = client.post(
        "/api/report",
        files={"photo": ("x.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"lat": lat, "lng": lng, "note": "μηχανάκι πάνω στη ράμπα"},
    )
    assert rep.status_code == 200
    body = rep.json()
    assert body["duplicate_of"] is None
    rid = body["request"]["id"]
    res = client.post(f"/api/reports/{rid}/resolve")
    assert res.status_code == 200
    return rid


def test_confirm_true_by_reporter_pays_5():
    # Reporter confirming fixed=true with their own ao_token earns one +5 fix_confirmed row verified by system.
    reporter = TestClient(app)
    reporter.post("/api/admin/reset")
    rid = _create_and_resolve(reporter)

    r = reporter.post(f"/api/reports/{rid}/confirm", data={"fixed": "true"})
    assert r.status_code == 200

    me = reporter.get("/api/points/me").json()
    fix_rows = [e for e in me["entries"] if e["action"] == "fix_confirmed"]
    assert len(fix_rows) == 1
    assert fix_rows[0]["ref_id"] == rid
    assert fix_rows[0]["points"] == 5
    assert fix_rows[0]["verified_by"] == "system"
    assert me["balance"] == 5


def test_confirm_twice_pays_once():
    # Confirming fixed=true twice by the reporter still grants only one +5 fix_confirmed row.
    reporter = TestClient(app)
    reporter.post("/api/admin/reset")
    rid = _create_and_resolve(reporter)

    assert reporter.post(f"/api/reports/{rid}/confirm", data={"fixed": "true"}).status_code == 200
    assert reporter.post(f"/api/reports/{rid}/confirm", data={"fixed": "true"}).status_code == 200

    me = reporter.get("/api/points/me").json()
    fix_rows = [e for e in me["entries"] if e["action"] == "fix_confirmed"]
    assert len(fix_rows) == 1
    assert fix_rows[0]["points"] == 5
    assert me["balance"] == 5


def test_confirm_by_other_token_pays_nothing():
    # Another caller with a different ao_token confirming fixed=true grants no points to either caller or reporter.
    TestClient(app).post("/api/admin/reset")
    reporter = TestClient(app)
    other = TestClient(app)
    assert other.get("/api/points/me").cookies.get("ao_token")

    rid = _create_and_resolve(reporter)
    r = other.post(f"/api/reports/{rid}/confirm", data={"fixed": "true"})
    assert r.status_code == 200

    rep_me = reporter.get("/api/points/me").json()
    other_me = other.get("/api/points/me").json()
    assert [e for e in rep_me["entries"] if e["action"] == "fix_confirmed"] == []
    assert [e for e in other_me["entries"] if e["action"] == "fix_confirmed"] == []
    assert rep_me["balance"] == 0
    assert other_me["balance"] == 0


def test_confirm_false_pays_nothing():
    # Reporter confirming fixed=false reopens the report and earns no fix_confirmed points row.
    reporter = TestClient(app)
    reporter.post("/api/admin/reset")
    rid = _create_and_resolve(reporter)

    r = reporter.post(f"/api/reports/{rid}/confirm", data={"fixed": "false"})
    assert r.status_code == 200

    me = reporter.get("/api/points/me").json()
    assert [e for e in me["entries"] if e["action"] == "fix_confirmed"] == []
    assert me["balance"] == 0


def test_reopen_survives_re_resolve(monkeypatch):
    # Re-resolving a previously reopened report keeps the reopen in history so district reopen_rate stays 1.0.
    client = TestClient(app)
    client.post("/api/admin/reset")
    monkeypatch.setattr(ckan, "district_of", lambda lat, lng: "7η Δημοτική Κοινότητα")

    rid = _create_and_resolve(client)
    assert client.post(f"/api/reports/{rid}/confirm", data={"fixed": "false"}).status_code == 200
    assert client.post(f"/api/reports/{rid}/resolve").status_code == 200

    eq = client.get("/api/equity").json()["items"]
    assert len(eq) == 1
    assert eq[0]["district"] == "7η Δημοτική Κοινότητα"
    assert eq[0]["reopen_rate"] == 1.0
