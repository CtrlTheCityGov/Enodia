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
    "lat": ["lat", "latitude", "y", "geo_lat", "position_lat"],
    "lon": ["lon", "lng", "long", "longitude", "x", "geo_lon", "position_lon"],
    "time": ["measurement_time", "measured_at", "timestamp", "interval_start", "datetime", "date", "time"],
    "aqi": ["aqi", "air_quality_index", "caqi"],
    "temp": ["temperature", "temp", "air_temperature"],
    "humidity": ["humidity", "rh"],
    "pm25": ["pm2_5", "pm25", "pm2.5"],
    "pm10": ["pm10"],
    "no2": ["no2"],
    "geometry": ["geometry", "geom", "the_geom", "wkt", "geojson", "shape", "polygon_geo"],
    # --- T10: City districts and air stations from CKAN ---
    # Join keys verified live on opendata.cityofathens.gr (TASKS.md T10, Sat 21 Nov; certainty: sure).
    "district_id": ["municipal_district_id", "district_id"],
    "neighbourhood_id": ["neighbourhood_id", "neighborhood_id"],
}
# Station location precision flags (DECISIONS.md A-21; certainty: sure).
LOCATION_EXACT = "exact"
LOCATION_NEIGHBOURHOOD_CENTRE = "neighbourhood_centre"
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


def _num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(str(v).strip().replace(",", "."))
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ geometry helpers
# --- T10: City districts and air stations from CKAN ---
# OGC WKT (ISO/IEC 13249-3) parser for POINT, POLYGON, MULTIPOLYGON strings (TASKS.md T10; certainty: sure).
_WKT_DIM_TAGS = ("Z", "M", "ZM")  # optional OGC WKT coordinate dimension suffixes (certainty: sure)


def _unwrap_parens(text: str) -> str | None:
    """Strip one balanced pair of outer parentheses, or return None if unbalanced."""
    s = text.strip()
    if len(s) < 2 or s[0] != "(" or s[-1] != ")":
        return None
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0 or (depth == 0 and i != len(s) - 1):
                return None
    return s[1:-1].strip() if depth == 0 else None


def _split_top_level(text: str) -> list[str] | None:
    """Split on top-level commas outside nested parentheses; return None if unbalanced."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return None
        elif ch == "," and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 1
    if depth != 0:
        return None
    parts.append(text[start:].strip())
    return parts


def _wkt_coord(text: str) -> list[float] | None:
    """Parse one 'lon lat [z [m]]' WKT coordinate into [lon, lat]."""
    toks = text.strip().split()
    if len(toks) < 2 or len(toks) > 4:
        return None
    x, y = _num(toks[0]), _num(toks[1])
    if x is None or y is None:
        return None
    return [x, y]


def _wkt_ring(text: str) -> list[list[float]] | None:
    """Parse a parenthesized WKT ring '(x1 y1, x2 y2, ...)'."""
    inner = _unwrap_parens(text)
    if not inner:
        return None
    pts: list[list[float]] = []
    for item in inner.split(","):
        pt = _wkt_coord(item)
        if pt is None:
            return None
        pts.append(pt)
    return pts if len(pts) >= 3 else None


def _wkt_polygon_coords(text: str) -> list[list[list[float]]] | None:
    """Parse '((ring1), (hole1), ...)' into GeoJSON Polygon coordinates."""
    inner = _unwrap_parens(text)
    if not inner:
        return None
    ring_strs = _split_top_level(inner)
    if not ring_strs:
        return None
    rings: list[list[list[float]]] = []
    for rs in ring_strs:
        ring = _wkt_ring(rs)
        if ring is None:
            return None
        rings.append(ring)
    return rings


def _parse_wkt(text: str) -> dict | None:
    """Parse a WKT POINT, POLYGON, or MULTIPOLYGON string into a GeoJSON geometry dict."""
    s = text.strip()
    if not s:
        return None
    if s.upper().startswith("SRID=") and ";" in s:
        s = s.split(";", 1)[1].strip()
    paren = s.find("(")
    if paren == -1:
        return None
    head = s[:paren].strip().upper().split()
    if not head or len(head) > 2 or (len(head) == 2 and head[1] not in _WKT_DIM_TAGS):
        return None
    kind, body = head[0], s[paren:].strip()
    if kind == "POINT":
        inner = _unwrap_parens(body)
        if not inner or "," in inner:
            return None
        pt = _wkt_coord(inner)
        return {"type": "Point", "coordinates": pt} if pt is not None else None
    if kind == "POLYGON":
        rings = _wkt_polygon_coords(body)
        return {"type": "Polygon", "coordinates": rings} if rings is not None else None
    if kind == "MULTIPOLYGON":
        inner = _unwrap_parens(body)
        if not inner:
            return None
        poly_strs = _split_top_level(inner)
        if not poly_strs:
            return None
        polys: list[list[list[list[float]]]] = []
        for ps in poly_strs:
            poly = _wkt_polygon_coords(ps)
            if poly is None:
                return None
            polys.append(poly)
        return {"type": "MultiPolygon", "coordinates": polys}
    return None


def _geom(value):
    if isinstance(value, dict):
        return value if "type" in value else None
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("{"):
            try:
                g = json.loads(s)
                return g if isinstance(g, dict) and "type" in g else None
            except ValueError:
                return None
        return _parse_wkt(s)
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
    dk = field(keys, "district_id")
    feats = []
    for rec in recs:
        g = _geom(rec.get(gk)) if gk else None
        if g:
            props = {"name_el": rec.get(nk) if nk else None,
                     "id": rec.get("id") if rec.get("id") is not None else rec.get("_id")}
            if dk and rec.get(dk) is not None:
                props["municipal_district_id"] = str(rec.get(dk)).strip()
            feats.append({"type": "Feature", "geometry": g, "properties": props})
    return {"type": "FeatureCollection", "features": feats, "source": got["source"]}


def districts() -> dict:
    return _polygons("districts")


def neighbourhoods() -> dict:
    return _polygons("neighbourhoods")


# --- T10: City districts and air stations from CKAN ---
def _district_names() -> dict[str, str]:
    """Map municipal district id (str) -> district name from municipal-districts-athens."""
    pkg = package(SLUGS["districts"])
    ds = datastore_resource(pkg["result"])
    if not ds:
        return {}
    got = records(ds["id"], limit=1000)
    recs = got["result"].get("records", [])
    if not recs:
        return {}
    keys = list(recs[0])
    low = {k.lower(): k for k in keys}
    f_id = low.get("id") or low.get("municipal_district_id") or low.get("district_id") or low.get("_id")
    f_name = field(keys, "name")
    if not f_id or not f_name:
        return {}
    names: dict[str, str] = {}
    for rec in recs:
        did, name = rec.get(f_id), rec.get(f_name)
        if did is not None and name:
            names[str(did).strip()] = str(name)
    return names


def _neighbourhood_centres() -> dict[str, tuple[float, float]]:
    """Map neighbourhood id (str) -> (lat, lon) centre from neighbourhoods-athens."""
    pkg = package(SLUGS["neighbourhoods"])
    ds = datastore_resource(pkg["result"])
    if not ds:
        return {}
    got = records(ds["id"], limit=1000)
    recs = got["result"].get("records", [])
    if not recs:
        return {}
    keys = list(recs[0])
    low = {k.lower(): k for k in keys}
    f_id = low.get("id") or low.get("neighbourhood_id") or low.get("_id")
    f_lat, f_lon = field(keys, "lat"), field(keys, "lon")
    if not f_id or not f_lat or not f_lon:
        return {}
    centres: dict[str, tuple[float, float]] = {}
    for rec in recs:
        nid = rec.get(f_id)
        lat, lon = _num(rec.get(f_lat)), _num(rec.get(f_lon))
        if nid is not None and lat is not None and lon is not None:
            centres[str(nid).strip()] = (lat, lon)
    return centres


def district_of(lat, lng) -> str | None:
    """Name of the Δημοτική Κοινότητα containing the point, or None if unknown/unavailable."""
    lat, lng = _num(lat), _num(lng)
    if lat is None or lng is None or not enabled():
        return None
    try:
        fc = districts()
    except Unavailable:
        return None
    if fc["features"]:
        for f in fc["features"]:
            if any(_in_ring(lng, lat, r) for r in _rings(f.get("geometry"))):
                return f["properties"].get("name_el") or "—"
        return None
    try:
        nb = neighbourhoods()
        names = _district_names()
    except Unavailable:
        return None
    for f in nb["features"]:
        if any(_in_ring(lng, lat, r) for r in _rings(f.get("geometry"))):
            did = (f.get("properties") or {}).get("municipal_district_id")
            if did is not None:
                return names.get(str(did).strip())
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
    f_geom, f_nb = field(keys, "geometry"), field(keys, "neighbourhood_id")
    nb_centres: dict[str, tuple[float, float]] | None = None
    out = []
    for rec in recs:
        lat = _num(rec.get(f_lat)) if f_lat else None
        lon = _num(rec.get(f_lon)) if f_lon else None
        location = LOCATION_EXACT
        if lat is None or lon is None:
            g = _geom(rec.get(f_geom)) if f_geom else None
            coords = g.get("coordinates") if g and g.get("type") == "Point" else None
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                lon, lat = _num(coords[0]), _num(coords[1])
        if (lat is None or lon is None) and f_nb:
            nid = rec.get(f_nb)
            if nid is not None and str(nid).strip():
                if nb_centres is None:
                    try:
                        nb_centres = _neighbourhood_centres()
                    except Unavailable:
                        nb_centres = {}
                centre = nb_centres.get(str(nid).strip())
                if centre:
                    lat, lon = centre
                    location = LOCATION_NEIGHBOURHOOD_CENTRE
        if lat is None or lon is None:
            continue
        out.append({"station_id": rec.get(f_id) if f_id else rec.get("_id"), "name": rec.get(f_name) if f_name else None,
                    "lat": lat, "lng": lon, "location": location})
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
        if sid is None:
            continue
        sid_key = str(sid).strip()
        if not sid_key or sid_key in latest:
            continue
        latest[sid_key] = rec
    by_id = {str(s["station_id"]).strip(): s for s in stations}
    items = []
    for sid_key, rec in latest.items():
        st = by_id.get(sid_key)
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
