"""B5 router: GET /api/map/env — temperature and AQI grid over the Municipality of Athens."""
from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import config, env, envgrid_src
from ..sandbox import SandboxError

router = APIRouter()

# Number of comma-separated floats in SPEC bbox query parameter (minLon,minLat,maxLon,maxLat)
# (source: docs/SPEC.md Backend contracts GET /env; certainty: sure).
BBOX_PARTS = 4


def parse_bbox(raw: str) -> tuple[float, float, float, float]:
    """Parse 'minLon,minLat,maxLon,maxLat' into a validated 4-float tuple."""
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != BBOX_PARTS:
        raise HTTPException(status_code=422, detail="bbox must be minLon,minLat,maxLon,maxLat")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="bbox coordinates must be numeric") from exc
    if not all(math.isfinite(v) for v in (min_lon, min_lat, max_lon, max_lat)):
        raise HTTPException(status_code=422, detail="bbox coordinates must be finite numbers")
    if min_lon > max_lon or min_lat > max_lat:
        raise HTTPException(status_code=422, detail="bbox min values must not exceed max values")
    return (min_lon, min_lat, max_lon, max_lat)


@router.get("/api/map/env")
def map_env(bbox: str | None = None) -> dict[str, Any]:
    """Serve the environmental grid (temp_c, aqi, pm25, uv_index, updated_at) in SPEC GET /env GeoJSON shape."""
    parsed_bbox = parse_bbox(bbox) if bbox else None
    return envgrid_src.get_env_grid(parsed_bbox)


@router.get("/api/map/cool-spots")
def map_cool_spots(
    lat: float = config.DEMO_START["lat"],
    lng: float = config.DEMO_START["lng"],
    radius_km: float = 3.0,
) -> dict[str, Any]:
    """Serve municipal cool spaces (friendship clubs, libraries) and OSM hydration/rest spots as GeoJSON."""
    from .. import main  # lazy: main imports this router at module import time

    features: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float]] = set()
    for category, kind_el in (("friendship_club", "Λέσχη Φιλίας (κλιματιζόμενος χώρος)"), ("library", "Δημοτική Βιβλιοθήκη")):
        try:
            items = main.sb.pois(category=category, lat=lat, lng=lng, radius_km=radius_km).get("items", [])
        except SandboxError:
            items = []
        for it in items:
            plat, plng = it.get("lat"), it.get("lng")
            name = it.get("name")
            if not isinstance(plat, (int, float)) or not isinstance(plng, (int, float)) or not name:
                continue
            key = (str(name), round(float(plng), 5), round(float(plat), 5))
            if key in seen:
                continue
            seen.add(key)
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(plng), float(plat)]},
                "properties": {
                    "name": name,
                    "kind": kind_el,
                    "category": category,
                    "address": it.get("address"),
                    "source": "mock" if config.MOCK else "AthensGov",
                },
            })
    return {
        "type": "FeatureCollection",
        "features": features,
        "env_meta": env.meta(),
    }
