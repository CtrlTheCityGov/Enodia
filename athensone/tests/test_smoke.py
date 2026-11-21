"""End-to-end smoke test of the demo loop in mock mode (no network needed).

    MOCK=1 VISION_PROVIDER=mock VALHALLA_URL=http://127.0.0.1:9 pytest -q
"""
import io
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")  # unreachable -> fallback route
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402
from app.geo import decode_polyline6  # noqa: E402

c = TestClient(app)


def jpeg_with_gps(lat=37.9678, lng=23.7457):
    img = Image.new("RGB", (640, 480), (90, 90, 120))
    exif = Image.Exif()
    def dms(x):
        d = int(x); m = int((x - d) * 60); s = round(((x - d) * 60 - m) * 60, 2)
        return (d, m, s)
    exif[0x8825] = {1: "N", 2: dms(lat), 3: "E", 4: dms(lng)}
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_full_loop():
    c.post("/api/admin/reset")
    assert c.get("/api/health").json()["mock"] is True

    # 1-2. ask with sources + cool places
    a = c.post("/api/ask", json={"text": "Πού να πάω να δροσιστώ;"}).json()
    assert a["sources"] and a["cool_places"]
    club = a["cool_places"][0]

    # 3. route (fallback because Valhalla is unreachable in tests)
    r1 = c.get("/api/route", params=dict(from_lat=37.9667, from_lng=23.7437, to_lat=club["lat"], to_lng=club["lng"])).json()
    assert r1["avoided_hazards"] == 0 and len(r1["geojson"]["coordinates"]) >= 2

    # 4. report with GPS taken from the photo; EXIF must be gone from the stored copy
    rep = c.post("/api/report", files={"photo": ("x.jpg", jpeg_with_gps(), "image/jpeg")},
                 data={"note": "μηχανάκι πάνω στη ράμπα"}).json()
    assert rep["gps_from_photo"] and rep["duplicate_of"] is None
    assert rep["ai"]["category"] == "sidewalk" and rep["ai"]["accessibility_blocker"]
    stored = c.get("/photos/" + rep["photo_url"].rsplit("/", 1)[1]).content
    assert 0x8825 not in Image.open(io.BytesIO(stored)).getexif()
    rid = rep["request"]["id"]

    # 5. duplicate within 50 m -> upvote, no new report; route now avoids the hazard
    dup = c.post("/api/report", files={"photo": ("y.jpg", jpeg_with_gps(37.96782, 23.74572), "image/jpeg")},
                 data={"note": "ράμπα"}).json()
    assert dup["duplicate_of"] == rid and dup["request"]["upvotes"] == 1
    r2 = c.get("/api/route", params=dict(from_lat=37.9667, from_lng=23.7437, to_lat=club["lat"], to_lng=club["lng"])).json()
    assert r2["avoided_hazards"] == 1

    # 6. operator approves (human in the loop)
    ops = c.get("/api/reports").json()["items"]
    assert ops[0]["local"]["needs_check"] is True  # mock confidence 0.6 < 0.85
    c.post(f"/api/reports/{rid}/approve", json={"note": "συνεργείο καθ' οδόν"})

    # 7. citizen sees the new status in the history
    st = c.get(f"/api/reports/{rid}").json()
    assert st["status"] == "in_progress" and st["history"][-1]["note"] == "συνεργείο καθ' οδόν"

    # resolving removes the hazard from routing
    c.post(f"/api/reports/{rid}/resolve")
    assert c.get("/api/hazards").json()["items"] == []


def test_polyline_decode():
    # precision-6 polyline of Plateia Varnava -> mock Friendship Club
    assert decode_polyline6("wuhlgAglehl@ohCwrF") == [[23.7437, 37.9667], [23.7476, 37.9689]]


def test_outside_athens_rejected():
    r = c.post("/api/report", files={"photo": ("z.jpg", jpeg_with_gps(), "image/jpeg")},
               data={"lat": 40.6, "lng": 22.9})
    assert r.status_code == 400


def test_stoa_guarantee_rules(monkeypatch):
    from app import works
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    by = {cd["id"]: cd["clock"] for cd in works.all_cards()}
    assert by["W-SEED-001"]["tier"] == "A" and by["W-SEED-001"]["until"] == "2026-12-15"
    assert by["W-SEED-002"]["tier"] == "B" and by["W-SEED-002"]["term_label"] == "INFERRED"  # 15-month default
    assert by["W-SEED-003"]["status"] == "ENDED"
    assert by["W-SEED-004"]["status"] == "UNKNOWN" and by["W-SEED-004"]["until"] is None  # no guessing
    assert works.add_months(__import__("datetime").date(2025, 11, 30), 15).isoformat() == "2027-02-28"
    rad = c.get("/api/works/radar", params={"days": 90}).json()
    assert [w["id"] for w in rad["items"]] == ["W-SEED-001", "W-SEED-002"] and rad["source"] == "SEED"
    assert len(c.get("/api/works/geojson").json()["features"]) == 5
    assert {l["id"] for l in c.get("/api/layers").json()["items"] if l["status"] == "live"} == {"reports", "places", "works", "env"}


def test_stoa_links_report_to_guarantee(monkeypatch):
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    rep = c.post("/api/report", files={"photo": ("s.jpg", jpeg_with_gps(), "image/jpeg")},
                 data={"lat": 37.96603, "lng": 23.74212, "note": "σπασμένες πλάκες πεζοδρομίου"}).json()
    rid = rep["request"]["id"]
    g = c.get(f"/api/reports/{rid}").json()["guarantee"]
    assert g["id"] == "W-SEED-001" and g["clock"]["status"] == "ACTIVE"
    d = c.post(f"/api/reports/{rid}/dossier").json()
    assert d["sent"] is False and "ΔΕΝ ΕΧΕΙ ΑΠΟΣΤΑΛΕΙ" in d["text"] and "SEED-ΑΔΑ-003" in d["text"]
    # unknown report -> error, never an empty dossier
    assert c.post("/api/reports/none/dossier").status_code in (404, 502)


NAV = dict(from_lat=37.9667, from_lng=23.7437, to_lat=37.9689, to_lng=23.7476)


def test_navigate_ranks_by_environment():
    c.post("/api/admin/reset")
    r = c.get("/api/navigate", params={**NAV, "shade": True, "air": True, "rest": True}).json()
    best, fast = r["candidates"][r["chosen"]], min(r["candidates"], key=lambda x: x["duration_min"])
    assert best is not fast and best["metrics"]["shade_pct"] > fast["metrics"]["shade_pct"]
    assert best["metrics"]["busy_pct"] < fast["metrics"]["busy_pct"] and "σκιά" in r["explanation_el"]
    assert r["env"]["source"] == "SEED"
    # preferences off -> fastest wins
    r0 = c.get("/api/navigate", params={**NAV, "shade": False, "air": False, "rest": False}).json()
    assert r0["candidates"][r0["chosen"]]["fastest"]
    # the destination is not counted as a rest stop
    assert all(x["metrics"]["rest_by_kind"].get("cool_place", 0) <= 1 for x in r["candidates"])


def _enc6(coords):
    out, plat, plng = [], 0, 0
    for lng, lat in coords:
        for v, prev in ((round(lat * 1e6), plat), (round(lng * 1e6), plng)):
            d = v - prev
            d = ~(d << 1) if d < 0 else d << 1
            while d >= 0x20:
                out.append(chr((0x20 | (d & 0x1f)) + 63)); d >>= 5
            out.append(chr(d + 63))
        plat, plng = round(lat * 1e6), round(lng * 1e6)
    return "".join(out)


def test_valhalla_alternates_and_profile(monkeypatch):
    from app import routing
    sent = []

    class R:
        def __init__(self, j): self._j = j
        def raise_for_status(self): pass
        def json(self): return self._j

    def trip(coords, km, s):
        return {"legs": [{"shape": _enc6(coords), "maneuvers": [{"instruction": "Ξεκινήστε"}]}],
                "summary": {"length": km, "time": s}}

    def fake_post(url, json, timeout):
        sent.append(json)
        if "exclude_polygons" in json:
            return R({"trip": trip([[23.7437, 37.9667], [23.7440, 37.9690], [23.7476, 37.9689]], 0.62, 560)})
        return R({"trip": trip([[23.7437, 37.9667], [23.7476, 37.9689]], 0.45, 400),
                  "alternates": [{"trip": trip([[23.7437, 37.9667], [23.7449, 37.9687], [23.7476, 37.9689]], 0.50, 450)}]})

    routing._cache.clear()
    monkeypatch.setattr(routing.httpx, "post", fake_post)
    r = c.get("/api/navigate", params={**NAV, "profile": "walker"}).json()
    assert len(r["candidates"]) == 3 and r["routing"] == "valhalla"
    assert sent[0]["alternates"] == 2 and sent[0]["costing_options"]["pedestrian"] == {"type": "wheelchair", "walking_speed": 3.0}
    assert sent[1]["exclude_polygons"]  # "away from traffic" candidate requested from SEED busy roads
    routing._cache.clear()


def test_ckan_city_data_and_open_standards(monkeypatch, tmp_path):
    """Fake AthensGov CKAN: column names are guessed from the schema, so use unusual ones on purpose."""
    import json as _json
    from app import ckan, config
    monkeypatch.setattr(config, "CKAN_MODE", "live")
    monkeypatch.setattr(ckan, "SNAP_DIR", tmp_path)
    ckan._mem.clear()
    square = {"type": "Polygon", "coordinates": [[[23.73, 37.96], [23.76, 37.96], [23.76, 37.98], [23.73, 37.98], [23.73, 37.96]]]}
    pk = lambda rid: {"resources": [{"id": rid, "format": "CSV", "datastore_active": True}]}
    data = {
        ("package_show", "municipal-districts-athens"): pk("r-dist"),
        ("package_show", "env-stations-registry"): pk("r-reg"),
        ("package_show", "env-all-stations"): pk("r-env"),
        ("package_show", "wifi-stations-registry"): pk("r-wifi"),
        ("datastore_search", "r-dist"): {"records": [{"_id": 1, "Name": "7η Δημοτική Κοινότητα", "geometry": _json.dumps(square)}]},
        ("datastore_search", "r-reg"): {"records": [{"station_id": 99, "station_name": "Σταθμός Παγκρατίου", "Latitude": "37.968", "Longitude": "23.745"}]},
        ("datastore_search", "r-env"): {"records": [
            {"station_id": 99, "measurement_time": "2026-11-21T12:00:00", "AQI": 4, "Temperature_C": 34.5, "PM2_5_ugm3": 31.0},
            {"station_id": 99, "measurement_time": "2026-11-21T11:00:00", "AQI": 2, "Temperature_C": 30.0, "PM2_5_ugm3": 9.0}]},
        ("datastore_search", "r-wifi"): {"records": [{"id": 5, "name": "Πλ. Βαρνάβα", "lat": 37.9667, "lon": 23.7437}]},
    }

    class R:
        def __init__(self, j): self._j = j
        def raise_for_status(self): pass
        def json(self): return self._j

    def fake_post(url, json, timeout, headers=None):
        action = url.rsplit("/", 1)[1]
        key = (action, json.get("id") or json.get("resource_id"))
        return R({"success": True, "result": data[key]})

    monkeypatch.setattr(ckan.httpx, "post", fake_post)
    air = c.get("/api/city/air").json()["items"]
    assert air[0]["aqi"] == 4 and air[0]["temp_c"] == 34.5 and air[0]["pm25"] == 31.0  # newest record wins
    assert c.get("/api/city/wifi").json()["items"][0]["name"] == "Πλ. Βαρνάβα"
    assert ckan.district_of(37.9667, 23.7437) == "7η Δημοτική Κοινότητα"
    assert ckan.district_of(38.01, 23.70) is None

    # navigation uses the City's station: AQI 4 -> explanation says so; 34.5 °C triggers heat mode
    r = c.get("/api/navigate", params={**NAV, "shade": True, "air": True, "rest": True}).json()
    assert "AQI 4/6" in r["explanation_el"] and r["prefs"]["heat_auto"] is True
    assert r["weather"]["source"].startswith("AthensGov")

    # a report gets its district; equity + Open311 + NGSI-LD + DCAT read it
    c.post("/api/admin/reset")
    c.post("/api/report", files={"photo": ("q.jpg", jpeg_with_gps(), "image/jpeg")},
           data={"lat": 37.9667, "lng": 23.7437, "note": "λακκούβα"})
    eq = c.get("/api/equity").json()["items"]
    assert eq[0]["district"] == "7η Δημοτική Κοινότητα" and eq[0]["reports"] == 1
    o = c.get("/open311/v2/requests.json").json()
    assert o[0]["status"] == "open" and o[0]["service_code"] == "pothole" and o[0]["lat"] == 37.9667
    assert c.get("/open311/v2/services.json").json()[0]["service_code"]
    e = c.get("/ngsi-ld/v1/entities", params={"type": "ServiceRequest"}).json()
    assert e[0]["type"] == "ServiceRequest" and e[0]["areaServed"]["value"] == "7η Δημοτική Κοινότητα"
    aq = c.get("/ngsi-ld/v1/entities", params={"type": "AirQualityObserved"}).json()
    assert aq[0]["airQualityIndex"]["value"] == 4
    assert len(c.get("/ngsi-ld/v1/entities", params={"type": "WorksRecord"}).json()) == 5
    assert len(c.get("/dcat/catalog.jsonld").json()["dcat:dataset"]) == 5

    # offline: snapshots on disk keep it working when the portal is down
    def down(*a, **k): raise ConnectionError("portal down")
    monkeypatch.setattr(ckan.httpx, "post", down)
    ckan._mem.clear()
    again = c.get("/api/city/air").json()
    assert again["items"][0]["aqi"] == 4 and again["source"].startswith("snapshot")
    ckan._mem.clear()
