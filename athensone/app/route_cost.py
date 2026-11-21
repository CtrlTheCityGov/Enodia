"""B9: route cost per profile (SPEC «Routing», F5). Pure functions, no I/O.

The router (app/routers/routing_map.py) fetches candidates with routing.candidates() and the map layers
(works, reports, env); this module decides which candidate each profile prefers and why.

  wheelchair  hard: never a candidate that touches an in-progress work or an open obstacle report, if any
              candidate avoids them all. Kerbs/ramps/steps come from Valhalla's wheelchair costing.
  stroller    soft: in-progress works and open congestion/obstacle reports add a penalty; busy roads
              (traffic exhaust proxy) weigh more when the City's AQI is poor.
  cool        shade weighted as in /api/navigate heat mode; busy roads (high-PM2.5 proxy) penalised.
              B5's grid (app.envgrid_src) is not on dev-b yet, so this uses env.score_line (trees/parks).

`reasons` compare the chosen route with the plain shortest one (no exclusions) and name what changed it.
"""
from __future__ import annotations

import math
from datetime import date

from . import env, works_src

# Same metres-per-degree constant as app/env.py and app/works.py (equirectangular, fine at city scale; sure).
K = 111_320.0
# A route "touches" a feature when it comes within 20 m of it: the same radius env.score_line uses for
# hazards_on_route (app/env.py; sure it matches, the value itself is a judgement call from the old code).
TOUCH_M = 20.0
# Half-width of the avoid polygon around a work line for Valhalla exclude_polygons: 15 m, about a street
# width plus pavement (guess, unverified; env.busy_polygons uses 18 m for busy roads).
WORK_HALF_WIDTH_M = 15.0
# Longest acceptable detour: 1.4x the fastest candidate, copied from /api/navigate max_detour (app/main.py; sure).
MAX_DETOUR = 1.4
# Shade and busy-road weights copied from /api/navigate (app/main.py: ws 1.2 when hot, wa 1.2 when AQI >= 4
# else 0.8; sure they match navigate). Cool always uses the hot shade weight (SPEC alias table: cool ≈ heat+shade).
SHADE_W_COOL = 1.2
BUSY_W_POOR_AIR, BUSY_W = 1.2, 0.8
POOR_AQI = 4  # same threshold as /api/navigate (app/main.py: aqi >= 4 on the 1-6 scale; sure it matches)
# Stroller soft penalty: +30% of the duration per work/report touched (guess, unverified; small enough that a
# 3x detour never wins, large enough to beat a few minutes' detour).
SOFT_PENALTY = 0.3
# SPEC Routing treats congestion as a stroller penalty; B12 and map_reports.CATEGORIES confirm the stored key.
SOFT_REPORT_CATEGORIES = {"congestion"}

PROFILES = ("wheelchair", "stroller", "cool")
# Valhalla pedestrian costing used per profile (keys of routing.PROFILES; SPEC table: cool does not exclude steps).
COSTING = {"wheelchair": "wheelchair", "stroller": "stroller", "cool": "walk"}


# ------------------------------------------------------------------ geometry
def _densify(coords: list, step_m: float = 8.0) -> list[tuple[float, float]]:
    """Points every ~step_m along a [[lng, lat], ...] line."""
    out: list[tuple[float, float]] = []
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        kx = K * math.cos(math.radians(y1))
        n = max(1, int(math.hypot((x2 - x1) * kx, (y2 - y1) * K) / step_m))
        out += [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n)]
    if coords:
        out.append((coords[-1][0], coords[-1][1]))
    return out


def _point_line_m(lng: float, lat: float, line: list) -> float:
    """Distance in metres from a point to a [[lng, lat], ...] polyline."""
    kx = K * math.cos(math.radians(lat))
    px, py = lng * kx, lat * K
    pts = [(x * kx, y * K) for x, y in line]
    best = float("inf")
    for (ax, ay), (bx, by) in zip(pts, pts[1:] or pts):
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def touches_line(route: list, line: list, radius_m: float = TOUCH_M) -> bool:
    """True if the route passes within radius_m of any point of the line (both [[lng, lat], ...])."""
    return any(_point_line_m(x, y, route) <= radius_m for x, y in _densify(line))


def touches_point(route: list, lng: float, lat: float, radius_m: float = TOUCH_M) -> bool:
    return _point_line_m(lng, lat, route) <= radius_m


def work_polygons(line: list, half_width_m: float = WORK_HALF_WIDTH_M) -> list[list[list[float]]]:
    """Closed rectangles around each segment of a work line, for Valhalla exclude_polygons."""
    out = []
    for (x1, y1), (x2, y2) in zip(line, line[1:]):
        kx = K * math.cos(math.radians(y1))
        dx, dy = (x2 - x1) * kx, (y2 - y1) * K
        length = math.hypot(dx, dy) or 1
        ox, oy = -dy / length * half_width_m / kx, dx / length * half_width_m / K
        out.append([[x1 + ox, y1 + oy], [x2 + ox, y2 + oy], [x2 - ox, y2 - oy], [x1 - ox, y1 - oy], [x1 + ox, y1 + oy]])
    return out


def work_point(line: list) -> dict:
    """One {lat, lng} on the work (its middle vertex), passed to Valhalla as an exclude_location."""
    x, y = line[len(line) // 2] if len(line) > 2 else ((line[0][0] + line[-1][0]) / 2, (line[0][1] + line[-1][1]) / 2)
    return {"lat": y, "lng": x}


# ------------------------------------------------------------------ layer filters
def in_progress(work: dict, today: date) -> bool:
    """Use B2 status for evidence-wrapped works and the legacy status and end date for flat records."""
    end = work.get("end_date")
    if isinstance(work.get("start_date"), dict) or isinstance(end, dict):
        # B12 delegates to B2's status_of so routing and the works layer agree.
        return works_src.status_of(work, today.isoformat()) == "in_progress"
    if work.get("status") != "in_progress":
        return False
    try:
        return not end or date.fromisoformat(end) >= today
    except ValueError:
        return True  # unreadable end date: treat as still in progress (safer for a wheelchair user)


# ------------------------------------------------------------------ scoring
def _hits(coords: list, works_list: list[dict], reports: list[dict]) -> tuple[list[dict], list[dict]]:
    w = [x for x in works_list if touches_line(coords, x["geometry"]["coordinates"])]
    r = [x for x in reports if touches_point(coords, x["lng"], x["lat"])]
    return w, r


def choose(profile: str, cands: list[dict], hard_works: list[dict], hard_reports: list[dict],
           soft_works: list[dict], soft_reports: list[dict], aqi: int | None) -> dict:
    """Pick the best candidate for the profile. Adds `metrics`, `score`, `_hits` to each candidate."""
    busy_w = BUSY_W_POOR_AIR if (aqi or 0) >= POOR_AQI else BUSY_W
    for c in cands:
        co = c["geojson"]["coordinates"]
        m = env.score_line(co) or {"shade_pct": 0, "busy_pct": 0}
        hw, hr = _hits(co, hard_works, hard_reports)
        sw, sr = _hits(co, soft_works, soft_reports)
        c["metrics"], c["_hard"], c["_soft"] = m, hw + hr, sw + sr
        d = c["duration_min"]
        if profile == "wheelchair":
            c["score"] = d
        elif profile == "stroller":
            c["score"] = d * (1 + SOFT_PENALTY * len(c["_soft"]) + busy_w * m["busy_pct"] / 100)
        else:  # cool
            c["score"] = d * (1 + SHADE_W_COOL * (1 - m["shade_pct"] / 100) + busy_w * m["busy_pct"] / 100)
    pool = [c for c in cands if not c["_hard"]] or cands  # hard rule first; if nothing is clear, keep all
    fastest = min(c["duration_min"] for c in pool)
    ok = [c for c in pool if c["duration_min"] <= fastest * MAX_DETOUR] or pool
    return min(ok, key=lambda c: c["score"])


def reasons(profile: str, best: dict, baseline: dict | None, works_list: list[dict], reports: list[dict]) -> list[dict]:
    """What the chosen route avoids versus the plain shortest one. Empty when they are the same line."""
    if baseline is None or best["geojson"]["coordinates"] == baseline["geojson"]["coordinates"]:
        return []
    bco, sco = best["geojson"]["coordinates"], baseline["geojson"]["coordinates"]
    out = []
    for w in works_list:
        line = w["geometry"]["coordinates"]
        if touches_line(sco, line) and not touches_line(bco, line):
            street = (w.get("street") or {}).get("value")
            out.append({"text": "αποφεύγει έργο σε εξέλιξη" + (f" ({street})" if street else ""),
                        "layer": "works", "feature_id": w["id"]})
    for r in reports:
        if touches_point(sco, r["lng"], r["lat"]) and not touches_point(bco, r["lng"], r["lat"]):
            text = "αποφεύγει σημείο συμφόρησης" if r.get("category") in SOFT_REPORT_CATEGORIES \
                else "αποφεύγει αναφερμένο εμπόδιο"
            out.append({"text": text, "layer": "reports", "feature_id": r["id"]})
    if profile in ("stroller", "cool"):
        b = best.get("metrics") or env.score_line(bco)
        s = env.score_line(sco)
        if profile == "cool" and b.get("shade_pct", 0) > s.get("shade_pct", 0):
            out.append({"text": f"περισσότερη σκιά: {b['shade_pct']}% αντί {s['shade_pct']}%",
                        "layer": "env", "feature_id": "shade"})
        if b.get("busy_pct", 0) < s.get("busy_pct", 0):
            out.append({"text": f"λιγότερο δίπλα σε δρόμους με κίνηση: {b['busy_pct']}% αντί {s['busy_pct']}%",
                        "layer": "env", "feature_id": "busy_road"})
    return out


def _work_ada(work: dict) -> str | None:
    """Extract the first cited ADA from a works card, or None."""
    for field in ("street", "title", "contractor", "amount_paid_eur"):
        val = work.get(field)
        if isinstance(val, dict):
            src = val.get("source")
            if isinstance(src, dict) and src.get("ada"):
                return str(src["ada"])
    return None


def compare(
    profile: str,
    best: dict,
    baseline: dict | None,
    works_list: list[dict],
    reports: list[dict],
    env_sample: dict | None = None,
) -> dict:
    """Build structured best-vs-baseline comparison metrics and avoided hazards for HUD/AI explanations."""
    bco = best["geojson"]["coordinates"]
    best_m = best.get("metrics") or env.score_line(bco) or {"shade_pct": 0, "busy_pct": 0}
    best_dist_m = round(best["distance_km"] * 1000)
    best_dur_s = round(best["duration_min"] * 60)

    best_works_hits, best_report_hits = _hits(bco, works_list, reports)

    same_as_baseline = baseline is None or bco == baseline["geojson"]["coordinates"]
    baseline_block = None
    avoided_works: list[dict] = []
    avoided_reports: list[dict] = []

    if baseline is not None:
        sco = baseline["geojson"]["coordinates"]
        base_m = env.score_line(sco) or {"shade_pct": 0, "busy_pct": 0}
        base_dist_m = round(baseline["distance_km"] * 1000)
        base_dur_s = round(baseline["duration_min"] * 60)
        baseline_block = {
            "geometry": baseline["geojson"],
            "distance_m": base_dist_m,
            "duration_s": base_dur_s,
            "shade_pct": int(base_m.get("shade_pct", 0)),
            "busy_pct": int(base_m.get("busy_pct", 0)),
        }
        if not same_as_baseline:
            for w in works_list:
                line = w["geometry"]["coordinates"]
                if touches_line(sco, line) and not touches_line(bco, line):
                    pt = work_point(line)
                    street_obj = w.get("street")
                    title_obj = w.get("title")
                    avoided_works.append({
                        "id": w["id"],
                        "street": street_obj.get("value") if isinstance(street_obj, dict) else street_obj,
                        "title": title_obj.get("value") if isinstance(title_obj, dict) else title_obj,
                        "ada": _work_ada(w),
                        "lon": pt["lng"],
                        "lat": pt["lat"],
                    })
            for r in reports:
                if touches_point(sco, r["lng"], r["lat"]) and not touches_point(bco, r["lng"], r["lat"]):
                    avoided_reports.append({
                        "id": r["id"],
                        "category": r.get("category") or "obstacle",
                        "lon": r["lng"],
                        "lat": r["lat"],
                    })
    else:
        base_m = best_m
        base_dist_m = best_dist_m
        base_dur_s = best_dur_s

    sample = env_sample or {}
    return {
        "profile": profile,
        "same_as_baseline": same_as_baseline,
        "baseline": baseline_block,
        "best": {
            "shade_pct": int(best_m.get("shade_pct", 0)),
            "busy_pct": int(best_m.get("busy_pct", 0)),
            "steps_excluded": profile in ("wheelchair", "stroller"),
        },
        "deltas": {
            "distance_m": best_dist_m - base_dist_m,
            "duration_s": best_dur_s - base_dur_s,
            "shade_pct": int(best_m.get("shade_pct", 0)) - int(base_m.get("shade_pct", 0)),
            "busy_pct": int(best_m.get("busy_pct", 0)) - int(base_m.get("busy_pct", 0)),
        },
        "env": {
            "aqi": sample.get("aqi"),
            "temp_c": sample.get("temp_c"),
            "uv_index": sample.get("uv_index"),
        },
        "avoided_works": avoided_works,
        "avoided_reports": avoided_reports,
        "on_route_works": len(best_works_hits),
        "on_route_reports": len(best_report_hits),
    }
