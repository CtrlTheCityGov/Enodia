"""Transit data adapter (B3): static metro/suburban rail + live OASA bus telematics.

Static lines and stations are built once into data/transit/static.json by scripts/fetch_transit.py
(from OpenStreetMap via Overpass; OASA/STASY static GTFS URLs returned 404/timeout on 2026-11-21).
Live bus positions and stop arrivals come from OASA Telematics (https://telematics.oasa.gr/api/)
with a 20 s in-memory TTL cache and disk snapshot fallback at data/transit/last.json.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from . import config

# Static metro/suburban GeoJSON bundle built by scripts/fetch_transit.py. Source: TASKS_B.md B3. Certainty: sure.
STATIC_PATH: Path = config.DATA_DIR / "transit" / "static.json"
# Last good OASA live bus snapshot on disk. Source: TASKS_B.md Common to B2-B5. Certainty: sure.
LAST_PATH: Path = config.DATA_DIR / "transit" / "last.json"

# Generic hackathon User-Agent matching scripts/fetch_env.py. Certainty: sure.
USER_AGENT = "AthensOne/0.1 (Apps4Athens hackathon prototype)"

# OASA CS_DATE is Athens local time: a bus answered CS_DATE 20:54:04 at ~20:56 EET (checked Sat 21 Nov 2026). Sure.
ATHENS_TZ = ZoneInfo("Europe/Athens")
# OASA CS_DATE formats observed in live responses ("2026-11-21 20:38:04.000", verified Sat 21 Nov 2026)
# and legacy SQL Server / telematics snapshots ("Nov 21 2026 08:15:00:000PM", used in test fixtures). Certainty: sure.
_CS_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%b %d %Y %I:%M:%S:%f%p",
    "%b %d %Y %I:%M:%S%p",
)

# In-memory TTL caches:
# _bus_cache: route_code -> (monotonic_ts, list[bus_feature])
# _arrivals_cache: stop_code -> (monotonic_ts, list[arrival_dict])
_bus_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_arrivals_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
# Parsed + normalised static.json, keyed by (path, mtime) so the 300 KB file is parsed once, not per request.
# Deliberately not named _cache/_bus_cache: tests clear those between runs, this one is self-invalidating.
_static_cache: dict[str, Any] = {}

BBox = tuple[float, float, float, float]

# Max parallel OASA getBusLocation calls in one get_buses() pass (8 default routes). Design default.
BUS_FETCH_WORKERS = 8

# Display colours for rail lines in station dots and the routes catalog, as agreed for the transit menu
# (Wave 1 card). Metro: STASY branding (approximate; static.json from OSM carries #007A33/#DA291C/#10069F).
# Suburban A1-A4 share one yellow so the menu reads "Προαστιακός" at a glance. Certainty: design default.
LINE_COLORS: dict[str, str] = {
    "M1": "#007A33",
    "M2": "#DC2626",
    "M3": "#0066B3",
    "SUBURBAN": "#EAB308",
}
# Neutral grey for unknown line codes. Design default.
DEFAULT_LINE_COLOR = "#6B7280"
# Greek capitals that look like Latin ones in OSM refs ("Μ1" U+039C, "Α1" U+0391). Sure.
_GREEK_TO_LATIN = str.maketrans({"Μ": "M", "Α": "A", "Π": "P"})


# ------------------------------------------------------------------ pure helpers
def _now_iso() -> str:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat()


def parse_bbox(raw: str | None) -> BBox | None:
    """Parse 'minLon,minLat,maxLon,maxLat' into a 4-float tuple, or None if empty."""
    if raw is None or not raw.strip():
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must have 4 comma-separated numbers: minLon,minLat,maxLon,maxLat")
    min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    if min_lon > max_lon or min_lat > max_lat:
        raise ValueError("bbox min must be <= max")
    return (min_lon, min_lat, max_lon, max_lat)


def bbox_intersects(a: BBox, b: BBox) -> bool:
    """Return True if two WGS84 bounding boxes overlap."""
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def point_in_bbox(lon: float, lat: float, bbox: BBox) -> bool:
    """Return True if (lon, lat) falls inside (min_lon, min_lat, max_lon, max_lat)."""
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def _geom_bbox(geom: dict[str, Any]) -> BBox | None:
    """Compute bounding box of a LineString or MultiLineString geometry."""
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    pts: list[list[float]] = []
    if gtype == "LineString":
        pts = coords
    elif gtype == "MultiLineString":
        for seg in coords:
            pts.extend(seg)
    if not pts:
        return None
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    return (min(lons), min(lats), max(lons), max(lats))


def line_intersects_bbox(feature: dict[str, Any], bbox: BBox) -> bool:
    """Return True if a line feature's bounding box intersects the requested bbox."""
    gb = _geom_bbox(feature.get("geometry") or {})
    return gb is not None and bbox_intersects(gb, bbox)


def parse_oasa_timestamp(raw: Any, fallback_iso: str) -> str:
    """Convert OASA CS_DATE strings to ISO-8601; fall back to fetched timestamp if unknown."""
    if not isinstance(raw, str) or not raw.strip():
        return fallback_iso
    text = " ".join(raw.strip().split())
    for fmt in _CS_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=ATHENS_TZ).isoformat()
        except ValueError:
            continue
    return fallback_iso


def canonical_line(ref: Any) -> str:
    """Map a rail line ref to Latin upper-case ('Μ1' -> 'M1', 'Α2' -> 'A2', 'Π1' -> 'P1'); '' if empty."""
    return str(ref or "").strip().translate(_GREEK_TO_LATIN).upper()


def line_color(ref: Any) -> str:
    """Display hex colour for a Metro/Suburban line ref (Greek or Latin letters)."""
    code = canonical_line(ref)
    if code in LINE_COLORS:
        return LINE_COLORS[code]
    raw = str(ref or "").strip().lower()
    if code in ("A1", "A2", "A3", "A4", "P1", "P2", "P3") or any(
        word in raw for word in ("suburban", "proastiakos", "προαστ")
    ):
        return LINE_COLORS["SUBURBAN"]
    return DEFAULT_LINE_COLOR


def _route_meta(route_code: str) -> dict[str, Any]:
    """Configured OASA route entry (line, Greek name, bbox) for a route_code, or {}."""
    for rt in config.TRANSIT_ROUTES:
        if str(rt.get("route_code")) == str(route_code):
            return rt
    return {}


def bus_mode(line: Any) -> str:
    """'trolley' for OASA line 2 (ΗΛΠΑΠ trolleybus 2 in config.TRANSIT_ROUTES), else 'bus'. Sure for line 2 only."""
    return "trolley" if str(line or "").strip() == "2" else "bus"


def enrich_bus_feature(feature: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """Return a copy of a bus feature with id, route_name and mode filled in (older snapshots lack them)."""
    props = dict(feature.get("properties") or {})
    rc = str(props.get("route_code") or "")
    veh = str(props.get("vehicle_id") or "")
    meta = _route_meta(rc)
    if not props.get("line"):
        props["line"] = str(meta.get("line") or rc)
    if not props.get("id"):
        # vehicle_id is the stable key the frontend interpolates on; fall back to a per-route index.
        props["id"] = veh or f"BUS-{rc}-{index}"
    if not props.get("route_name"):
        props["route_name"] = str(meta.get("name") or "")
    if not props.get("mode"):
        props["mode"] = bus_mode(props["line"])
    return {**feature, "properties": props}


def parse_bus_locations(payload: Any, route_code: str, line: str, fetched_at: str) -> list[dict[str, Any]]:
    """Parse an OASA getBusLocation JSON payload into GeoJSON Point features.

    OASA returns an empty string '' or null when no vehicle is active on a route; those become [].
    Bearing is set to float(VEH_HEADING) when provided and numeric, else None (never 0 or guessed).
    """
    if not isinstance(payload, list):
        return []
    route_name = str(_route_meta(route_code).get("name") or "")
    features: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            lat = float(row["CS_LAT"])
            lon = float(row["CS_LNG"])
        except (KeyError, TypeError, ValueError):
            continue
        raw_heading = row.get("VEH_HEADING")
        if raw_heading is None:
            raw_heading = row.get("bearing")
        bearing: float | None
        try:
            bearing = float(raw_heading) if raw_heading is not None and raw_heading != "" else None
        except (TypeError, ValueError):
            bearing = None
        rc = str(row.get("ROUTE_CODE") or route_code)
        veh = str(row.get("VEH_NO") or "")
        ts = parse_oasa_timestamp(row.get("CS_DATE"), fetched_at)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "id": veh or f"BUS-{rc}-{len(features)}",
                    "vehicle_id": veh,
                    "line": line,
                    "route_code": rc,
                    "route_name": route_name,
                    "mode": bus_mode(line),
                    "bearing": bearing,
                    "updated_at": ts,
                },
            }
        )
    return features


def parse_stop_arrivals(payload: Any) -> list[dict[str, Any]]:
    """Parse an OASA getStopArrivals JSON payload into wait-time dicts."""
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            wait_min = int(row["btime2"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append(
            {
                "route_code": str(row.get("route_code") or ""),
                "vehicle_id": str(row.get("veh_code") or ""),
                "wait_min": wait_min,
            }
        )
    return out


# ------------------------------------------------------------------ upstream HTTP (one function per call)
def fetch_bus_locations(route_code: str) -> Any:
    """Call OASA telematics getBusLocation for one route_code."""
    r = httpx.get(
        config.OASA_TELEMATICS_URL,
        params={"act": "getBusLocation", "p1": route_code},
        headers={"User-Agent": USER_AGENT},
        timeout=config.TRANSIT_HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def fetch_stop_arrivals(stop_code: str) -> Any:
    """Call OASA telematics getStopArrivals for one stop_code."""
    r = httpx.get(
        config.OASA_TELEMATICS_URL,
        params={"act": "getStopArrivals", "p1": stop_code},
        headers={"User-Agent": USER_AGENT},
        timeout=config.TRANSIT_HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------ disk snapshot & static loaders
def normalize_station(feature: dict[str, Any]) -> dict[str, Any]:
    """Copy of a station feature whose properties always carry lines (list), line (primary) and color."""
    props = dict(feature.get("properties") or {})
    raw_lines = props.get("lines")
    if isinstance(raw_lines, str):
        lines = [raw_lines] if raw_lines.strip() else []
    elif isinstance(raw_lines, list):
        lines = [str(x) for x in raw_lines if x not in (None, "")]
    else:
        lines = []
    primary = str(props.get("line") or (lines[0] if lines else "") or props.get("ref") or "")
    if primary and not lines:
        lines = [primary]
    props["lines"] = lines
    props["line"] = primary
    props["color"] = line_color(primary) if primary else str(props.get("color") or DEFAULT_LINE_COLOR)
    return {**feature, "properties": props}


def _rail_catalog(line_feats: list[dict[str, Any]], station_feats: list[dict[str, Any]]) -> dict[str, list]:
    """Metro and Suburban line entries (ref, name, color, station_count, bbox) for the transit menu."""
    counts: dict[str, int] = {}
    for st in station_feats:
        for ref in (st.get("properties") or {}).get("lines") or []:
            code = canonical_line(ref)
            counts[code] = counts.get(code, 0) + 1
    metro: list[dict[str, Any]] = []
    suburban: list[dict[str, Any]] = []
    for f in line_feats:
        p = f.get("properties") or {}
        ref = str(p.get("ref") or "")
        if not ref:
            continue
        gb = _geom_bbox(f.get("geometry") or {})
        entry = {
            "ref": ref,
            "name": str(p.get("name") or ref),
            "color": line_color(ref),
            "station_count": counts.get(canonical_line(ref), 0),
            "bbox": list(gb) if gb else None,
        }
        is_metro = p.get("mode") == "subway" or canonical_line(ref).startswith("M")
        (metro if is_metro else suburban).append(entry)
    metro.sort(key=lambda e: canonical_line(e["ref"]))
    suburban.sort(key=lambda e: canonical_line(e["ref"]))
    return {"metro": metro, "suburban": suburban}


def load_static() -> dict[str, Any]:
    """Load pre-built static metro/suburban lines and stations from STATIC_PATH (cached per path+mtime).

    Stations are normalised (line, lines, color). The returned dict also carries 'catalog' (metro/suburban
    line entries). Callers must treat the returned objects as read-only: they are shared between requests.
    """
    empty = {
        "lines": {"type": "FeatureCollection", "features": []},
        "stations": {"type": "FeatureCollection", "features": []},
        "catalog": {"metro": [], "suburban": []},
    }
    try:
        key = (str(STATIC_PATH), STATIC_PATH.stat().st_mtime)
    except OSError:
        return empty
    if _static_cache.get("key") == key:
        return _static_cache["data"]
    try:
        data = json.loads(STATIC_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    lines = data.get("lines") or empty["lines"]
    stations_in = (data.get("stations") or {}).get("features") or []
    stations = {"type": "FeatureCollection", "features": [normalize_station(f) for f in stations_in]}
    result = {
        "lines": lines,
        "stations": stations,
        "catalog": _rail_catalog(lines.get("features") or [], stations["features"]),
    }
    _static_cache["key"] = key
    _static_cache["data"] = result
    return result


def _read_snapshot() -> dict[str, Any] | None:
    if not LAST_PATH.exists():
        return None
    try:
        data = json.loads(LAST_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("by_route"), dict):
            return data
    except (OSError, ValueError):
        return None
    return None


def _write_snapshot(updated_by_route: dict[str, list[dict[str, Any]]], updated_at: str) -> None:
    existing = _read_snapshot() or {}
    merged = dict(existing.get("by_route") or {})
    merged.update(updated_by_route)
    payload = {"updated_at": updated_at, "by_route": merged}
    LAST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ public service functions
def _select_routes(bbox: BBox | None) -> list[dict[str, Any]]:
    """Return configured routes whose bounding box overlaps bbox (or all if bbox is None)."""
    routes = config.TRANSIT_ROUTES
    if bbox is None:
        return list(routes)
    # A route with no known bbox (env override with a new code) is always polled.
    return [r for r in routes if r.get("bbox") is None or bbox_intersects(r["bbox"], bbox)]


def _filter_bus_features(features: list[dict[str, Any]], bbox: BBox | None) -> list[dict[str, Any]]:
    if bbox is None:
        return list(features)
    return [
        f
        for f in features
        if point_in_bbox(f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1], bbox)
    ]


def get_buses(bbox: BBox | None = None) -> tuple[list[dict[str, Any]], str, str]:
    """Fetch live OASA bus positions for routes crossing bbox, with 20 s cache and snapshot fallback.

    Returns (bus_features, source, updated_at) where source is one of:
    'live', 'cache', 'snapshot', 'unavailable'.
    """
    routes = _select_routes(bbox)
    now_mono = time.monotonic()
    now_iso = _now_iso()

    collected: list[dict[str, Any]] = []
    fresh_by_route: dict[str, list[dict[str, Any]]] = {}
    any_live = False
    any_cache = False
    failed_codes: list[str] = []

    to_fetch: list[tuple[str, str]] = []
    for rt in routes:
        rc = str(rt["route_code"])
        line = str(rt.get("line") or rc)
        hit = _bus_cache.get(rc)
        if hit is not None and (now_mono - hit[0]) < config.TRANSIT_BUS_TTL_S:
            collected.extend(hit[1])
            any_cache = True
            continue
        to_fetch.append((rc, line))

    def _fetch_one(item: tuple[str, str]) -> tuple[str, list[dict[str, Any]] | None]:
        rc, line = item
        try:
            return rc, parse_bus_locations(fetch_bus_locations(rc), rc, line, now_iso)
        except (httpx.HTTPError, OSError, ValueError):
            return rc, None

    if to_fetch:
        # Uncached routes are fetched in parallel (I/O-bound httpx calls); results keep the route order.
        workers = max(1, min(BUS_FETCH_WORKERS, len(to_fetch)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_fetch_one, to_fetch))
        for rc, feats in results:
            if feats is None:
                failed_codes.append(rc)
                continue
            _bus_cache[rc] = (now_mono, feats)
            fresh_by_route[rc] = feats
            collected.extend(feats)
            any_live = True

    if any_live:
        try:
            _write_snapshot(fresh_by_route, now_iso)
        except OSError:
            pass
        return _filter_bus_features(collected, bbox), "live", now_iso

    if any_cache and not failed_codes:
        return _filter_bus_features(collected, bbox), "cache", now_iso

    # Upstream failed (all uncached routes errored): serve disk snapshot if available.
    snap = _read_snapshot()
    if snap is not None:
        by_route = snap["by_route"]
        snap_feats: list[dict[str, Any]] = []
        selected_codes = [str(r["route_code"]) for r in routes]
        for rc in selected_codes:
            if isinstance(by_route.get(rc), list):
                # Older snapshots were written before id/route_name/mode existed: fill them in on read.
                snap_feats.extend(
                    enrich_bus_feature(f, i) for i, f in enumerate(by_route[rc]) if isinstance(f, dict)
                )
        return _filter_bus_features(snap_feats, bbox), "snapshot", str(snap.get("updated_at") or now_iso)

    if any_cache:
        return _filter_bus_features(collected, bbox), "cache", now_iso

    return [], "unavailable", now_iso


def get_stop_arrivals(stop_code: str) -> dict[str, Any]:
    """Return cached or live OASA arrival wait times (minutes) for a bus stop."""
    now_mono = time.monotonic()
    now_iso = _now_iso()
    hit = _arrivals_cache.get(stop_code)
    if hit is not None and (now_mono - hit[0]) < config.TRANSIT_ARRIVALS_TTL_S:
        return {"stop_code": stop_code, "arrivals": list(hit[1]), "source": "cache", "updated_at": now_iso}
    try:
        raw = fetch_stop_arrivals(stop_code)
        arrivals = parse_stop_arrivals(raw)
        _arrivals_cache[stop_code] = (now_mono, arrivals)
        return {"stop_code": stop_code, "arrivals": arrivals, "source": "live", "updated_at": now_iso}
    except (httpx.HTTPError, OSError, ValueError):
        return {"stop_code": stop_code, "arrivals": [], "source": "unavailable", "updated_at": now_iso}


def get_transit(bbox: BBox | None = None) -> dict[str, Any]:
    """Assemble the SPEC GET /transit payload: lines, stations, buses, source, updated_at."""
    static = load_static()
    line_feats = static["lines"].get("features") or []
    station_feats = static["stations"].get("features") or []

    if bbox is not None:
        station_feats = [
            f
            for f in station_feats
            if point_in_bbox(f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1], bbox)
        ]
        line_feats = [f for f in line_feats if line_intersects_bbox(f, bbox)]

    bus_feats, source, updated_at = get_buses(bbox)
    return {
        "lines": {"type": "FeatureCollection", "features": line_feats},
        "stations": {"type": "FeatureCollection", "features": station_feats},
        "buses": {"type": "FeatureCollection", "features": bus_feats},
        "source": source,
        "updated_at": updated_at,
        "routes": routes_catalog(static.get("catalog") or {}, bus_feats),
    }


def routes_catalog(rail: dict[str, Any], bus_feats: list[dict[str, Any]]) -> dict[str, list]:
    """Menu catalog: every Metro / Suburban line (from static.json) and every configured OASA route.

    Rail entries are the full network (not bbox-filtered) so the menu always lists Μ1-Μ3 and A1-A4.
    active_vehicles counts the buses returned in this response (so it follows the same bbox).
    """
    active: dict[str, int] = {}
    for f in bus_feats:
        rc = str((f.get("properties") or {}).get("route_code") or "")
        active[rc] = active.get(rc, 0) + 1
    buses = []
    for rt in config.TRANSIT_ROUTES:
        rc = str(rt.get("route_code") or "")
        line = str(rt.get("line") or rc)
        bb = rt.get("bbox")
        buses.append(
            {
                "route_code": rc,
                "line": line,
                "name": str(rt.get("name") or ""),
                "mode": bus_mode(line),
                "active_vehicles": active.get(rc, 0),
                "bbox": list(bb) if bb else None,
            }
        )
    return {
        "metro": [dict(e) for e in rail.get("metro") or []],
        "suburban": [dict(e) for e in rail.get("suburban") or []],
        "buses": buses,
    }
