"""Tests for T7: Points fixes (T2 follow-up)."""
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

from app import points, store  # noqa: E402
from app.main import app  # noqa: E402


def _jpeg_bytes() -> bytes:
    img = Image.new("RGB", (320, 240), (90, 90, 120))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _create_report(client: TestClient, lat: float = 37.9667, lng: float = 23.7437, note: str = "ράμπα") -> str:
    r = client.post(
        "/api/report",
        files={"photo": ("p.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"lat": lat, "lng": lng, "note": note},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["duplicate_of"] is None
    return body["request"]["id"]


def test_district_target_from_env(monkeypatch):
    # Checks that DISTRICT_TARGET=100 sets the /api/points/districts target to 100.
    monkeypatch.setenv("DISTRICT_TARGET", "100")
    client = TestClient(app)
    client.post("/api/admin/reset")

    res = client.get("/api/points/districts")
    assert res.status_code == 200
    assert res.json()["target"] == 100


def test_district_target_default_5000(monkeypatch):
    # Checks that /api/points/districts defaults target to 5000 when DISTRICT_TARGET is unset.
    monkeypatch.delenv("DISTRICT_TARGET", raising=False)
    client = TestClient(app)
    client.post("/api/admin/reset")

    res = client.get("/api/points/districts")
    assert res.status_code == 200
    assert res.json()["target"] == 5000


def test_dossier_on_rejected_report_pays_nothing():
    # Checks that opening a Stoa dossier on a rejected report with a works record grants no +30 points row.
    TestClient(app).post("/api/admin/reset")
    reporter = TestClient(app)
    operator = TestClient(app)

    rid = _create_report(reporter, lat=37.96603, lng=23.74212, note="σπασμένες πλάκες πεζοδρομίου")
    assert reporter.get(f"/api/reports/{rid}").json()["guarantee"] is not None

    rej = operator.post(f"/api/reports/{rid}/reject")
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"

    dos = operator.post(f"/api/reports/{rid}/dossier")
    assert dos.status_code == 200

    rep_me = reporter.get("/api/points/me").json()
    assert rep_me["balance"] == 0
    assert rep_me["entries"] == []
    assert operator.get("/api/points/me").json()["entries"] == []


def test_malformed_token_replaced():
    # Checks that a malformed ao_token=abc cookie is replaced with a valid token and never stored in the ledger.
    TestClient(app).post("/api/admin/reset")
    client = TestClient(app)
    client.cookies.set("ao_token", "abc")

    me_res = client.get("/api/points/me")
    assert me_res.status_code == 200
    new_tok = me_res.cookies.get("ao_token")
    assert "ao_token=" in me_res.headers.get("set-cookie", "")
    assert new_tok and new_tok != "abc"
    assert points.is_valid_token("abc") is False
    assert points.is_valid_token(new_tok) is True

    # Reset cookie to malformed value before creating + approving a report to verify no ledger row uses "abc".
    bad_client = TestClient(app)
    bad_client.cookies.set("ao_token", "abc")
    rep_res = bad_client.post(
        "/api/report",
        files={"photo": ("p.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"lat": 37.9667, "lng": 23.7437, "note": "ράμπα"},
    )
    assert rep_res.status_code == 200
    rep_tok = rep_res.cookies.get("ao_token")
    assert rep_tok and rep_tok != "abc"
    assert points.is_valid_token(rep_tok) is True

    rid = rep_res.json()["request"]["id"]
    assert bad_client.post(f"/api/reports/{rid}/approve").status_code == 200

    assert store.points_entries("abc") == []
    assert store.points_balance("abc") == 0
    assert store.points_balance(rep_tok) == 10
