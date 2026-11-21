"""Track B router (A-32, A-33): GET /api/map/transit (metro, suburban rail, OASA buses)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import transit_src

router = APIRouter()


@router.get("/api/map/transit")
def map_transit(
    bbox: str | None = Query(default=None, description="Optional WGS84 bbox: minLon,minLat,maxLon,maxLat"),
) -> dict:
    """Return metro/suburban lines & stations plus live OASA bus positions."""
    try:
        parsed_bbox = transit_src.parse_bbox(bbox)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return transit_src.get_transit(parsed_bbox)
