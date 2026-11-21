"""Tests for T2: Points wallet, earn side."""
import io
import json
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import ckan, main  # noqa: E402
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


def test_approve_twice_pays_once():
    # Approving the same report twice must insert only one +10 ledger row for the reporter.
    client = TestClient(app)
    client.post("/api/admin/reset")
    rid = _create_report(client)

    assert client.post(f"/api/reports/{rid}/approve").status_code == 200
    assert client.post(f"/api/reports/{rid}/approve").status_code == 200

    me = client.get("/api/points/me").json()
    assert me["balance"] == 10
    assert len(me["entries"]) == 1
    assert me["entries"][0]["points"] == 10


def test_balance_is_ledger_sum():
    # Account balance equals the sum of all earned ledger entries for that account.
    client = TestClient(app)
    client.post("/api/admin/reset")
    rid1 = _create_report(client, lat=37.96603, lng=23.74212, note="σπασμένες πλάκες πεζοδρομίου")
    rid2 = _create_report(client, lat=37.9689, lng=23.7476, note="λακκούβα")

    assert client.post(f"/api/reports/{rid1}/approve").status_code == 200  # +10
    assert client.post(f"/api/reports/{rid2}/approve").status_code == 200  # +10
    assert client.post(f"/api/reports/{rid1}/dossier").status_code == 200  # +30

    me = client.get("/api/points/me").json()
    assert len(me["entries"]) == 3
    assert me["balance"] == sum(e["points"] for e in me["entries"]) == 50


def test_daily_cap_three_reports():
    # Daily cap of 3 approved reports per account caps 4 same-day approvals at 30 points.
    client = TestClient(app)
    client.post("/api/admin/reset")
    rids = [
        _create_report(client, lat=37.965 + i * 0.002, lng=23.743, note=f"πρόβλημα {i}")
        for i in range(4)
    ]
    for rid in rids:
        assert client.post(f"/api/reports/{rid}/approve").status_code == 200

    me = client.get("/api/points/me").json()
    assert me["balance"] == 30


def test_dossier_bonus_30():
    # Opening a Stoa dossier credits +30 to the original reporter, not to the engineer calling dossier.
    TestClient(app).post("/api/admin/reset")
    reporter = TestClient(app)
    operator = TestClient(app)

    rid = _create_report(reporter, lat=37.96603, lng=23.74212, note="σπασμένες πλάκες πεζοδρομίου")
    res = operator.post(f"/api/reports/{rid}/dossier")
    assert res.status_code == 200

    rep_me = reporter.get("/api/points/me").json()
    op_me = operator.get("/api/points/me").json()
    assert rep_me["balance"] == 30
    assert len(rep_me["entries"]) == 1
    assert rep_me["entries"][0]["points"] == 30
    assert op_me["balance"] == 0


def test_token_never_sent_to_sandbox(monkeypatch):
    # Creating a report with an ao_token cookie never passes the token into the sandbox client or its stored requests.
    client = TestClient(app)
    client.post("/api/admin/reset")

    me_res = client.get("/api/points/me")
    assert me_res.status_code == 200
    token = me_res.cookies.get("ao_token")
    assert token

    calls = []
    orig_create = main.sb.create_request

    def spy_create(*args, **kwargs):
        calls.append((args, kwargs))
        return orig_create(*args, **kwargs)

    monkeypatch.setattr(main.sb, "create_request", spy_create)

    _create_report(client)
    assert len(calls) == 1
    assert token not in json.dumps(calls, ensure_ascii=False)
    assert token not in json.dumps(main.sb._m.requests, ensure_ascii=False)


def test_points_me_without_cookie():
    # Calling GET /api/points/me without a cookie sets an HttpOnly ao_token cookie and returns 0 / Γείτονας.
    TestClient(app).post("/api/admin/reset")
    fresh = TestClient(app)
    res = fresh.get("/api/points/me")
    assert res.status_code == 200

    token = res.cookies.get("ao_token")
    assert token
    assert "httponly" in res.headers.get("set-cookie", "").lower()

    body = res.json()
    assert body["balance"] == 0
    assert body["tier"] == "Γείτονας"
    assert body["entries"] == []


def test_districts_totals(monkeypatch):
    # GET /api/points/districts aggregates totals per district against a shared target with no account ids.
    monkeypatch.setattr(
        ckan,
        "district_of",
        lambda lat, lng: "1η Δημοτική Κοινότητα" if lat and lat >= 37.975 else "7η Δημοτική Κοινότητα",
    )
    client = TestClient(app)
    client.post("/api/admin/reset")
    token = client.get("/api/points/me").cookies.get("ao_token")
    assert token

    rid1 = _create_report(client, lat=37.9667, lng=23.7437, note="ράμπα 1")
    rid2 = _create_report(client, lat=37.9687, lng=23.7437, note="ράμπα 2")
    rid3 = _create_report(client, lat=37.9800, lng=23.7300, note="ράμπα 3")
    for rid in (rid1, rid2, rid3):
        assert client.post(f"/api/reports/{rid}/approve").status_code == 200

    res = client.get("/api/points/districts")
    assert res.status_code == 200
    data = res.json()
    by_district = {item["district"]: item["points"] for item in data["items"]}
    assert by_district["7η Δημοτική Κοινότητα"] == 20
    assert by_district["1η Δημοτική Κοινότητα"] == 10
    assert data["target"] > 0
    assert token not in res.text
    assert all("account" not in item for item in data["items"])
