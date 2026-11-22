"""B13 router: GET /api/map/services?category= (official registry service for a report category).

Auto-discovered by app/main.py via app/routers/ (A-32).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import categories, service_guide
from ..sandbox import SandboxError

router = APIRouter()


@router.get("/api/map/services")
def map_services(category: str):
    """The registry service for one sandbox category. 422 unknown category; 503 sandbox down (api.js then uses
    web/mock/services.json)."""
    if category not in categories.SANDBOX:
        raise HTTPException(status_code=422, detail=f"unknown category: {category}")
    from ..main import sb  # late import: app.main imports this module while it starts (same as map_reports.py)
    try:
        return service_guide.guide(sb, category)
    except SandboxError as exc:
        raise HTTPException(status_code=503, detail="sandbox unavailable") from exc
