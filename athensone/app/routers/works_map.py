"""B2: GET /api/map/works, SPEC «Backend contracts» `GET /works` (A-33 path).

Reads the same works file as the existing /api/works/* routes (works.py: $STOA_WORKS_PATH, then
data/stoa/works.json from scripts/fetch_works.py, then the SEED file), so it never calls Διαύγεια or ΚΗΜΔΗΣ
at request time. Existing /api/works/* routes are untouched.
"""
from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, HTTPException, Query

from .. import config, map_reports, works, works_src

router = APIRouter()

STATUSES = ("planned", "in_progress", "completed")  # SPEC / B0 card: the allowed `status` values


def _bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    try:
        b = tuple(float(x) for x in raw.split(","))
    except ValueError:
        b = ()
    if len(b) != 4 or b[0] > b[2] or b[1] > b[3]:
        raise HTTPException(422, "bbox must be minLon,minLat,maxLon,maxLat")
    return b  # type: ignore[return-value]


def _open_reports() -> list[tuple[float, float]] | None:
    """Coordinates from open sandbox requests and unlinked map reports; None if the sandbox fails."""
    from .. import main  # imported here: app.main includes this router while it is still loading

    try:
        items = main.sb.list_requests(mine=True).get("items", [])
    except main.SandboxError:
        return None
    reports = [(r["lat"], r["lng"]) for r in items
               if r.get("status") in main.OPEN and r.get("lat") is not None and r.get("lng") is not None]
    # B12 counts linked reports through the sandbox only; the link identifies the same submission.
    reports.extend((r["lat"], r["lon"]) for r in map_reports.all_reports() if r["city_request_id"] is None)
    return reports


@router.get("/api/map/works")
def map_works(bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
              status: str | None = Query(None, description="planned | in_progress | completed")):
    box = _bbox(bbox)
    if status is not None and status not in STATUSES:
        raise HTTPException(422, f"status must be one of {', '.join(STATUSES)}")
    today = works.today().isoformat()
    reports = _open_reports()
    feats = []
    for card in works.all_cards():
        if box and not works_src.in_bbox(card["geometry"], box):
            continue
        f = works_src.map_feature(card, today, reports or [])
        if reports is None:
            f["properties"]["reports_count"] = None  # sandbox down: unknown, not 0
        if status and f["properties"]["status"] != status:
            continue
        feats.append(f)
    m = works.meta()
    # `source` is "snapshot": the works file is built by hand (fetch_works.py) or is the SEED set, never live.
    # `data_source` keeps the file's own label ("SEED" or the pipeline's) so the UI can show «SEED».
    return {"type": "FeatureCollection", "features": feats, "source": "snapshot", "data_source": m["source"],
            "updated_at": m["snapshot"], "note": m["note"]}


_ADA_RE = re.compile(r"^[A-Za-zΑ-Ωα-ω0-9-]{4,32}$")


@router.get("/api/map/works/lookup")
def map_works_lookup(ada: str = Query(..., description="Diavgeia ADA code")) -> dict:
    """Fetch live metadata for a single Diavgeia decision by ΑΔΑ."""
    code = ada.strip()
    if not _ADA_RE.match(code):
        raise HTTPException(400, "Invalid ΑΔΑ format")
    url = f"{config.DIAVGEIA_URL}/decisions/{code}"
    try:
        resp = httpx.get(url, headers={"Accept": "application/json"}, timeout=5.0)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Diavgeia upstream unavailable") from exc
    if resp.status_code == 404:
        raise HTTPException(404, f"ΑΔΑ {code} not found on Diavgeia")
    if resp.status_code >= 400:
        raise HTTPException(502, f"Diavgeia returned HTTP {resp.status_code}")
    data = resp.json()
    return {
        "ada": data.get("ada") or code,
        "subject": data.get("subject"),
        "decision_type_id": data.get("decisionTypeId"),
        "issue_date": data.get("issueDate"),
        "organization_id": data.get("organizationId"),
        "document_url": data.get("documentUrl") or f"https://diavgeia.gov.gr/decision/view/{code}",
        "source": "live",
    }
