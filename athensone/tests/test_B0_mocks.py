"""Tests for task B0: Contracts + first mocks (offline, reads web/mock/*)."""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from pathlib import Path

from app.geo import haversine_km

MOCK_DIR = Path(__file__).resolve().parent.parent / "web" / "mock"

MOCK_JSON_FILES = (
    "env.json",
    "access.geojson",
    "works.geojson",
    "transit.geojson",
    "health.geojson",
    "reports.geojson",
    "points.json",
    "stoa.json",
    "base.geojson",
)

GEOJSON_FILES = (
    "env.json",
    "access.geojson",
    "works.geojson",
    "health.geojson",
    "reports.geojson",
    "base.geojson",
)

ATHENS_LON_MIN, ATHENS_LON_MAX = 23.68, 23.80
ATHENS_LAT_MIN, ATHENS_LAT_MAX = 37.95, 38.03

SYNTAGMA = (23.7348, 37.9755)
MONASTIRAKI = (23.7257, 37.9761)


def _load(name: str):
    path = MOCK_DIR / name
    assert path.is_file(), f"Missing mock file: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _is_num(val) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _iter_coords(geom: dict):
    gtype = geom.get("type")
    if gtype == "GeometryCollection":
        for sub in geom.get("geometries", []):
            yield from _iter_coords(sub)
        return
    coords = geom.get("coordinates")

    def walk(node):
        if isinstance(node, list) and node and _is_num(node[0]):
            yield node[0], node[1]
        elif isinstance(node, list):
            for child in node:
                yield from walk(child)

    yield from walk(coords)


def _to_local_m(lon: float, lat: float, ref_lat: float = 37.9758) -> tuple[float, float]:
    k = 111_320.0
    return lon * k * math.cos(math.radians(ref_lat)), lat * k


def _point_seg_dist_m(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _segments_intersect(a1, a2, b1, b2) -> bool:
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    def on_seg(p, q, r):
        return (
            min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
            and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])
        )

    d1, d2 = cross(b1, b2, a1), cross(b1, b2, a2)
    d3, d4 = cross(a1, a2, b1), cross(a1, a2, b2)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True
    return (
        (d1 == 0 and on_seg(b1, a1, b2))
        or (d2 == 0 and on_seg(b1, a2, b2))
        or (d3 == 0 and on_seg(a1, b1, a2))
        or (d4 == 0 and on_seg(a1, b2, a2))
    )


def _seg_seg_dist_m(a1, a2, b1, b2) -> float:
    p1, p2 = _to_local_m(*a1), _to_local_m(*a2)
    q1, q2 = _to_local_m(*b1), _to_local_m(*b2)
    if _segments_intersect(p1, p2, q1, q2):
        return 0.0
    return min(
        _point_seg_dist_m(p1[0], p1[1], q1[0], q1[1], q2[0], q2[1]),
        _point_seg_dist_m(p2[0], p2[1], q1[0], q1[1], q2[0], q2[1]),
        _point_seg_dist_m(q1[0], q1[1], p1[0], p1[1], p2[0], p2[1]),
        _point_seg_dist_m(q2[0], q2[1], p1[0], p1[1], p2[0], p2[1]),
    )


# Checks that all 9 mock JSON/GeoJSON files exist under web/mock/ and parse as valid JSON.
def test_all_mock_files_exist_and_parse():
    for name in MOCK_JSON_FILES:
        data = _load(name)
        assert data is not None, f"{name} parsed to None"


# Checks that every mock carries an ISO snapshot date and non-empty note (stoa.json documented in README.md without a wrapper).
def test_every_mock_has_snapshot_and_note():
    for name in MOCK_JSON_FILES:
        data = _load(name)
        if name == "stoa.json":
            assert isinstance(data, list), "stoa.json must be a top-level array without a wrapper object"
            continue
        assert isinstance(data, dict), f"{name} must be a top-level JSON object"
        snap = data.get("snapshot")
        assert isinstance(snap, str), f"{name} missing string snapshot"
        date.fromisoformat(snap)
        note = data.get("note")
        assert isinstance(note, str) and note.strip(), f"{name} missing non-empty note"

    readme_path = MOCK_DIR / "README.md"
    assert readme_path.is_file(), "web/mock/README.md must exist for stoa.json snapshot and note"
    readme = readme_path.read_text(encoding="utf-8")
    assert "stoa.json" in readme, "README.md must document stoa.json"
    iso_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", readme)
    assert iso_dates, "README.md must include an ISO snapshot date for stoa.json"
    for d in iso_dates:
        date.fromisoformat(d)
    assert len(readme.strip()) > 30, "README.md must include a non-empty note"


# Checks that every coordinate in every GeoJSON FeatureCollection (including transit sub-collections) falls inside the Athens WGS84 bbox.
def test_geojson_is_wgs84_in_athens():
    collections: list[tuple[str, dict]] = [(name, _load(name)) for name in GEOJSON_FILES]
    transit = _load("transit.geojson")
    for sub in ("lines", "stations", "buses"):
        collections.append((f"transit.geojson#{sub}", transit[sub]))

    for label, fc in collections:
        assert fc.get("type") == "FeatureCollection", f"{label} is not a FeatureCollection"
        features = fc.get("features")
        assert isinstance(features, list) and features, f"{label} has no features"
        for i, feat in enumerate(features):
            geom = feat.get("geometry")
            assert isinstance(geom, dict), f"{label}[{i}] missing geometry"
            coords = list(_iter_coords(geom))
            assert coords, f"{label}[{i}] has empty coordinates"
            for lon, lat in coords:
                assert ATHENS_LON_MIN <= lon <= ATHENS_LON_MAX, f"{label}[{i}] lon {lon} out of bounds"
                assert ATHENS_LAT_MIN <= lat <= ATHENS_LAT_MAX, f"{label}[{i}] lat {lat} out of bounds"


# Checks that env.json contains >= 20 Point features, each with numeric temp_c, aqi, pm25 and an ISO updated_at timestamp.
def test_env_points_have_contract_fields():
    data = _load("env.json")
    features = data.get("features", [])
    points = [f for f in features if f.get("geometry", {}).get("type") == "Point"]
    assert len(points) >= 20
    for i, feat in enumerate(points):
        props = feat.get("properties", {})
        for field in ("temp_c", "aqi", "pm25"):
            assert _is_num(props.get(field)), f"env[{i}] missing numeric {field}"
        updated = props.get("updated_at")
        assert isinstance(updated, str), f"env[{i}] missing updated_at string"
        datetime.fromisoformat(updated.replace("Z", "+00:00"))


# Checks that env.json includes a hotter zone with max temp_c - min temp_c >= 2.
def test_env_has_hot_zone():
    data = _load("env.json")
    temps = [f["properties"]["temp_c"] for f in data["features"]]
    assert max(temps) - min(temps) >= 2.0


# Checks that access.geojson includes all four accessibility kinds and an OSM id on every feature.
def test_access_kinds_present():
    data = _load("access.geojson")
    expected_kinds = {"kerb_lowered", "wheelchair", "ramp", "tactile_paving"}
    seen_kinds = set()
    for i, feat in enumerate(data["features"]):
        props = feat.get("properties", {})
        kind = props.get("kind")
        assert kind in expected_kinds, f"access[{i}] unexpected kind {kind!r}"
        seen_kinds.add(kind)
        osm_id = props.get("osm_id") if "osm_id" in props else props.get("id", feat.get("id"))
        assert osm_id not in (None, "") and not isinstance(osm_id, bool), f"access[{i}] missing OSM id"
    assert seen_kinds == expected_kinds


# Checks that works.geojson has 10-15 works, all 12 contract fields, and status in the allowed set.
def test_works_count_and_fields():
    data = _load("works.geojson")
    features = data["features"]
    assert 10 <= len(features) <= 15
    contract_fields = {
        "id",
        "title",
        "status",
        "contractor",
        "amount_contract_eur",
        "amount_paid_eur",
        "ada",
        "adam",
        "start_date",
        "end_date",
        "guarantee_end",
        "reports_count",
    }
    allowed_status = {"planned", "in_progress", "completed"}
    for i, feat in enumerate(features):
        props = feat.get("properties", {})
        missing = contract_fields - set(props.keys())
        assert not missing, f"works[{i}] missing contract fields: {sorted(missing)}"
        assert props["status"] in allowed_status, f"works[{i}] invalid status {props['status']!r}"


# Checks that each work has amount_paid_eur <= amount_contract_eur and guarantee_end >= end_date when known.
def test_works_money_and_dates_consistent():
    data = _load("works.geojson")
    for i, feat in enumerate(data["features"]):
        props = feat["properties"]
        paid = props.get("amount_paid_eur")
        contract = props.get("amount_contract_eur")
        if paid is not None and contract is not None:
            assert _is_num(paid) and _is_num(contract), f"works[{i}] non-numeric money fields"
            assert paid <= contract, f"works[{i}] paid {paid} exceeds contract {contract}"
        g_end = props.get("guarantee_end")
        end_d = props.get("end_date")
        if g_end is not None and end_d is not None:
            assert date.fromisoformat(g_end) >= date.fromisoformat(end_d), (
                f"works[{i}] guarantee_end {g_end} before end_date {end_d}"
            )


# Checks that each work is either cited from diavgeia.gov.gr or marked as SEED with a SEED- ADA.
def test_works_ada_real_or_seed():
    data = _load("works.geojson")
    for i, feat in enumerate(data["features"]):
        props = feat["properties"]
        src = props.get("source_url") or ""
        is_real = isinstance(src, str) and src.startswith("https://diavgeia.gov.gr/")
        ada = props.get("ada")
        is_seed = isinstance(ada, str) and ada.startswith("SEED-") and props.get("seed") is True
        assert is_real or is_seed, f"works[{i}] neither Diavgeia-backed nor properly flagged SEED"


# Checks that at least one in_progress LineString work lies within 150 m of Syntagma -> Monastiraki.
def test_works_on_demo_route():
    data = _load("works.geojson")
    found = False
    for feat in data["features"]:
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        if props.get("status") != "in_progress" or geom.get("type") != "LineString":
            continue
        coords = geom.get("coordinates", [])
        for p1, p2 in zip(coords, coords[1:]):
            if _seg_seg_dist_m(p1, p2, SYNTAGMA, MONASTIRAKI) <= 150.0:
                found = True
                break
        if found:
            break
    assert found, "No in_progress LineString work within 150 m of Syntagma -> Monastiraki"


# Checks that transit.geojson contains non-empty lines, stations, and buses FeatureCollections.
def test_transit_has_three_collections():
    data = _load("transit.geojson")
    for key in ("lines", "stations", "buses"):
        assert key in data, f"transit.geojson missing {key}"
        fc = data[key]
        assert fc.get("type") == "FeatureCollection", f"transit.{key} must be a FeatureCollection"
        assert isinstance(fc.get("features"), list) and len(fc["features"]) > 0, (
            f"transit.{key} must be non-empty"
        )


# Checks that every transit line has a non-empty name and a #rrggbb hex color.
def test_transit_lines_have_colours():
    data = _load("transit.geojson")
    for i, feat in enumerate(data["lines"]["features"]):
        props = feat.get("properties", {})
        name = props.get("name")
        color = props.get("color")
        assert isinstance(name, str) and name.strip(), f"transit.lines[{i}] missing name"
        assert isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color), (
            f"transit.lines[{i}] invalid color {color!r}"
        )


# Checks that transit stations include Syntagma and Monastiraki and every station has bool/null elevator.
def test_transit_demo_stations():
    data = _load("transit.geojson")
    names = []
    for i, feat in enumerate(data["stations"]["features"]):
        props = feat.get("properties", {})
        assert "elevator" in props, f"transit.stations[{i}] missing elevator field"
        elev = props["elevator"]
        assert elev is None or isinstance(elev, bool), f"transit.stations[{i}] elevator must be bool or null"
        names.append(str(props.get("name", "")))
    assert any("Σύνταγμα" in n for n in names), "Missing Σύνταγμα station"
    assert any("Μοναστηράκι" in n for n in names), "Missing Μοναστηράκι station"


# Checks that health.geojson has both pharmacy and hospital kinds and all required fields on every feature.
def test_health_fields_and_kinds():
    data = _load("health.geojson")
    features = data["features"]
    kinds = set()
    required = {"kind", "name", "address", "phone", "hours", "specialties", "on_duty"}
    for i, feat in enumerate(features):
        props = feat.get("properties", {})
        missing = required - set(props.keys())
        assert not missing, f"health[{i}] missing fields: {sorted(missing)}"
        assert props["kind"] in {"φαρμακείο", "νοσοκομείο"}, f"health[{i}] invalid kind {props['kind']!r}"
        assert isinstance(props["specialties"], list), f"health[{i}] specialties must be a list"
        assert isinstance(props["on_duty"], bool), f"health[{i}] on_duty must be a bool"
        kinds.add(props["kind"])
    assert kinds == {"φαρμακείο", "νοσοκομείο"}


# Checks that at least one on-duty pharmacy in health.geojson is within 500 m of Syntagma.
def test_health_on_duty_near_syntagma():
    data = _load("health.geojson")
    syn_lon, syn_lat = SYNTAGMA
    near = []
    for feat in data["features"]:
        props = feat.get("properties", {})
        if props.get("kind") == "φαρμακείο" and props.get("on_duty") is True:
            lon, lat = feat["geometry"]["coordinates"][:2]
            if haversine_km(lat, lon, syn_lat, syn_lon) * 1000.0 <= 500.0:
                near.append(feat)
    assert near, "No on-duty pharmacy within 500 m of Syntagma"


# Checks that reports.geojson coordinates have <= 4 decimals and no personal/photo-like properties exist.
def test_reports_rounded_and_anonymous():
    data = _load("reports.geojson")
    forbidden = ("user", "token", "email", "photo")
    for i, feat in enumerate(data["features"]):
        for lon, lat in _iter_coords(feat["geometry"]):
            assert abs(lon - round(lon, 4)) < 1e-9, f"reports[{i}] lon {lon} has >4 decimals"
            assert abs(lat - round(lat, 4)) < 1e-9, f"reports[{i}] lat {lat} has >4 decimals"
        props = feat.get("properties", {})
        for key in props:
            low = key.lower()
            assert not any(bad in low for bad in forbidden), f"reports[{i}] forbidden property {key!r}"


# Checks that points.json matches the contract, progress_pct is 0..100, balance equals sum of deltas, and no user_id exists.
def test_points_contract_and_sum():
    data = _load("points.json")

    def _has_user_id(obj) -> bool:
        if isinstance(obj, dict):
            return any(k.lower() == "user_id" or _has_user_id(v) for k, v in obj.items())
        if isinstance(obj, list):
            return any(_has_user_id(v) for v in obj)
        return False

    assert not _has_user_id(data), "points.json must not contain user_id"
    assert {"balance", "district", "history", "rewards"}.issubset(data.keys())
    district = data["district"]
    assert {"name", "progress_pct", "goal"}.issubset(district.keys())
    assert _is_num(district["progress_pct"]) and 0 <= district["progress_pct"] <= 100
    history = data["history"]
    assert isinstance(history, list)
    for i, item in enumerate(history):
        assert {"ts", "delta", "reason"}.issubset(item.keys()), f"history[{i}] missing keys"
        assert _is_num(item["delta"]), f"history[{i}] delta must be numeric"
    assert data["balance"] == sum(item["delta"] for item in history)
    rewards = data["rewards"]
    assert isinstance(rewards, list)
    for i, reward in enumerate(rewards):
        assert {"id", "title", "cost"}.issubset(reward.keys()), f"rewards[{i}] missing keys"


# Checks that every citation label in stoa.json appears in its answer_md and has numeric lon and lat.
def test_stoa_citations_in_answer():
    data = _load("stoa.json")
    assert isinstance(data, list) and len(data) > 0
    for i, entry in enumerate(data):
        answer = entry.get("answer_md")
        assert isinstance(answer, str) and answer.strip(), f"stoa[{i}] missing answer_md"
        citations = entry.get("citations")
        assert isinstance(citations, list), f"stoa[{i}] citations must be a list"
        for j, cit in enumerate(citations):
            label = cit.get("label")
            assert isinstance(label, str) and label and label in answer, (
                f"stoa[{i}].citations[{j}] label {label!r} not found in answer_md"
            )
            assert _is_num(cit.get("lon")) and _is_num(cit.get("lat")), (
                f"stoa[{i}].citations[{j}] missing numeric lon/lat"
            )


# Checks that the Stoa demo pharmacy question's first citation is within 20 m of an on-duty pharmacy in health.geojson.
def test_stoa_pharmacy_demo_question():
    stoa = _load("stoa.json")
    health = _load("health.geojson")
    q = "Ποιο φαρμακείο εφημερεύει κοντά μου;"
    matches = [entry for entry in stoa if entry.get("question") == q]
    assert matches, f"stoa.json missing demo question: {q}"
    citations = matches[0].get("citations", [])
    assert citations, "Demo pharmacy entry must have at least one citation"
    first = citations[0]

    pharmacies = [
        f
        for f in health["features"]
        if f.get("properties", {}).get("kind") == "φαρμακείο"
        and f.get("properties", {}).get("on_duty") is True
    ]
    assert pharmacies, "health.geojson has no on-duty pharmacies"
    min_dist_m = min(
        haversine_km(
            first["lat"],
            first["lon"],
            f["geometry"]["coordinates"][1],
            f["geometry"]["coordinates"][0],
        )
        * 1000.0
        for f in pharmacies
    )
    assert min_dist_m <= 20.0, f"First citation is {min_dist_m:.1f} m from nearest on-duty pharmacy (> 20 m)"


# Checks that base.geojson contains at least 1 Polygon/MultiPolygon boundary and at least 3 LineString roads.
def test_base_has_boundary_and_roads():
    data = _load("base.geojson")
    features = data["features"]
    polys = [f for f in features if f.get("geometry", {}).get("type") in ("Polygon", "MultiPolygon")]
    lines = [f for f in features if f.get("geometry", {}).get("type") == "LineString"]
    assert len(polys) >= 1, "base.geojson needs at least 1 (Multi)Polygon boundary"
    assert len(lines) >= 3, "base.geojson needs at least 3 LineString roads"
