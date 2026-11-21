"""AthensGov open data (CKAN, https://opendata.cityofathens.gr) — public, no API key, CC BY 4.0.

Datasets used (slugs from the portal's "Smart Neighbourhood" guide):
  municipal-districts-athens   the 7 Δημοτικές Κοινότητες (geometry)
  neighbourhoods-athens        neighbourhood geometry
  env-stations-registry        environmental stations (id, name, location)
  env-all-stations             hourly measurements: AQI (1-6), °C, %, kPa, µg/m³
  wifi-stations-registry       municipal WiFi hotspots

Column names are not published in the guide, so we read each resource's schema at
runtime (datastore_info / record keys) and match columns by name (see FIELD_HINTS).
If the guess is wrong on the day, set CKAN_FIELD_<NAME>=<column> in .env.

Every successful call is snapshotted to data/ckan/ so the demo still works offline;
responses say whether they are "live", "snapshot <time>" or "unavailable".
The portal blocks browser calls (CORS), so this runs server-side only.
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone

import httpx

from . import config

SNAP_DIR = config.DATA_DIR / "ckan"
SLUGS = {
    "districts": "municipal-districts-athens",
    "neighbourhoods": "neighbourhoods-athens",
    "env_registry": "env-stations-registry",
    "env_all": "env-all-stations",
    "wifi_registry": "wifi-stations-registry",
}
FIELD_HINTS = {
    "station_id": ["station_id", "stationid", "station", "sensor_id", "id"],
    "name": ["name_el", "name", "title", "onoma", "όνομα", "label", "description"],
    "lat": ["lat", "latitude", "y", "geo_lat"],
    "lon": ["lon", "lng", "long", "longitude", "x", "geo_lon"],
    "time": ["measurement_time", "measured_at", "timestamp", "interval_start", "datetime", "date", "time"],
    "aqi": ["aqi", "air_quality_index", "caqi"],
    "temp": ["temperature", "temp", "air_temperature"],
    "humidity": ["humidity", "rh"],
    "pm25": ["pm2_5", "pm25", "pm2.5"],
    "pm10": ["pm10"],
    "no2": ["no2"],
    "geometry": ["geometry", "geom", "the_geom", "wkt", "geojson", "shape"],
}
# European AQI wording for the 1-6 scale (our reading of the portal's 1-6 AQI; confirm on the day)
AQI_EL = {1: "Καλή", 2: "Ικανοποιητική", 3: "Μέτρια", 4: "Κακή", 5: "Πολύ κακή", 6: "Εξαιρετικά κακή"}

_mem: dict = {}


class Unavailable(Exception):
    pass


def enabled() -> bool:
    return config.CKAN_MODE != "off"


# ------------------------------------------------------------------ low level
def _snap_path(key: str):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:120]
    return SNAP_DIR / f"{safe}.json"


def _call(action: str, ttl: int = 600, **params) -> dict:
    """CKAN action with memory cache + disk snapshot fallback. Returns {'result', 'source', 'at'}."""
    key = action + "?" + json.dumps(params, sort_keys=True, ensure_ascii=False)
    hit = _mem.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    if config.CKAN_MODE == "live":
        try:
            r = httpx.post(f"{config.CKAN_URL}/{action}", json=params, timeout=12,
                           headers={"User-Agent": "AthensOne-hackathon/0.3"})
            r.raise_for_status()
            j = r.json()
            if not j.get("success", True):
                raise Unavailable(str(j.get("error")))
            out = {"result": j["result"], "source": "live", "at": _now()}
            SNAP_DIR.mkdir(parents=True, exist_ok=True)
            _snap_path(key).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            _mem[key] = (time.time() + ttl, out)
            return out
        except Exception:
            pass  # fall through to the snapshot
    p = _snap_path(key)
    if config.CKAN_MODE != "off" and p.exists():
        out = json.loads(p.read_text(encoding="utf-8"))
        out["source"] = f"snapshot {out.get('at', '')}"
        _mem[key] = (time.time() + 60, out)
        return out
    raise Unavailable(f"{action} unavailable ({config.CKAN_MODE})")


def _fetch_url(url: str) -> dict:
    """A resource file (e.g. GeoJSON) on the portal, with the same snapshot fallback."""
    key = "url:" + url
    p = _snap_path(key)
    if config.CKAN_MODE == "live":
        try:
            r = httpx.get(url, timeout=20, headers={"User-Agent": "AthensOne-hackathon/0.3"})
            r.raise_for_status()
            data = r.json()
            SNAP_DIR.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"result": data, "at": _now()}, ensure_ascii=False), encoding="utf-8")
            return {"result": data, "source": "live", "at": _now()}
        except Exception:
            pass
    if config.CKAN_MODE != "off" and p.exists():
        out = json.loads(p.read_text(encoding="utf-8"))
        return {"result": out["result"], "source": f"snapshot {out.get('at', '')}", "at": out.get("at")}
    raise Unavailable(url)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def package(slug: str) -> dict:
    return _call("package_show", ttl=3600, id=slug)


def records(resource_id: str, limit: int = 500, sort: str | None = None, filters: dict | None = None) -> dict:
    params = {"resource_id": resource_id, "limit": limit}
    if sort:
        params["sort"] = sort
    if filters:
        params["filters"] = filters
    return _call("datastore_search", ttl=300, **params)


def datastore_resource(pkg: dict) -> dict | None:
    res = pkg.get("resources") or []
    return next((r for r in res if r.get("datastore_active")), None)


# ------------------------------------------------------------------ field matching
def field(keys, role: str) -> str | None:
    override = os.getenv(f"CKAN_FIELD_{role.upper()}")
    if override and override in keys:
        return override
    low = {k.lower(): k for k in keys}
    for hint in FIELD_HINTS[role]:
        if hint in low:
            return low[hint]
    for hint in FIELD_HINTS[role]:  # substring match second (e.g. "pm2_5_ugm3")
        if len(hint) < 3:
            continue
        for lk, k in low.items():
            if hint in lk:
                return k
    return None


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ geometry helpers
def _geom(value):
    if isinstance(value, dict):
        return value if "type" in value else None
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return None


def _rings(geom):
    if not geom:
        return []
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [p[0] for p in geom["coordinates"]]
    return []


def _in_ring(x, y, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-15) + x1:
            inside = not inside
    return inside


# ------------------------------------------------------------------ datasets
def _polygons(slug_key: str) -> dict:
    pkg = package(SLUGS[slug_key])
    res = pkg["result"].get("resources") or []
    geo = next((r for r in res if str(r.get("format", "")).lower() in ("geojson", "json") and r.get("url")), None)
    if geo:
        got = _fetch_url(geo["url"])
        fc = got["result"]
        if fc.get("type") == "FeatureCollection":
            for f in fc["features"]:
                props = f.get("properties") or {}
                nk = field(list(props), "name")
                props["name_el"] = props.get(nk) if nk else None
            return {"type": "FeatureCollection", "features": fc["features"], "source": got["source"]}
    ds = datastore_resource(pkg["result"])
    if not ds:
        raise Unavailable(f"no geometry in {SLUGS[slug_key]}")
    got = records(ds["id"], limit=1000)
    recs = got["result"].get("records", [])
    keys = list(recs[0]) if recs else []
    gk, nk = field(keys, "geometry"), field(keys, "name")
    feats = []
    for rec in recs:
        g = _geom(rec.get(gk)) if gk else None
        if g:
            feats.append({"type": "Feature", "geometry": g,
                          "properties": {"name_el": rec.get(nk) if nk else None, "id": rec.get("_id")}})
    return {"type": "FeatureCollection", "features": feats, "source": got["source"]}


def districts() -> dict:
    return _polygons("districts")


def neighbourhoods() -> dict:
    return _polygons("neighbourhoods")


def district_of(lat, lng) -> str | None:
    """Name of the Δημοτική Κοινότητα containing the point, or None if unknown/unavailable."""
    if lat is None or not enabled():
        return None
    try:
        fc = districts()
    except Unavailable:
        return None
    for f in fc["features"]:
        if any(_in_ring(lng, lat, r) for r in _rings(f.get("geometry"))):
            return f["properties"].get("name_el") or "—"
    return None


def _registry(slug_key: str) -> tuple[list[dict], str]:
    pkg = package(SLUGS[slug_key])
    ds = datastore_resource(pkg["result"])
    if not ds:
        raise Unavailable(f"no datastore in {SLUGS[slug_key]}")
    got = records(ds["id"], limit=1000)
    recs = got["result"].get("records", [])
    if not recs:
        return [], got["source"]
    keys = list(recs[0])
    f_id, f_name, f_lat, f_lon = (field(keys, r) for r in ("station_id", "name", "lat", "lon"))
    out = []
    for rec in recs:
        lat, lon = _num(rec.get(f_lat)), _num(rec.get(f_lon))
        if lat is None or lon is None:
            g = _geom(rec.get(field(keys, "geometry") or ""))
            if g and g.get("type") == "Point":
                lon, lat = g["coordinates"][:2]
        if lat is None or lon is None:
            continue
        out.append({"station_id": rec.get(f_id) if f_id else rec.get("_id"), "name": rec.get(f_name) if f_name else None,
                    "lat": lat, "lng": lon})
    return out, got["source"]


def env_stations():
    return _registry("env_registry")


def wifi_stations():
    return _registry("wifi_registry")


def air_latest() -> dict:
    """Newest measurement per station, joined to station coordinates."""
    stations, src_reg = env_stations()
    pkg = package(SLUGS["env_all"])
    ds = datastore_resource(pkg["result"])
    if not ds:
        raise Unavailable("env-all-stations has no datastore resource")
    probe = records(ds["id"], limit=1)["result"].get("records", [])
    keys = list(probe[0]) if probe else []
    f = {r: field(keys, r) for r in ("station_id", "time", "aqi", "temp", "humidity", "pm25", "pm10", "no2")}
    got = records(ds["id"], limit=max(200, 4 * len(stations)), sort=f"{f['time']} desc" if f["time"] else None)
    latest: dict = {}
    for rec in got["result"].get("records", []):
        sid = rec.get(f["station_id"]) if f["station_id"] else None
        if sid is None or sid in latest:
            continue
        latest[sid] = rec
    by_id = {str(s["station_id"]): s for s in stations}
    items = []
    for sid, rec in latest.items():
        st = by_id.get(str(sid))
        if not st:
            continue
        aqi = _num(rec.get(f["aqi"])) if f["aqi"] else None
        items.append({**st, "time": rec.get(f["time"]) if f["time"] else None,
                      "aqi": int(aqi) if aqi else None, "aqi_el": AQI_EL.get(int(aqi)) if aqi else None,
                      "temp_c": _num(rec.get(f["temp"])) if f["temp"] else None,
                      "humidity": _num(rec.get(f["humidity"])) if f["humidity"] else None,
                      "pm25": _num(rec.get(f["pm25"])) if f["pm25"] else None,
                      "pm10": _num(rec.get(f["pm10"])) if f["pm10"] else None,
                      "no2": _num(rec.get(f["no2"])) if f["no2"] else None})
    return {"items": items, "source": got["source"], "fields": f,
            "note": "AthensGov env-all-stations, CC BY 4.0; AQI wording = European AQI reading of the 1-6 scale"}


def nearest_air(lat, lng, max_km=1.5) -> dict | None:
    if not enabled():
        return None
    try:
        items = air_latest()["items"]
    except (Unavailable, KeyError):
        return None
    best = None
    for s in items:
        d = _km(lat, lng, s["lat"], s["lng"])
        if d <= max_km and (best is None or d < best[0]):
            best = (d, s)
    return {**best[1], "distance_km": round(best[0], 2)} if best else None


def _km(lat1, lng1, lat2, lng2):
    k = 111.32
    return math.hypot((lng2 - lng1) * k * math.cos(math.radians(lat1)), (lat2 - lat1) * k)


def status() -> dict:
    out = {"mode": config.CKAN_MODE, "url": config.CKAN_URL, "datasets": {}}
    for key, slug in SLUGS.items():
        try:
            out["datasets"][slug] = package(slug)["source"]
        except Unavailable as e:
            out["datasets"][slug] = f"unavailable: {e}"
    return out
