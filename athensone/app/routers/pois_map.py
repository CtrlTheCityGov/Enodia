"""B14: GET /api/map/pois, the City's own POIs (sandbox /v1/pois) as an official map layer (SPEC F2 layers).

One sandbox call per category around the bbox centre; the answer is a GeoJSON FeatureCollection with every
feature marked `official: true`. Existing callers of sb.pois (cool places, envgrid) are untouched.
"""
from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException, Query

from .. import config
from ..geo import haversine_km
from .works_map import _bbox

router = APIRouter()

# The two sandbox categories verified to exist (card B14; already used by cool places / envgrid). Certainty: verified.
DEFAULT_CATEGORIES = "friendship_club,library"
# No bbox → Σύνταγμα [lon, lat], 3 km (card B14). Certainty: card value; coordinates are Σύνταγμα square.
DEFAULT_CENTER = (23.7348, 37.9755)
DEFAULT_RADIUS_KM = 3.0
# Upper bound on the sandbox search radius (card B14). Certainty: card value, not a sandbox limit we checked.
MAX_RADIUS_KM = 5.0
# Items per category per call (card B14). Certainty: card value.
PAGE_SIZE = 50
# Max categories per call: each costs one sandbox call (100 req/min limit). Our choice (B14 fix round).
MAX_CATEGORIES = 5


def _circle(box: tuple[float, float, float, float] | None) -> tuple[float, float, float]:
    """(lon, lat, radius_km): bbox centre and half its diagonal, capped; or the Σύνταγμα default."""
    if box is None:
        return DEFAULT_CENTER[0], DEFAULT_CENTER[1], DEFAULT_RADIUS_KM
    min_lon, min_lat, max_lon, max_lat = box
    lon, lat = (min_lon + max_lon) / 2, (min_lat + max_lat) / 2
    half_diag = haversine_km(min_lat, min_lon, max_lat, max_lon) / 2
    return lon, lat, min(half_diag, MAX_RADIUS_KM)


def _feature(p: dict, lon: float, lat: float, source: str) -> dict:
    dist = p.get("distance_km")
    if not isinstance(dist, (int, float)) or isinstance(dist, bool):  # missing or not a number: compute it ourselves
        dist = round(haversine_km(lat, lon, p["lat"], p["lng"]), 3)
    props = {"id": p["id"], "name": p.get("name"), "category": p.get("category"), "address": p.get("address"),
             "open_now": p.get("open_now"), "distance_km": dist, "source": source, "official": True}
    return {"type": "Feature", "id": p["id"], "geometry": {"type": "Point", "coordinates": [p["lng"], p["lat"]]},
            "properties": props}


@router.get("/api/map/pois")
def map_pois(categories: str = Query(DEFAULT_CATEGORIES, description="comma-separated sandbox categories"),
             bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat")):
    from .. import main  # imported here: app.main includes this router while it is still loading

    lon, lat, radius = _circle(_bbox(bbox))
    cats = list(dict.fromkeys(c.strip() for c in categories.split(",") if c.strip()))
    if len(cats) > MAX_CATEGORIES:
        raise HTTPException(422, f"at most {MAX_CATEGORIES} categories")
    source = "mock" if config.MOCK else "sandbox"
    feats: dict[str, dict] = {}
    errors: list[str] = []
    for cat in cats:
        try:
            items = main.sb.pois(category=cat, lat=lat, lng=lon, radius_km=radius, size=PAGE_SIZE).get("items", [])
        except main.SandboxError:
            errors.append(cat)
            continue
        for p in items:
            if p.get("id") is None or p["id"] in feats:
                continue
            try:
                p = {**p, "lat": float(p["lat"]), "lng": float(p["lng"])}
            except (KeyError, TypeError, ValueError):
                continue  # missing or non-numeric coordinates: untrusted upstream data, skip the POI
            if not (math.isfinite(p["lat"]) and math.isfinite(p["lng"])):
                continue
            feats[p["id"]] = _feature(p, lon, lat, source)
    if cats and len(errors) == len(cats):
        raise HTTPException(503, "sandbox unavailable for every POI category")
    ordered = sorted(feats.values(), key=lambda f: f["properties"]["distance_km"])
    return {"type": "FeatureCollection", "features": ordered, "errors": errors}
