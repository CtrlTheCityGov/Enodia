"""Transit data adapter (B3): static metro/suburban rail + live OASA bus telematics.

Static lines and stations are built once into data/transit/static.json by scripts/fetch_transit.py
(from OpenStreetMap via Overpass; OASA/STASY static GTFS URLs returned 404/timeout on 2026-11-21).
Live bus positions and stop arrivals come from OASA Telematics (https://telematics.oasa.gr/api/)
with a 20 s in-memory TTL cache and disk snapshot fallback at data/transit/last.json.
"""
from __future__ import annotations

import json
import time
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

BBox = tuple[float, float, float, float]


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


def parse_bus_locations(payload: Any, route_code: str, line: str, fetched_at: str) -> list[dict[str, Any]]:
    """Parse an OASA getBusLocation JSON payload into GeoJSON Point features.

    OASA returns an empty string '' or null when no vehicle is active on a route; those become [].
    Bearing is set to float(VEH_HEADING) when provided and numeric, else None (never 0 or guessed).
    """
    if not isinstance(payload, list):
        return []
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
                    "vehicle_id": veh,
                    "line": line,
                    "route_code": rc,
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
def load_static() -> dict[str, Any]:
    """Load pre-built static metro/suburban lines and stations from STATIC_PATH."""
    empty_fc = {"type": "FeatureCollection", "features": []}
    if not STATIC_PATH.exists():
        return {"lines": dict(empty_fc), "stations": dict(empty_fc)}
    try:
        data = json.loads(STATIC_PATH.read_text(encoding="utf-8"))
        lines = data.get("lines") or empty_fc
        stations = data.get("stations") or empty_fc
        return {"lines": lines, "stations": stations}
    except (OSError, ValueError):
        return {"lines": dict(empty_fc), "stations": dict(empty_fc)}


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

    for rt in routes:
        rc = str(rt["route_code"])
        line = str(rt.get("line") or rc)
        hit = _bus_cache.get(rc)
        if hit is not None and (now_mono - hit[0]) < config.TRANSIT_BUS_TTL_S:
            collected.extend(hit[1])
            any_cache = True
            continue
        try:
            raw = fetch_bus_locations(rc)
            feats = parse_bus_locations(raw, rc, line, now_iso)
            _bus_cache[rc] = (now_mono, feats)
            fresh_by_route[rc] = feats
            collected.extend(feats)
            any_live = True
        except (httpx.HTTPError, OSError, ValueError):
            failed_codes.append(rc)

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
                snap_feats.extend(by_route[rc])
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
    }
