"""B4 router: GET /api/map/health (on-duty pharmacies and hospitals, SPEC F2 & A-33).

Leaves existing GET /api/health (server status) completely unchanged.
Auto-discovered by app/main.py via app/routers/ (A-32).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import onduty_src

router = APIRouter()


@router.get("/api/map/health")
def map_health(date: str | None = None):
    """Return on-duty pharmacies and central-Athens hospitals as a GeoJSON FeatureCollection."""
    try:
        return onduty_src.get_onduty(date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
