"""Open-Meteo environmental grid (temperature, European AQI, PM2.5) with CKAN station overrides.

Builds a fixed grid across the Municipality of Athens (spacing config.ENV_GRID_M, default 600 m),
fetches current temperature and air quality in one multi-coordinate request per upstream API,
caches in memory for config.ENV_CACHE_TTL_S (15 min), and snapshots the last good grid to
data/envgrid/last.json for offline fallback.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from . import ckan, config

# Mean metres per degree of latitude on WGS84 (source: matches app/env.py:26 & app/ckan.py:560; certainty: sure).
METERS_PER_DEG_LAT = 111_320.0
# Coordinate rounding precision in decimal degrees (~1.1 m at Athens latitude; keeps query URLs compact and matches
# tests/test_B5_envgrid.py:157; certainty: sure).
COORD_DECIMALS = 5
# Open-Meteo query timezone for Athens (source: matches app/main.py:132; certainty: sure).
OPEN_METEO_TIMEZONE = "Europe/Athens"
# Open-Meteo current-variable query strings (verified online 2026-11-21 on both v1 endpoints; certainty: verified).
FORECAST_CURRENT_FIELDS = "temperature_2m"
AIR_QUALITY_CURRENT_FIELDS = "european_aqi,pm2_5,uv_index"
# Disk snapshot location relative to config.DATA_DIR (source: docs/TASKS_B.md Common to B2–B5 &
# tests/test_B5_envgrid.py:35; certainty: sure).
SNAPSHOT_SUBDIR = "envgrid"
SNAPSHOT_FILENAME = "last.json"
# Fallback station label when a CKAN station record omits both name and station_id
# (source: matches app/main.py:231; certainty: sure).
STATION_FALLBACK_LABEL = "AthensGov"

_cache: dict[str, Any] | None = None


def _now_iso() -> str:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(timespec="seconds")


def _opt_num(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _valid_iso(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return s
    except ValueError:
        return None


def _station_label(station: dict[str, Any]) -> str:
    raw_name = station.get("name")
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()
    sid = station.get("station_id")
    if sid is not None and str(sid).strip():
        return str(sid).strip()
    return STATION_FALLBACK_LABEL


def grid_points(
    bbox: tuple[float, float, float, float] | None = None,
    step_m: float | None = None,
) -> list[tuple[float, float]]:
    """Return fixed (lon, lat) grid centres inside bbox spaced by step_m metres."""
    min_lon, min_lat, max_lon, max_lat = bbox if bbox is not None else config.ENV_BBOX
    step = float(step_m if step_m is not None else config.ENV_GRID_M)
    if step <= 0 or not math.isfinite(step):
        raise ValueError("ENV_GRID_M must be a positive finite number")

    mid_lat = (min_lat + max_lat) / 2.0
    dlat = step / METERS_PER_DEG_LAT
    dlon = step / (METERS_PER_DEG_LAT * math.cos(math.radians(mid_lat)))

    points: list[tuple[float, float]] = []
    lat = min_lat + dlat / 2.0
    while lat <= max_lat:
        lon = min_lon + dlon / 2.0
        while lon <= max_lon:
            rlon = round(lon, COORD_DECIMALS)
            rlat = round(lat, COORD_DECIMALS)
            if min_lon <= rlon <= max_lon and min_lat <= rlat <= max_lat:
                points.append((rlon, rlat))
            lon += dlon
        lat += dlat
    return points


def _coord_params(points: list[tuple[float, float]], current_fields: str) -> dict[str, str]:
    return {
        "latitude": ",".join(str(lat) for _, lat in points),
        "longitude": ",".join(str(lon) for lon, _ in points),
        "current": current_fields,
        "timezone": OPEN_METEO_TIMEZONE,
    }


def _normalize_batch(payload: Any, expected: int) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        rows = [payload]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError("unexpected Open-Meteo payload type")
    if len(rows) != expected or not all(isinstance(r, dict) for r in rows):
        raise ValueError(f"Open-Meteo returned {len(rows)} rows for {expected} grid points")
    return rows


def fetch_forecast(points: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Fetch current temperature_2m for all grid points in one Open-Meteo Forecast call."""
    r = httpx.get(
        config.ENV_FORECAST_URL,
        params=_coord_params(points, FORECAST_CURRENT_FIELDS),
        timeout=config.ENV_HTTP_TIMEOUT_S,
    )
    r.raise_for_status()
    return _normalize_batch(r.json(), len(points))


def fetch_air_quality(points: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Fetch current european_aqi and pm2_5 for all grid points in one Open-Meteo Air Quality call."""
    r = httpx.get(
        config.ENV_AIR_QUALITY_URL,
        params=_coord_params(points, AIR_QUALITY_CURRENT_FIELDS),
        timeout=config.ENV_HTTP_TIMEOUT_S,
    )
    r.raise_for_status()
    return _normalize_batch(r.json(), len(points))


def build_features(
    points: list[tuple[float, float]],
    forecast_rows: list[dict[str, Any]],
    aq_rows: list[dict[str, Any]],
    fetched_at: str,
    station_lookup: Callable[[float, float], dict[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    """Combine grid coordinates, Open-Meteo readings, and optional CKAN station overrides into GeoJSON Features."""
    features: list[dict[str, Any]] = []
    for (lon, lat), fc, aq in zip(points, forecast_rows, aq_rows):
        fc_cur = fc.get("current") if isinstance(fc.get("current"), dict) else {}
        aq_cur = aq.get("current") if isinstance(aq.get("current"), dict) else {}

        temp_c = _opt_num(fc_cur.get("temperature_2m"))
        aqi = _opt_num(aq_cur.get("european_aqi"))
        pm25 = _opt_num(aq_cur.get("pm2_5"))
        uv_index = _opt_num(aq_cur.get("uv_index"))
        point_updated = _valid_iso(fc_cur.get("time")) or _valid_iso(aq_cur.get("time")) or fetched_at

        props: dict[str, Any] = {
            "temp_c": temp_c,
            "aqi": aqi,
            # Which AQI scale `aqi` is on (A-37): Open-Meteo European AQI 0-100+ ("eaqi") or the AthensGov
            # station class 1-6 ("city_1_6"). They don't compare; clients colour by pm25. Source: Open-Meteo
            # air-quality API docs, AthensGov CKAN env-all-stations (app/ckan.py). Certainty: sure.
            "aqi_scale": "eaqi" if aqi is not None else None,
            "pm25": pm25,
            "uv_index": uv_index,
            "updated_at": point_updated,
        }

        if station_lookup is not None:
            st = station_lookup(lat, lon)
            if isinstance(st, dict):
                overridden = False
                for key in ("temp_c", "aqi", "pm25"):
                    val = _opt_num(st.get(key))
                    if val is not None:
                        props[key] = val
                        overridden = True
                        if key == "aqi":
                            props["aqi_scale"] = "city_1_6"  # A-37
                if overridden:
                    st_time = _valid_iso(st.get("time"))
                    if st_time:
                        props["updated_at"] = st_time
                    props["station"] = _station_label(st)

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            }
        )
    return features


def filter_bbox(
    features: list[dict[str, Any]],
    bbox: tuple[float, float, float, float] | None,
) -> list[dict[str, Any]]:
    """Keep only GeoJSON Point features whose [lon, lat] fall inside (minLon, minLat, maxLon, maxLat)."""
    if bbox is None:
        return list(features)
    min_lon, min_lat, max_lon, max_lat = bbox
    out: list[dict[str, Any]] = []
    for feat in features:
        lon, lat = feat["geometry"]["coordinates"]
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            out.append(feat)
    return out


def _snapshot_path() -> Path:
    return config.DATA_DIR / SNAPSHOT_SUBDIR / SNAPSHOT_FILENAME


def _save_snapshot(features: list[dict[str, Any]], updated_at: str) -> None:
    path = _snapshot_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"features": features, "updated_at": updated_at}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def _load_snapshot() -> tuple[list[dict[str, Any]], str] | None:
    path = _snapshot_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        return None
    updated_at = _valid_iso(data.get("updated_at")) or _now_iso()
    return data["features"], updated_at


def _response(
    features: list[dict[str, Any]],
    source: str,
    updated_at: str,
    bbox: tuple[float, float, float, float] | None,
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": filter_bbox(features, bbox),
        "source": source,
        "updated_at": updated_at,
    }


def get_env_grid(bbox: tuple[float, float, float, float] | None = None) -> dict[str, Any]:
    """Return the Athens environmental grid as a GeoJSON FeatureCollection with TTL cache and snapshot fallback."""
    global _cache
    now_mono = time.monotonic()
    grid_key = (config.ENV_BBOX, config.ENV_GRID_M)

    if _cache is not None and _cache["key"] == grid_key and now_mono < _cache["expires_at"]:
        return _response(_cache["features"], "cache", _cache["updated_at"], bbox)

    if config.WEATHER != "off":
        try:
            pts = grid_points()
            fc_rows = fetch_forecast(pts)
            aq_rows = fetch_air_quality(pts)
            fetched_at = _now_iso()
            max_km = config.ENV_STATION_MAX_M / 1000.0
            station_lookup = (
                (lambda lat, lon: ckan.nearest_air(lat, lon, max_km=max_km))
                if ckan.enabled()
                else None
            )
            features = build_features(pts, fc_rows, aq_rows, fetched_at, station_lookup=station_lookup)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            features = None
        if features is not None:
            _cache = {
                "key": grid_key,
                "expires_at": now_mono + config.ENV_CACHE_TTL_S,
                "features": features,
                "updated_at": fetched_at,
            }
            _save_snapshot(features, fetched_at)
            return _response(features, "live", fetched_at, bbox)

    snap = _load_snapshot()
    if snap is not None:
        snap_features, snap_updated = snap
        return _response(snap_features, "snapshot", snap_updated, bbox)

    return _response([], "unavailable", _now_iso(), bbox)
