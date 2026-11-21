"""B5 router: GET /api/map/env — temperature and AQI grid over the Municipality of Athens."""
from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import envgrid_src

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
    """Serve the environmental grid (temp_c, aqi, pm25, updated_at) in SPEC GET /env GeoJSON shape."""
    parsed_bbox = parse_bbox(bbox) if bbox else None
    return envgrid_src.get_env_grid(parsed_bbox)
