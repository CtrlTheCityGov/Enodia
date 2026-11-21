"""Tests for T1: "Is it fixed?" confirmation loop."""
import io
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import ckan, store  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)


def _jpeg_with_gps(lat=37.9678, lng=23.7457):
    img = Image.new("RGB", (640, 480), (90, 90, 120))
    exif = Image.Exif()

    def dms(x):
        d = int(x)
        m = int((x - d) * 60)
        s = round(((x - d) * 60 - m) * 60, 2)
        return (d, m, s)

    exif[0x8825] = {1: "N", 2: dms(lat), 3: "E", 4: dms(lng)}
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def _create_and_resolve_report():
    rep = c.post(
        "/api/report",
        files={"photo": ("x.jpg", _jpeg_with_gps(), "image/jpeg")},
        data={"note": "μηχανάκι πάνω στη ράμπα"},
    )
    assert rep.status_code == 200
    rid = rep.json()["request"]["id"]
    res = c.post(f"/api/reports/{rid}/resolve")
    assert res.status_code == 200
    return rid


def test_resolve_asks_confirmation():
    # Check that resolving a report inserts a confirmation row with asked_at set and answered_at null.
    c.post("/api/admin/reset")
    rid = _create_and_resolve_report()
    conf = store.get_confirmation(rid)
    assert conf is not None
    assert conf["request_id"] == rid
    assert conf["asked_at"] is not None
    assert conf["answered_at"] is None


def test_confirm_false_reopens_report():
    # Check that confirming fixed=false reopens the report to in_progress with the citizen note.
    c.post("/api/admin/reset")
    rid = _create_and_resolve_report()
    r = c.post(f"/api/reports/{rid}/confirm", data={"fixed": "false"})
    assert r.status_code == 200
    st = c.get(f"/api/reports/{rid}").json()
    assert st["status"] == "in_progress"
    assert st["history"][-1]["note"] == "Ο πολίτης αναφέρει ότι δεν διορθώθηκε"


def test_confirm_false_hazard_back():
    # Check that confirming fixed=false puts the reopened accessibility blocker back into /api/hazards.
    c.post("/api/admin/reset")
    rid = _create_and_resolve_report()
    assert all(h["id"] != rid for h in c.get("/api/hazards").json()["items"])
    r = c.post(f"/api/reports/{rid}/confirm", data={"fixed": "false"})
    assert r.status_code == 200
    assert any(h["id"] == rid for h in c.get("/api/hazards").json()["items"])


def test_reopen_rate_in_equity(monkeypatch):
    # Check that reopening a report in a district sets that district's reopen_rate to 1.0 in /api/equity.
    c.post("/api/admin/reset")
    monkeypatch.setattr(ckan, "district_of", lambda lat, lng: "7η Δημοτική Κοινότητα")
    rid = _create_and_resolve_report()
    r = c.post(f"/api/reports/{rid}/confirm", data={"fixed": "false"})
    assert r.status_code == 200
    eq = c.get("/api/equity").json()["items"]
    assert len(eq) == 1
    assert eq[0]["district"] == "7η Δημοτική Κοινότητα"
    assert eq[0]["reopen_rate"] == 1.0


def test_confirm_true_keeps_resolved():
    # Check that confirming fixed=true keeps status resolved and keeps the hazard out of /api/hazards.
    c.post("/api/admin/reset")
    rid = _create_and_resolve_report()
    r = c.post(f"/api/reports/{rid}/confirm", data={"fixed": "true"})
    assert r.status_code == 200
    st = c.get(f"/api/reports/{rid}").json()
    assert st["status"] == "resolved"
    assert all(h["id"] != rid for h in c.get("/api/hazards").json()["items"])


def test_confirm_photo_blurred_no_exif():
    # Check that an optional photo uploaded on confirm goes through privacy processing and stores no EXIF.
    c.post("/api/admin/reset")
    rid = _create_and_resolve_report()
    r = c.post(
        f"/api/reports/{rid}/confirm",
        data={"fixed": "false"},
        files={"photo": ("confirm.jpg", _jpeg_with_gps(), "image/jpeg")},
    )
    assert r.status_code == 200
    conf = store.get_confirmation(rid)
    assert conf is not None and conf["photo"]
    stored = c.get("/photos/" + conf["photo"].rsplit("/", 1)[-1]).content
    exif = Image.open(io.BytesIO(stored)).getexif()
    assert 0x8825 not in exif and len(exif) == 0


def test_confirm_unknown_report_404():
    # Check that confirming an unknown report id returns 404.
    c.post("/api/admin/reset")
    r = c.post("/api/reports/REQ-UNKNOWN/confirm", data={"fixed": "false"})
    assert r.status_code == 404
