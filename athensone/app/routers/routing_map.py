"""B9: POST /api/map/routing (SPEC «Backend contracts» POST /routing, path per A-33).

I/O only: read the layers the map shows (works, reports, env, City air station), ask routing.candidates()
for routes as /api/navigate does, and let app/route_cost.py pick one per profile and explain why.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from .. import ckan, env, envgrid_src, map_reports, route_cost, routing, store, works
from ..sandbox import SandboxError

router = APIRouter()

# Same bbox padding as /api/navigate (app/main.py: pad 0.004 deg, ~400 m; sure it matches).
PAD_DEG = 0.004


class RoutingRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    frm: list[float] = Field(alias="from", min_length=2, max_length=2)  # [lon, lat]
    to: list[float] = Field(min_length=2, max_length=2)  # [lon, lat]
    profile: Literal["wheelchair", "stroller", "cool"]


class CarRoutingRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    frm: list[float] = Field(alias="from", min_length=2, max_length=2)
    to: list[float] = Field(min_length=2, max_length=2)


def _open_reports() -> list[dict]:
    """Read route hazards from legacy reports and map reports, using sandbox status for City requests."""
    from .. import main  # lazy: main imports this module at the end of its own import

    try:
        status = {r["id"]: r["status"] for r in main.sb.list_requests(mine=True).get("items", [])}
    except SandboxError:
        status = {}
    # Legacy reports keep main.active_hazards()'s default for unknown City request statuses.
    reports = [{"id": r["request_id"], "lat": r["lat"], "lng": r["lng"], "category": r["category"],
                "blocker": r["accessibility_blocker"]}
               for r in store.all_reports()
               if r["lat"] is not None and r["lng"] is not None and status.get(r["request_id"], "submitted") in main.OPEN]
    for row in map_reports.all_reports():
        if row["city_request_id"] is not None and status.get(row["city_request_id"], "submitted") not in main.OPEN:
            continue
        # B12 defines obstacle as a blocker and congestion as soft (see SOFT_REPORT_CATEGORIES).
        reports.append({"id": row["id"], "lat": row["lat"], "lng": row["lon"], "category": row["category"],
                        "blocker": row["category"] == "obstacle"})
    return reports


def _in_bbox(line: list, bbox: tuple) -> bool:
    return any(bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3] for x, y in line)


def _nearest_env_sample(lon: float, lat: float, bbox: tuple, air: dict | None) -> dict:
    """Pick real microclimate values (temp_c, aqi, uv_index) near route midpoint without inventing numbers."""
    out: dict = {"aqi": (air or {}).get("aqi"), "temp_c": None, "uv_index": None}
    try:
        grid = envgrid_src.get_env_grid(bbox)
        feats = grid.get("features") or []
        if not feats:
            grid = envgrid_src.get_env_grid(None)
            feats = grid.get("features") or []
        best_props = None
        best_d2 = float("inf")
        for f in feats:
            coords = (f.get("geometry") or {}).get("coordinates")
            if not isinstance(coords, list) or len(coords) < 2:
                continue
            d2 = (coords[0] - lon) ** 2 + (coords[1] - lat) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_props = f.get("properties") or {}
        if best_props:
            if out["aqi"] is None and best_props.get("aqi") is not None:
                out["aqi"] = best_props.get("aqi")
            if best_props.get("temp_c") is not None:
                out["temp_c"] = best_props.get("temp_c")
            if best_props.get("uv_index") is not None:
                out["uv_index"] = best_props.get("uv_index")
    except Exception:
        pass
    return out


@router.post("/api/map/routing")
def map_routing(req: RoutingRequest) -> dict:
    return _compute_route(req.frm, req.to, req.profile)


@router.post("/api/map/routing/car")
def map_routing_car(req: CarRoutingRequest) -> dict:
    return _compute_route(req.frm, req.to, "car")


def _compute_route(req_frm: list[float], req_to: list[float], profile: str) -> dict:
    (flng, flat), (tlng, tlat) = req_frm, req_to
    frm, to = {"lat": flat, "lng": flng}, {"lat": tlat, "lng": tlng}
    bbox = (min(flng, tlng) - PAD_DEG, min(flat, tlat) - PAD_DEG, max(flng, tlng) + PAD_DEG, max(flat, tlat) + PAD_DEG)
    costing = route_cost.COSTING[profile]

    today = works.today()
    live_works = [w for w in works.all_cards()
                  if route_cost.in_progress(w, today) and _in_bbox(w["geometry"]["coordinates"], bbox)]
    reports = _open_reports()
    blockers = [r for r in reports if r["blocker"]]
    soft = [r for r in reports if r["blocker"] or r["category"] in route_cost.SOFT_REPORT_CATEGORIES]
    hazards = [{"id": r["id"], "lat": r["lat"], "lng": r["lng"], "category": r["category"]} for r in blockers]

    if profile == "wheelchair":
        # hard: send works to Valhalla as excluded locations + avoid polygons, then filter in route_cost
        hz = hazards + [route_cost.work_point(w["geometry"]["coordinates"]) for w in live_works]
        polys = [p for w in live_works for p in route_cost.work_polygons(w["geometry"]["coordinates"])] or None
        hard_works, hard_reports, soft_works, soft_reports, reason_reports = live_works, blockers, [], [], blockers
    elif profile == "car":
        # car: avoid roadworks & congestion reports softly, prefer less congested arteries
        hz = hazards
        polys = [p for w in live_works for p in route_cost.work_polygons(w["geometry"]["coordinates"])] or env.busy_polygons(bbox) or None
        hard_works, hard_reports = [], []
        soft_works, soft_reports = live_works, soft
        reason_reports = soft_reports
    else:
        # stroller and cool: like /api/navigate with air=True (busy-road avoid polygons); works/reports are soft
        hz = hazards
        polys = env.busy_polygons(bbox) or None
        hard_works, hard_reports = [], []
        soft_works, soft_reports = (live_works, soft) if profile == "stroller" else ([], [])
        reason_reports = soft_reports

    cands = [dict(c) for c in routing.candidates(frm, to, hz, costing, polys)]
    # the plain shortest route (no exclusions) is what `reasons` compare against
    plain = routing.candidates(frm, to, [], costing, None)
    baseline = min(plain, key=lambda c: c["distance_km"]) if plain else None

    mid_lon, mid_lat = (flng + tlng) / 2, (flat + tlat) / 2
    air = ckan.nearest_air(mid_lat, mid_lon)
    env_sample = _nearest_env_sample(mid_lon, mid_lat, bbox, air)
    best = route_cost.choose(profile, cands, hard_works, hard_reports, soft_works, soft_reports,
                             env_sample.get("aqi"))
    why = route_cost.reasons(profile, best, baseline, hard_works or soft_works, reason_reports)
    comparison = route_cost.compare(profile, best, baseline, live_works, soft, env_sample)

    best_metrics = best.get("metrics") or {}
    busy_pct = int(best_metrics.get("busy_pct", 0) or 0)
    congestion_hits = len([r for r in soft if r.get("category") == "congestion"])
    traffic_level = "heavy" if busy_pct >= 55 or congestion_hits >= 2 else ("moderate" if busy_pct >= 25 or congestion_hits >= 1 or len(live_works) >= 2 else "low")
    delay_min = round(best["duration_min"] * (0.35 if traffic_level == "heavy" else (0.18 if traffic_level == "moderate" else 0.05)), 1) if profile == "car" else 0

    return {
        "geometry": best["geojson"],
        "distance_m": round(best["distance_km"] * 1000),
        "duration_s": round((best["duration_min"] + delay_min) * 60),
        "legs": [{"mode": "car" if profile == "car" else "walk"}],
        "reasons": why,
        "comparison": comparison,
        "traffic": {
            "level": traffic_level,
            "delay_min": delay_min,
            "busy_pct": busy_pct,
            "congestion_reports": congestion_hits,
            "works_nearby": len(live_works),
        },
        # extra keys (not in the SPEC contract): where the line came from, so the UI can label a fallback
        "source": best["source"],
        "label": best.get("label"),
        "env": env.meta(),
        # A-40 (additive): the wheelchair route still touches a hard blocker because no candidate avoids them
        # all. `_hard` is set by route_cost.choose with the same "touches" test; other profiles have no blockers.
        "blocked": profile == "wheelchair" and bool(best.get("_hard")),
    }
