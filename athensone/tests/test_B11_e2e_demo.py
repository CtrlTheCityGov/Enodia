"""Tests for B11: Phase 4 integration & end-to-end demo rehearsal (/api/map/*)."""
from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import (  # noqa: E402
    ckan,
    config,
    env,
    envgrid_src,
    main,
    onduty_src,
    routing,
    transit_src,
    works,
)
from app.main import app  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SYNTAGMA = [23.7348, 37.9755]
MONASTIRAKI = [23.7257, 37.9761]


def _jpeg_with_gps(lat: float = 37.9660, lng: float = 23.7420) -> bytes:
    """Create a synthetic JPEG with GPS EXIF metadata."""
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


def _patch_open_meteo(monkeypatch) -> None:
    """Serve offline multi-coordinate Open-Meteo responses for the env grid."""
    def _build_payload(request: httpx.Request) -> list[dict] | dict:
        url = str(request.url)
        lats = [float(x) for x in request.url.params.get("latitude", "").split(",") if x.strip()]
        lons = [float(x) for x in request.url.params.get("longitude", "").split(",") if x.strip()]
        if "air-quality" in url:
            rows = [
                {
                    "latitude": lat,
                    "longitude": lon,
                    "timezone": "Europe/Athens",
                    "current": {
                        "time": "2026-11-21T12:00",
                        "european_aqi": 20 + (i % 4) * 5,
                        "pm2_5": round(8.0 + (i % 4) * 2.0, 2),
                    },
                }
                for i, (lat, lon) in enumerate(zip(lats, lons))
            ]
        elif "forecast" in url:
            rows = [
                {
                    "latitude": lat,
                    "longitude": lon,
                    "timezone": "Europe/Athens",
                    "current": {
                        "time": "2026-11-21T12:00",
                        "temperature_2m": round(19.0 + (i % 5) * 0.6, 2),
                    },
                }
                for i, (lat, lon) in enumerate(zip(lats, lons))
            ]
        else:
            raise AssertionError(f"Unexpected external URL in offline test: {url}")
        return rows[0] if len(rows) == 1 else rows

    def fake_handle(self, request: httpx.Request) -> httpx.Response:
        payload = _build_payload(request)
        return httpx.Response(
            200,
            content=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            request=request,
        )

    async def fake_async_handle(self, request: httpx.Request) -> httpx.Response:
        return fake_handle(self, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fake_handle)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_async_handle)


# Runs SPEC Demo script steps 2–6 sequentially on a single TestClient session fully offline.
def test_e2e_demo_backend_6_steps(monkeypatch, tmp_path):
    now = [3_100_000_000.0]
    monkeypatch.setattr(time, "time", lambda: now[0])
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    monkeypatch.setattr(config, "WEATHER", "on")
    monkeypatch.setattr(config, "CKAN_MODE", "off")
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    monkeypatch.setattr(ckan, "nearest_air", lambda lat, lng, max_km=1.5: None)

    monkeypatch.setattr(envgrid_src, "_snapshot_path", lambda: tmp_path / "envgrid_last.json")
    monkeypatch.setattr(transit_src, "LAST_PATH", tmp_path / "transit_last.json")
    monkeypatch.setattr(onduty_src, "CACHE_DIR", tmp_path / "onduty")

    envgrid_src._cache = None
    transit_src._bus_cache.clear()
    transit_src._arrivals_cache.clear()
    onduty_src.clear_cache()
    routing._cache.clear()
    works._cache.clear()
    env._cache.clear()
    main._weather.clear()
    ckan._mem.clear()

    _patch_open_meteo(monkeypatch)
    bus_fixture = json.loads((FIXTURES_DIR / "B3" / "oasa_bus_location_3922.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(transit_src, "fetch_bus_locations", lambda route_code: bus_fixture)
    monkeypatch.setattr(transit_src, "fetch_stop_arrivals", lambda stop_code: [])

    pharm_html = (FIXTURES_DIR / "B4" / "pharmacies.html").read_text(encoding="utf-8")
    hosp_txt = (FIXTURES_DIR / "B4" / "hospitals.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(onduty_src, "fetch_pharmacies_page", lambda date_str: pharm_html)
    monkeypatch.setattr(onduty_src, "fetch_hospitals_announcement", lambda date_str: hosp_txt)
    monkeypatch.setattr(onduty_src, "fetch_geocode", lambda address: (37.9755, 23.7348))

    client = TestClient(app)
    client.post("/api/admin/reset")
    before_photos = set(config.PHOTO_DIR.iterdir())

    try:
        # Step 2a: Env grid >= 20 points with temp_c, aqi, pm25, updated_at.
        env_res = client.get("/api/map/env")
        assert env_res.status_code == 200
        env_body = env_res.json()
        assert env_body["type"] == "FeatureCollection"
        assert len(env_body["features"]) >= 20
        for feat in env_body["features"]:
            props = feat["properties"]
            assert isinstance(props["temp_c"], (int, float))
            assert isinstance(props["aqi"], (int, float))
            assert isinstance(props["pm25"], (int, float))
            assert props["updated_at"]

        # Step 2b: Transit returns 3 non-empty FeatureCollections (lines, stations, buses).
        tr_res = client.get("/api/map/transit")
        assert tr_res.status_code == 200
        tr_body = tr_res.json()
        for key in ("lines", "stations", "buses"):
            assert tr_body[key]["type"] == "FeatureCollection"
            assert len(tr_body[key]["features"]) >= 1

        # Step 3: Works list + work_progress report with GPS photo awards 15 pts and strips EXIF.
        works_res = client.get("/api/map/works")
        assert works_res.status_code == 200
        works_feats = works_res.json()["features"]
        assert len(works_feats) >= 1
        work = works_feats[0]
        work_id = work["properties"]["id"]
        work_lon, work_lat = work["geometry"]["coordinates"][0]

        rep_res = client.post(
            "/api/map/reports",
            data={
                "category": "work_progress",
                "work_id": work_id,
                "lon": str(work_lon),
                "lat": str(work_lat),
                "note": "Πρόοδος εργασιών πεζοδρομίου",
            },
            files={"photo": ("work1.jpg", _jpeg_with_gps(work_lat, work_lon), "image/jpeg")},
        )
        assert rep_res.status_code == 200
        rep_body = rep_res.json()
        assert rep_body["points_awarded"] == 15
        assert isinstance(rep_body["photo_url_blurred"], str)
        assert rep_body["photo_url_blurred"].startswith("/photos/")

        stored = client.get(rep_body["photo_url_blurred"])
        assert stored.status_code == 200
        exif = Image.open(io.BytesIO(stored.content)).getexif()
        assert 0x8825 not in exif and len(exif) == 0

        # Step 4: Wheelchair and cool routes return valid LineString geometries.
        for profile in ("wheelchair", "cool"):
            rt_res = client.post(
                "/api/map/routing",
                json={"from": SYNTAGMA, "to": MONASTIRAKI, "profile": profile},
            )
            assert rt_res.status_code == 200
            rt_body = rt_res.json()
            assert rt_body["geometry"]["type"] == "LineString"
            assert len(rt_body["geometry"]["coordinates"]) >= 2
            assert rt_body["legs"] == [{"mode": "walk"}]
            assert rt_body["distance_m"] > 0
            assert rt_body["duration_s"] > 0

        # Step 5: Stoa pharmacy query near Syntagma returns a pharmacy citation in answer_md.
        stoa_res = client.post(
            "/api/map/stoa_ask",
            json={
                "question": "Ποιο φαρμακείο εφημερεύει κοντά μου;",
                "center": SYNTAGMA,
                "history": [],
            },
        )
        assert stoa_res.status_code == 200
        stoa_body = stoa_res.json()
        assert len(stoa_body["citations"]) >= 1
        first_cit = stoa_body["citations"][0]
        assert first_cit["kind"] == "pharmacy"
        assert isinstance(first_cit["lon"], (int, float))
        assert isinstance(first_cit["lat"], (int, float))
        assert first_cit["label"] in stoa_body["answer_md"]

        # Step 6: Points balance is 15; after reaching 30 points, redeeming a 30-pt reward works.
        pts_res = client.get("/api/map/points")
        assert pts_res.status_code == 200
        pts_body = pts_res.json()
        assert pts_body["balance"] == 15
        reward_30 = next((r for r in pts_body["rewards"] if r["cost"] == 30), None)
        assert reward_30 is not None

        # Submit a second work_progress photo > 50 m away to earn another +15 (30 total).
        rep2_res = client.post(
            "/api/map/reports",
            data={
                "category": "work_progress",
                "work_id": works_feats[1]["properties"]["id"] if len(works_feats) > 1 else work_id,
                "lon": str(SYNTAGMA[0]),
                "lat": str(SYNTAGMA[1]),
                "note": "Δεύτερη αναφορά προόδου",
            },
            files={"photo": ("work2.jpg", _jpeg_with_gps(SYNTAGMA[1], SYNTAGMA[0]), "image/jpeg")},
        )
        assert rep2_res.status_code == 200
        assert rep2_res.json()["points_awarded"] == 15

        pts_30 = client.get("/api/map/points")
        assert pts_30.status_code == 200
        assert pts_30.json()["balance"] == 30

        redeem_res = client.post("/api/map/points/redeem", json={"reward_id": reward_30["id"]})
        assert redeem_res.status_code == 200
        redeem_body = redeem_res.json()
        assert redeem_body["ok"] is True
        assert redeem_body["balance"] == 0
        assert isinstance(redeem_body["voucher_code"], str) and redeem_body["voucher_code"]

        pts_after = client.get("/api/map/points")
        assert pts_after.status_code == 200
        assert pts_after.json()["balance"] == 0
    finally:
        for p in set(config.PHOTO_DIR.iterdir()) - before_photos:
            p.unlink(missing_ok=True)
        client.post("/api/admin/reset")
        envgrid_src._cache = None
        transit_src._bus_cache.clear()
        transit_src._arrivals_cache.clear()
        onduty_src.clear_cache()
        routing._cache.clear()
        works._cache.clear()
        env._cache.clear()
