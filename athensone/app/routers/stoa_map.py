"""B8: `POST /api/map/stoa_ask` (SPEC contract `POST /stoa_ask`, path per A-33). Logic lives in app/stoa_map.py."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import config, stoa_map

router = APIRouter()


class StoaAskIn(BaseModel):
    question: str = Field(max_length=500)  # a chat question; 500 chars is a generous cap, implementer's choice
    # [lon, lat] of the map centre (SPEC). Missing -> the demo start point (app/config.py DEMO_START).
    center: list[float] = Field(
        default_factory=lambda: [config.DEMO_START["lng"], config.DEMO_START["lat"]], min_length=2, max_length=2
    )
    history: list = Field(default_factory=list)  # accepted for the contract; the rule router does not use it


@router.post("/api/map/stoa_ask")
def stoa_ask_map(body: StoaAskIn) -> dict:
    out = stoa_map.answer(body.question, body.center, body.history)
    out.setdefault("source", "mock" if config.MOCK else "live")
    out.setdefault("updated_at", datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
    return out
