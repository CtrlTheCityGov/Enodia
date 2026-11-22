"""B15: GET /api/map/resolved, the «Διορθώθηκαν κοντά σου» layer (SPEC F5, closing the loop).

Requests the City sandbox marks `resolved`, with how long each took. Only coarse, non-personal fields leave this
route: no title, description, address, note, history, photo or `created_by_you`; coordinates rounded to ~10 m.
`/api/equity` (per-district stats) is separate and not touched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import statistics

from fastapi import APIRouter, HTTPException, Query

from .. import categories, works
from ..geo import haversine_km
from ..sandbox import SandboxError

router = APIRouter()

# No bbox: Σύνταγμα, 3 km (B14 card rule). Coordinates from the B14 card; certainty: verified on the map by the card.
SYNTAGMA = (37.9755, 23.7348)  # (lat, lng)
DEFAULT_RADIUS_KM = 3.0
# Radius cap for a bbox, same as B14 card. Our choice, keeps one sandbox call small.
MAX_RADIUS_KM = 5.0
# One sandbox page (card: size=100). Certainty: card.
PAGE_SIZE = 100
# 4 decimals ≈ 11 m of latitude: SPEC privacy «~10 m». Certainty: verified arithmetic.
COORD_DECIMALS = 4


def _centre_radius(raw: str | None) -> tuple[float, float, float]:
    """bbox "minLon,minLat,maxLon,maxLat" -> (lat, lng, radius_km): centre and half the diagonal, capped at 5 km."""
    if not raw:
        return SYNTAGMA[0], SYNTAGMA[1], DEFAULT_RADIUS_KM
    try:
        b = tuple(float(x) for x in raw.split(","))
    except ValueError:
        b = ()
    if len(b) != 4 or not all(math.isfinite(x) for x in b) or b[0] > b[2] or b[1] > b[3]:
        raise HTTPException(422, "bbox must be minLon,minLat,maxLon,maxLat")
    lat, lng = (b[1] + b[3]) / 2, (b[0] + b[2]) / 2
    radius = haversine_km(b[1], b[0], b[3], b[2]) / 2
    return lat, lng, min(radius, MAX_RADIUS_KM)


def _parse(ts) -> datetime | None:
    """ISO 8601 (with Z or an offset) -> aware datetime; None if missing or unparsable.
    A timestamp without offset is read as UTC (the sandbox writes UTC; unverified for the live sandbox)."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _resolved_at(req: dict) -> str | None:
    """The `at` of the first history entry with status resolved, else `updated_at` (card)."""
    for h in req.get("history") or []:
        if isinstance(h, dict) and h.get("status") == "resolved" and h.get("at"):
            return h["at"]
    return req.get("updated_at")


def _hours(created: str | None, resolved: str | None) -> float | None:
    a, b = _parse(created), _parse(resolved)
    if a is None or b is None or b < a:  # resolved before created: inconsistent data, unknown rather than negative
        return None
    return round((b - a).total_seconds() / 3600, 1)


def _feature(req: dict, resolved_at: str) -> dict:
    lat = round(float(req["lat"]), COORD_DECIMALS)
    lng = round(float(req["lng"]), COORD_DECIMALS)
    cat = req.get("category") or "other"
    props = {
        "id": req.get("id"),
        "category": cat,
        "label_el": categories.LABEL_EL.get(cat, cat),
        "resolved_at": resolved_at,
        "hours_to_resolve": _hours(req.get("created_at"), resolved_at),
        "district_name": req.get("district"),
    }
    return {"type": "Feature", "id": props["id"], "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": props}


@router.get("/api/map/resolved")
def list_resolved(bbox: str | None = None, days: int = Query(30, ge=1, le=365)):
    from ..main import sb  # imported here: app.main includes this router while it is still loading

    lat, lng, radius_km = _centre_radius(bbox)
    try:
        items = sb.list_requests(status="resolved", lat=lat, lng=lng, radius_km=radius_km,
                                 size=PAGE_SIZE).get("items", [])
    except SandboxError:
        raise HTTPException(503, "City sandbox unavailable")
    cutoff = works.today() - timedelta(days=days)
    features = []
    for req in items:
        if req.get("status") != "resolved" or req.get("lat") is None or req.get("lng") is None:
            continue
        resolved_at = _resolved_at(req)
        when = _parse(resolved_at)
        if when is None or when.date() < cutoff:
            continue  # outside the window, or no usable date to place it in the window
        try:
            feat = _feature(req, resolved_at)
        except (TypeError, ValueError):
            continue  # non-numeric lat/lng from the sandbox (untrusted upstream data): skip, never 500
        if not all(math.isfinite(c) for c in feat["geometry"]["coordinates"]):
            continue
        features.append(feat)
    hours = [f["properties"]["hours_to_resolve"] for f in features
             if f["properties"]["hours_to_resolve"] is not None]
    return {
        "type": "FeatureCollection",
        "source": "mock" if sb.mock else "sandbox",  # A-39: label mock-sandbox data so the UI shows «δοκιμαστικό»
        "features": features,
        "summary": {"count": len(features),
                    "median_hours_to_resolve": round(statistics.median(hours), 1) if hours else None},
    }
