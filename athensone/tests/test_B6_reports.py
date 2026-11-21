"""Tests for B6: Map report flow (+), plate blur, rounding, points, and confirmations."""
import io
import json
import os
import time
from datetime import datetime, timezone

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import config, main  # noqa: E402
from app.main import app  # noqa: E402


def _jpeg_bytes() -> bytes:
    img = Image.new("RGB", (320, 240), (90, 90, 120))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _jpeg_with_gps(lat: float = 37.9678, lng: float = 23.7457) -> bytes:
    img = Image.new("RGB", (640, 480), (90, 90, 120))
    exif = Image.Exif()

    def dms(x: float) -> tuple[int, int, float]:
        d = int(x)
        m = int((x - d) * 60)
        s = round(((x - d) * 60 - m) * 60, 2)
        return (d, m, s)

    exif[0x8825] = {1: "N", 2: dms(lat), 3: "E", 4: dms(lng)}
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def _plate_jpeg() -> bytes:
    # Synthetic rear-of-vehicle plate image detected by OpenCV's bundled Russian plate cascade.
    img = np.full((300, 500, 3), (60, 70, 80), dtype=np.uint8)
    cv2.rectangle(img, (80, 70), (420, 230), (40, 45, 50), -1)
    cv2.rectangle(img, (140, 120), (360, 175), (240, 240, 240), -1)
    cv2.rectangle(img, (140, 120), (360, 175), (20, 20, 20), 2)
    cv2.putText(img, "A777AA 77", (152, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (15, 15, 15), 3)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def test_map_report_contract():
    # Verify POST /api/map/reports with a photo returns the SPEC/card contract fields.
    client = TestClient(app)
    client.post("/api/admin/reset")
    before = set(config.PHOTO_DIR.iterdir())
    try:
        res = client.post(
            "/api/map/reports",
            data={"category": "incident", "lon": 23.7348, "lat": 37.9755, "note": "δοκιμή"},
            files={"photo": ("p.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["id"]
        assert isinstance(body["photo_url_blurred"], str) and "/photos/" in body["photo_url_blurred"]
        assert isinstance(body["points_awarded"], int)
        assert isinstance(body["blur"], dict)
        assert isinstance(body["blur"]["faces"], int) and body["blur"]["faces"] >= 0
        assert isinstance(body["blur"]["plates"], int) and body["blur"]["plates"] >= 0
    finally:
        for p in set(config.PHOTO_DIR.iterdir()) - before:
            p.unlink(missing_ok=True)


def test_map_report_without_photo():
    # Verify POST /api/map/reports works without a photo and returns photo_url_blurred as null.
    client = TestClient(app)
    client.post("/api/admin/reset")
    res = client.post(
        "/api/map/reports",
        data={"category": "congestion", "lon": 23.7348, "lat": 37.9755, "note": "κίνηση"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["id"]
    assert body["photo_url_blurred"] is None
    assert body["blur"]["faces"] == 0
    assert body["blur"]["plates"] == 0


def test_map_report_bad_category_422():
    # Verify an unknown report category is rejected with HTTP 422.
    client = TestClient(app)
    client.post("/api/admin/reset")
    res = client.post(
        "/api/map/reports",
        data={"category": "foo", "lon": 23.7348, "lat": 37.9755, "note": "invalid"},
    )
    assert res.status_code == 422


def test_photo_exif_stripped_original_not_on_disk():
    # Verify EXIF GPS is stripped and only the processed JPEG is written to data/photos/.
    client = TestClient(app)
    client.post("/api/admin/reset")
    before = set(config.PHOTO_DIR.iterdir())
    raw = _jpeg_with_gps()
    new_files = []
    try:
        res = client.post(
            "/api/map/reports",
            data={"category": "incident", "lon": 23.7348, "lat": 37.9755, "note": "φωτό"},
            files={"photo": ("gps.jpg", raw, "image/jpeg")},
        )
        assert res.status_code == 200
        new_files = [p for p in config.PHOTO_DIR.iterdir() if p not in before]
        assert len(new_files) == 1
        stored_bytes = new_files[0].read_bytes()
        assert stored_bytes != raw
        exif = Image.open(io.BytesIO(stored_bytes)).getexif()
        assert 0x8825 not in exif and len(exif) == 0
        url_name = res.json()["photo_url_blurred"].rsplit("/", 1)[-1]
        assert url_name == new_files[0].name
        assert client.get(f"/photos/{url_name}").status_code == 200
    finally:
        for p in new_files:
            p.unlink(missing_ok=True)


def test_plate_blur_counted():
    # Verify a licence plate in an uploaded photo is detected and counted in blur.plates.
    client = TestClient(app)
    client.post("/api/admin/reset")
    before = set(config.PHOTO_DIR.iterdir())
    try:
        res = client.post(
            "/api/map/reports",
            data={"category": "obstacle", "lon": 23.7348, "lat": 37.9755, "note": "παρκαρισμένο στη ράμπα"},
            files={"photo": ("plate.jpg", _plate_jpeg(), "image/jpeg")},
        )
        assert res.status_code == 200
        assert res.json()["blur"]["plates"] >= 1
    finally:
        for p in set(config.PHOTO_DIR.iterdir()) - before:
            p.unlink(missing_ok=True)


def test_public_coords_rounded():
    # Verify public GET /api/map/reports coordinates are rounded to at most 4 decimal places (~10 m).
    client = TestClient(app)
    client.post("/api/admin/reset")
    res = client.post(
        "/api/map/reports",
        data={"category": "incident", "lon": 23.7348123, "lat": 37.9755678, "note": "στρογγυλοποίηση"},
    )
    assert res.status_code == 200
    rid = res.json()["id"]

    fc = client.get("/api/map/reports").json()
    assert fc["type"] == "FeatureCollection"
    feat = next((f for f in fc["features"] if f["properties"]["id"] == rid), None)
    assert feat is not None
    lon, lat = feat["geometry"]["coordinates"]
    assert abs(lon - round(lon, 4)) < 1e-12
    assert abs(lat - round(lat, 4)) < 1e-12
    assert lon == 23.7348 and lat == 37.9756


def test_points_map_report_5():
    # Verify the first incident map report today awards 5 points to the caller.
    TestClient(app).post("/api/admin/reset")
    client = TestClient(app)
    res = client.post(
        "/api/map/reports",
        data={"category": "incident", "lon": 23.7348, "lat": 37.9755, "note": "πρώτο συμβάν"},
    )
    assert res.status_code == 200
    assert res.json()["points_awarded"] == 5
    assert client.get("/api/points/me").json()["balance"] == 5


def test_points_work_progress_photo_15():
    # Verify a work_progress report with photo and work_id awards 15 points.
    TestClient(app).post("/api/admin/reset")
    client = TestClient(app)
    before = set(config.PHOTO_DIR.iterdir())
    try:
        res = client.post(
            "/api/map/reports",
            data={
                "category": "work_progress",
                "lon": 23.7348,
                "lat": 37.9755,
                "note": "πρόοδος έργου",
                "work_id": "W-SEED-001",
            },
            files={"photo": ("work.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert res.status_code == 200
        assert res.json()["points_awarded"] == 15
        assert client.get("/api/points/me").json()["balance"] == 15
    finally:
        for p in set(config.PHOTO_DIR.iterdir()) - before:
            p.unlink(missing_ok=True)


def test_duplicate_no_points():
    # Verify a duplicate report of the same category within 50 m and 30 min awards 0 points.
    TestClient(app).post("/api/admin/reset")
    client = TestClient(app)
    r1 = client.post(
        "/api/map/reports",
        data={"category": "incident", "lon": 23.7348, "lat": 37.9755, "note": "πρώτο"},
    )
    assert r1.status_code == 200
    assert r1.json()["points_awarded"] == 5

    # ~20 m north of first report, submitted within 30 min
    r2 = client.post(
        "/api/map/reports",
        data={"category": "incident", "lon": 23.7348, "lat": 37.97568, "note": "δεύτερο"},
    )
    assert r2.status_code == 200
    assert r2.json()["points_awarded"] == 0
    assert client.get("/api/points/me").json()["balance"] == 5


def test_daily_cap_10():
    # Verify the daily cap of 10 map reports per account gives 0 points on the 11th report.
    TestClient(app).post("/api/admin/reset")
    client = TestClient(app)
    awarded = []
    for i in range(11):
        res = client.post(
            "/api/map/reports",
            data={
                "category": "incident",
                "lon": 23.735,
                "lat": round(37.960 + i * 0.002, 5),
                "note": f"συμβάν {i}",
            },
        )
        assert res.status_code == 200
        awarded.append(res.json()["points_awarded"])

    assert awarded[:10] == [5] * 10
    assert awarded[10] == 0
    assert client.get("/api/points/me").json()["balance"] == 50


def test_confirm_other_plus_2_once():
    # Verify confirming another user's report grants +2 once and self-confirming grants 0.
    TestClient(app).post("/api/admin/reset")
    client_a = TestClient(app)
    client_b = TestClient(app)

    r_a = client_a.post(
        "/api/map/reports",
        data={"category": "incident", "lon": 23.7348, "lat": 37.9755, "note": "συμβάν"},
    )
    assert r_a.status_code == 200
    rid = r_a.json()["id"]

    c1 = client_b.post(f"/api/map/reports/{rid}/confirm")
    assert c1.status_code == 200
    assert c1.json()["confirmations"] == 1
    assert client_b.get("/api/points/me").json()["balance"] == 2

    c2 = client_b.post(f"/api/map/reports/{rid}/confirm")
    assert c2.status_code == 200
    assert c2.json()["confirmations"] == 1
    assert client_b.get("/api/points/me").json()["balance"] == 2

    c_self = client_a.post(f"/api/map/reports/{rid}/confirm")
    assert c_self.status_code == 200
    assert c_self.json()["confirmations"] == 1
    assert client_a.get("/api/points/me").json()["balance"] == 5


def test_obstacle_creates_city_request_without_token(monkeypatch):
    # Verify an obstacle map report creates a sandbox City request without leaking the ao_token cookie.
    TestClient(app).post("/api/admin/reset")
    client = TestClient(app)
    token = client.get("/api/points/me").cookies.get("ao_token")
    assert token

    calls = []
    orig_create = main.sb.create_request

    def spy_create(*args, **kwargs):
        calls.append((args, kwargs))
        return orig_create(*args, **kwargs)

    monkeypatch.setattr(main.sb, "create_request", spy_create)

    res = client.post(
        "/api/map/reports",
        data={"category": "obstacle", "lon": 23.7348, "lat": 37.9755, "note": "κάδος στη ράμπα"},
    )
    assert res.status_code == 200
    assert len(calls) == 1
    assert token not in json.dumps(calls, ensure_ascii=False)
    assert token not in json.dumps(main.sb._m.requests, ensure_ascii=False)


def test_city_confirmed_bonus_20():
    # Verify operator approval of a map report's City request grants +20 city_confirmed to the reporter.
    TestClient(app).post("/api/admin/reset")
    reporter = TestClient(app)
    operator = TestClient(app)

    rep = reporter.post(
        "/api/map/reports",
        data={"category": "obstacle", "lon": 23.7348, "lat": 37.9755, "note": "εμπόδιο πεζοδρομίου"},
    )
    assert rep.status_code == 200
    assert rep.json()["points_awarded"] == 5

    items = operator.get("/api/reports").json()["items"]
    assert len(items) == 1
    city_rid = items[0]["id"]

    app_res = operator.post(f"/api/reports/{city_rid}/approve")
    assert app_res.status_code == 200

    rep_me = reporter.get("/api/points/me").json()
    assert rep_me["balance"] == 25
    assert any(e["action"] == "city_confirmed" and e["points"] == 20 for e in rep_me["entries"])
    assert operator.get("/api/points/me").json()["balance"] == 0


def test_get_reports_bbox_since():
    # Verify GET /api/map/reports filters correctly by bbox and since parameters.
    TestClient(app).post("/api/admin/reset")
    client = TestClient(app)

    r_before_in = client.post(
        "/api/map/reports",
        data={"category": "incident", "lon": 23.7348, "lat": 37.9755, "note": "πριν εντός"},
    ).json()
    time.sleep(1.1)
    since = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    time.sleep(1.1)
    r_after_out = client.post(
        "/api/map/reports",
        data={"category": "congestion", "lon": 23.7900, "lat": 38.0200, "note": "μετά εκτός"},
    ).json()
    r_after_in = client.post(
        "/api/map/reports",
        data={"category": "damage", "lon": 23.7350, "lat": 37.9760, "note": "μετά εντός"},
    ).json()

    bbox = "23.730,37.970,23.740,37.980"

    both = client.get("/api/map/reports", params={"bbox": bbox, "since": since})
    assert both.status_code == 200
    both_features = both.json()["features"]
    assert {f["properties"]["id"] for f in both_features} == {r_after_in["id"]}
    props = both_features[0]["properties"]
    assert {"id", "category", "created_at", "confirmations"}.issubset(props.keys())

    only_bbox = client.get("/api/map/reports", params={"bbox": bbox}).json()["features"]
    assert {f["properties"]["id"] for f in only_bbox} == {r_before_in["id"], r_after_in["id"]}

    only_since = client.get("/api/map/reports", params={"since": since}).json()["features"]
    assert {f["properties"]["id"] for f in only_since} == {r_after_out["id"], r_after_in["id"]}


def test_existing_report_route_unchanged():
    # Verify legacy POST /api/report retains its exact response keys after B6 changes.
    client = TestClient(app)
    client.post("/api/admin/reset")
    before = set(config.PHOTO_DIR.iterdir())
    try:
        res = client.post(
            "/api/report",
            files={"photo": ("x.jpg", _jpeg_with_gps(), "image/jpeg")},
            data={"note": "μηχανάκι πάνω στη ράμπα"},
        )
        assert res.status_code == 200
        assert set(res.json().keys()) == {
            "duplicate_of",
            "request",
            "ai",
            "photo_url",
            "faces_blurred",
            "gps_from_photo",
        }
    finally:
        for p in set(config.PHOTO_DIR.iterdir()) - before:
            p.unlink(missing_ok=True)
