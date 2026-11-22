"""C2 (Wave 3): transit enrichment + citizen → operator → citizen workflow fixes.

Fully offline: mock sandbox, OASA telematics monkeypatched (no network), TestClient only.
"""
import os
import re
import sys

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, transit_src  # noqa: E402
from app.main import app  # noqa: E402

HEX = re.compile(r"#[0-9a-fA-F]{6}")
# Syntagma square area; two points ~10 m apart (well inside the 50 m duplicate radius).
P1 = (37.97550, 23.73480)
P2 = (37.97559, 23.73480)
# A second, unrelated spot ~1 km away for the fix-confirmation flow.
P3 = (37.98380, 23.72750)


# ------------------------------------------------------------------ fixtures
@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("OPERATOR_KEY", raising=False)
    c = TestClient(app)
    assert c.post("/api/admin/reset").status_code == 200
    return c


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture()
def oasa(monkeypatch, tmp_path):
    """Patch OASA telematics: every route answers two buses near Syntagma; snapshot goes to tmp."""
    def fake_get(url, *args, **kwargs):
        params = kwargs.get("params") or {}
        if params.get("act") == "getStopArrivals":
            return _FakeResponse([])
        rc = str(params.get("p1") or "")
        return _FakeResponse([
            {"VEH_NO": f"{rc}1", "CS_DATE": "2026-11-21 20:38:04.000", "CS_LAT": "37.9755", "CS_LNG": "23.7348",
             "ROUTE_CODE": rc, "VEH_HEADING": "90"},
            {"VEH_NO": f"{rc}2", "CS_DATE": "2026-11-21 20:38:09.000", "CS_LAT": "37.9760", "CS_LNG": "23.7352",
             "ROUTE_CODE": rc},
        ])

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(transit_src, "LAST_PATH", tmp_path / "last.json")
    transit_src._bus_cache.clear()
    yield
    transit_src._bus_cache.clear()


def _map_report(c, lat, lng, category="damage", subtype="sidewalk", note="σπασμένες πλάκες"):
    data = {"category": category, "lon": lng, "lat": lat, "note": note}
    if subtype:
        data["subtype"] = subtype
    r = c.post("/api/map/reports", data=data)
    assert r.status_code == 200, r.text
    return r.json()


def _act(c, rid, **body):
    body.setdefault("actor", "Μηχ. Δοκιμή")
    r = c.post(f"/api/cases/{rid}/actions", json=body)
    assert r.status_code == 200, (body, r.text)
    return r.json()


def _resolve(c, rid):
    """Shortest audited path to RESOLVED: investigate → municipal repair (engineer, reason) → resolve."""
    _act(c, rid, action="start_investigation")
    _act(c, rid, action="decide_municipal_repair", role="engineer", reason="Αυτοψία: φθορά, αποκατάσταση από Δήμο")
    _act(c, rid, action="resolve")


# ------------------------------------------------------------------ transit
def test_transit_buses_are_enriched_with_id_route_name_and_mode(client, oasa):
    data = client.get("/api/map/transit").json()
    buses = data["buses"]["features"]
    assert buses, "every configured route answered two buses"
    names = {str(r["route_code"]): r["name"] for r in config.TRANSIT_ROUTES}
    for f in buses:
        p = f["properties"]
        assert p["id"] and p["id"] == p["vehicle_id"]
        assert p["mode"] in ("bus", "trolley")
        assert p["route_name"] == names.get(p["route_code"], "")
    trolley_lines = {f["properties"]["line"] for f in buses if f["properties"]["mode"] == "trolley"}
    assert trolley_lines <= {"2"}
    if any(str(r["line"]) == "2" for r in config.TRANSIT_ROUTES):
        assert trolley_lines == {"2"}


def test_transit_stations_have_line_lines_and_palette_color(client, oasa):
    stations = client.get("/api/map/transit").json()["stations"]["features"]
    assert stations
    for f in stations:
        p = f["properties"]
        assert isinstance(p["lines"], list)
        assert isinstance(p["line"], str)
        assert HEX.fullmatch(p["color"])
        if p["lines"]:
            assert p["line"] == p["lines"][0]
    m2 = [f for f in stations if transit_src.canonical_line(f["properties"]["line"]) == "M2"]
    assert m2 and all(f["properties"]["color"] == "#DC2626" for f in m2)


def test_transit_routes_catalog_lists_metro_suburban_and_bus_routes(client, oasa):
    routes = client.get("/api/map/transit").json()["routes"]
    assert set(routes) == {"metro", "suburban", "buses"}
    metro_refs = {transit_src.canonical_line(e["ref"]) for e in routes["metro"]}
    assert {"M1", "M2", "M3"} <= metro_refs
    assert routes["suburban"] and all(e["color"] == "#EAB308" for e in routes["suburban"])
    for e in routes["metro"] + routes["suburban"]:
        assert e["station_count"] >= 1 and len(e["bbox"]) == 4
    assert len(routes["buses"]) == len(config.TRANSIT_ROUTES)
    assert all(e["active_vehicles"] == 2 for e in routes["buses"])


def test_transit_static_is_parsed_once_per_mtime(client, oasa, monkeypatch):
    transit_src.load_static()  # warm the cache
    calls = []
    real_loads = transit_src.json.loads
    monkeypatch.setattr(transit_src.json, "loads", lambda s, *a, **k: calls.append(1) or real_loads(s, *a, **k))
    transit_src.load_static()
    transit_src.load_static()
    assert calls == []


# ------------------------------------------------------------------ workflow
def test_subtype_mismatch_near_duplicate_gets_its_own_case(client):
    a = _map_report(client, *P1, subtype="sidewalk")
    b = _map_report(client, *P2, subtype="pothole", note="λακκούβα δίπλα")
    assert a["city_request_id"] and b["city_request_id"]
    assert a["city_request_id"] != b["city_request_id"]
    assert b["linked_to_existing"] is False
    assert b["points_awarded"] == 0  # still a raw-category duplicate: no double points
    assert client.get(f"/api/cases/{b['city_request_id']}").status_code == 200
    ids = {i["id"] for i in client.get("/api/reports").json()["items"]}
    assert {a["city_request_id"], b["city_request_id"]} <= ids


def test_linked_duplicate_pin_shows_canonical_case_status(client):
    a = _map_report(client, *P1)
    b = _map_report(client, *P2, note="και εδώ σπασμένη πλάκα")
    assert b["linked_to_existing"] and b["city_request_id"] == a["city_request_id"]
    _resolve(client, a["city_request_id"])
    feats = client.get("/api/map/reports").json()["features"]
    status = {f["properties"]["id"]: f["properties"]["status"] for f in feats}
    assert status[a["tracking_id"]] == "resolved"
    assert status[b["tracking_id"]] == "resolved"


def test_map_reporter_earns_fix_confirmation_and_is_asked_only_once(client):
    rep = _map_report(client, *P3)
    rid, tid = rep["city_request_id"], rep["tracking_id"]
    _resolve(client, rid)

    before = client.get(f"/api/track/{tid}").json()
    assert before["can_confirm_fix"] is True and before["fix_confirmed"] is None

    r = client.post(f"/api/reports/{rid}/confirm", data={"fixed": "true"})
    assert r.status_code == 200

    me = client.get("/api/points/me").json()
    fix_rows = [e for e in me["entries"] if e["action"] == "fix_confirmed"]
    assert len(fix_rows) == 1 and fix_rows[0]["ref_id"] == rid and fix_rows[0]["points"] == 5

    after = client.get(f"/api/track/{tid}").json()
    assert after["can_confirm_fix"] is False
    assert after["fix_confirmed"] is True


def test_fix_confirmation_needs_the_reporters_token(client):
    rep = _map_report(client, *P3)
    rid = rep["city_request_id"]
    _resolve(client, rid)
    stranger = TestClient(app)  # fresh cookie jar = another anonymous citizen
    assert stranger.post(f"/api/reports/{rid}/confirm", data={"fixed": "true"}).status_code == 200
    me = stranger.get("/api/points/me").json()
    assert [e for e in me["entries"] if e["action"] == "fix_confirmed"] == []


def test_active_link_targets_skips_unlinked(client):
    from app import cases

    a = _map_report(client, *P1)
    b = _map_report(client, *P2, note="ίδια βλάβη")
    rid = a["city_request_id"]
    assert cases.active_link_targets().get(b["tracking_id"]) == rid
    r = client.post(f"/api/cases/{rid}/links/{b['tracking_id']}/unlink",
                    json={"actor": "Α", "reason": "Διαφορετική βλάβη"})
    assert r.status_code == 200
    assert b["tracking_id"] not in cases.active_link_targets()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
