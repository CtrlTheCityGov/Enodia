"""Step-free walking routes with Valhalla (OpenStreetMap data).

Pedestrian costing with type "wheelchair"; reported hazards are passed as
exclude_locations so the route goes around them. If Valhalla is unreachable,
a clearly-labelled straight-line fallback keeps the demo moving.
"""
from __future__ import annotations

import math
import time

import httpx

from . import config
from .geo import decode_polyline6, haversine_km

_cache: dict = {}


def route(frm: dict, to: dict, hazards: list[dict] | None = None, profile: str = "wheelchair") -> dict:
    hazards = hazards or []
    key = (round(frm["lat"], 5), round(frm["lng"], 5), round(to["lat"], 5), round(to["lng"], 5),
           tuple(sorted((round(h["lat"], 5), round(h["lng"], 5)) for h in hazards)), profile)
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    body = {
        "locations": [{"lat": frm["lat"], "lon": frm["lng"]}, {"lat": to["lat"], "lon": to["lng"]}],
        "costing": "pedestrian",
        "costing_options": {"pedestrian": {"type": profile}} if profile in ("wheelchair", "blind") else {},
        "exclude_locations": [{"lat": h["lat"], "lon": h["lng"]} for h in hazards],
        "directions_options": {"units": "kilometers", "language": "el-GR"},
    }
    try:
        r = httpx.post(f"{config.VALHALLA_URL}/route", json=body, timeout=12)
        r.raise_for_status()
        trip = r.json()["trip"]
        leg = trip["legs"][0]
        result = {
            "source": "valhalla",
            "geojson": {"type": "LineString", "coordinates": decode_polyline6(leg["shape"])},
            "distance_km": round(trip["summary"]["length"], 3),
            "duration_min": round(trip["summary"]["time"] / 60, 1),
            "avoided_hazards": len(hazards),
            "steps": [m.get("instruction") for m in leg.get("maneuvers", [])][:30],
        }
    except Exception as e:
        result = _fallback(frm, to, hazards)
        result["error"] = f"{type(e).__name__}"
    _cache[key] = (time.time() + 300, result)
    return result


def _seg_dist_km(p, a, b):
    kx = 111.32 * math.cos(math.radians(a["lat"]))
    ax, ay, bx, by = a["lng"] * kx, a["lat"] * 111.32, b["lng"] * kx, b["lat"] * 111.32
    px, py = p["lng"] * kx, p["lat"] * 111.32
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ((dx * dx + dy * dy) or 1)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _fallback(frm, to, hazards):
    """Straight line, bent sideways around any hazard close to the line. Demo only."""
    pts = [[frm["lng"], frm["lat"]]]
    for h in hazards:
        if _seg_dist_km(h, frm, to) < 0.04:  # only hazards actually on the straight line
            pts.append([h["lng"] + 0.0008, h["lat"] + 0.0008])
    pts.append([to["lng"], to["lat"]])
    dist = sum(haversine_km(a[1], a[0], b[1], b[0]) for a, b in zip(pts, pts[1:]))
    return {"source": "fallback", "geojson": {"type": "LineString", "coordinates": pts},
            "distance_km": round(dist, 3), "duration_min": round(dist / 3.5 * 60, 1),
            "avoided_hazards": len(hazards), "steps": []}


# ------------------------------------------------------------------ multi-candidate navigation
# Accessibility profiles -> Valhalla pedestrian costing. All except "walk" avoid steps.
PROFILES = {
    "wheelchair": {"type": "wheelchair"},
    "walker": {"type": "wheelchair", "walking_speed": 3.0},   # walking aid / older person
    "stroller": {"type": "wheelchair", "walking_speed": 4.0},
    "blind": {"type": "blind"},
    "walk": {},
}


def _trip(trip, label, source="valhalla"):
    leg = trip["legs"][0]
    return {"source": source, "label": label,
            "geojson": {"type": "LineString", "coordinates": decode_polyline6(leg["shape"])},
            "distance_km": round(trip["summary"]["length"], 3),
            "duration_min": round(trip["summary"]["time"] / 60, 1),
            "steps": [m.get("instruction") for m in leg.get("maneuvers", [])][:30]}


def candidates(frm: dict, to: dict, hazards=None, profile="wheelchair", avoid_polys=None) -> list[dict]:
    """Several step-free candidates: Valhalla's best + alternates, plus one that excludes busy roads.
    Ranking happens in main.navigate with env.score_line; here we only generate."""
    hazards = hazards or []
    key = ("cand", round(frm["lat"], 5), round(frm["lng"], 5), round(to["lat"], 5), round(to["lng"], 5),
           tuple(sorted((round(h["lat"], 5), round(h["lng"], 5)) for h in hazards)), profile, bool(avoid_polys))
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    is_auto = profile == "auto"
    base = {
        "locations": [{"lat": frm["lat"], "lon": frm["lng"]}, {"lat": to["lat"], "lon": to["lng"]}],
        "costing": "auto" if is_auto else "pedestrian",
        "costing_options": {"auto": {"use_tolls": 0.5}} if is_auto else {"pedestrian": PROFILES.get(profile, PROFILES["wheelchair"])},
        "exclude_locations": [{"lat": h["lat"], "lon": h["lng"]} for h in hazards],
        "directions_options": {"units": "kilometers", "language": "el-GR"},
    }
    out = []
    try:
        r = httpx.post(f"{config.VALHALLA_URL}/route", json={**base, "alternates": 2}, timeout=12)
        r.raise_for_status()
        j = r.json()
        out.append(_trip(j["trip"], "Valhalla · βέλτιστη"))
        out += [_trip(a["trip"], f"Valhalla · εναλλακτική {i + 1}") for i, a in enumerate(j.get("alternates", []))]
        if avoid_polys:
            try:
                r2 = httpx.post(f"{config.VALHALLA_URL}/route", json={**base, "exclude_polygons": avoid_polys}, timeout=12)
                r2.raise_for_status()
                out.append(_trip(r2.json()["trip"], "Valhalla · αποφυγή κυκλοφορίας"))
            except Exception:
                pass  # no route without busy roads: fine, keep the others
    except Exception as e:
        out = _fallback_candidates(frm, to, hazards, speed_kmh=22.0 if is_auto else 3.5)
        for c in out:
            c["error"] = type(e).__name__
    # drop near-duplicates (same length within 2% and same midpoint within ~15 m)
    uniq = []
    for c in out:
        co = c["geojson"]["coordinates"]
        mid = co[len(co) // 2]
        if not any(abs(c["distance_km"] - u["distance_km"]) <= 0.02 * u["distance_km"] and
                   haversine_km(mid[1], mid[0], *u["_mid"][::-1]) < 0.015 for u in uniq):
            c["_mid"] = mid
            uniq.append(c)
    for c in uniq:
        c.pop("_mid", None)
        c["avoided_hazards"] = len(hazards)
    _cache[key] = (time.time() + 300, uniq)
    return uniq


def _fallback_candidates(frm, to, hazards, speed_kmh: float = 3.5):
    """Offline demo only: direct line + two side detours, clearly labelled."""
    direct = _fallback(frm, to, hazards)
    direct["label"] = "Δοκιμαστική · ευθεία"
    if speed_kmh > 5.0:
        direct["duration_min"] = round(direct["distance_km"] / speed_kmh * 60, 1)
    kx = 111.32 * math.cos(math.radians(frm["lat"]))
    dx, dy = (to["lng"] - frm["lng"]) * kx, (to["lat"] - frm["lat"]) * 111.32
    L = (dx * dx + dy * dy) ** .5 or 1
    off_km = min(0.12, L * 0.3)
    out = [direct]
    for sign, name in ((1, "Δοκιμαστική · παράκαμψη Β"), (-1, "Δοκιμαστική · παράκαμψη Ν")):
        mid = [(frm["lng"] + to["lng"]) / 2 - sign * dy / L * off_km / kx, (frm["lat"] + to["lat"]) / 2 + sign * dx / L * off_km / 111.32]
        pts = [[frm["lng"], frm["lat"]], mid, [to["lng"], to["lat"]]]
        dist = sum(haversine_km(a[1], a[0], b[1], b[0]) for a, b in zip(pts, pts[1:]))
        out.append({"source": "fallback", "label": name, "geojson": {"type": "LineString", "coordinates": pts},
                    "distance_km": round(dist, 3), "duration_min": round(dist / speed_kmh * 60, 1), "steps": []})
    return out
