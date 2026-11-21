"""B6: map reports («+» flow) with the SPEC contract shapes, under /api/map/ (A-33).

POST /api/map/reports               multipart category, lon, lat, note, work_id?, photo?
GET  /api/map/reports?bbox=&since=  GeoJSON points: id, category, created_at, confirmations
POST /api/map/reports/{id}/confirm  confirmations + 1, +2 to the confirmer (not the author, once per account)
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile

from .. import ckan, config, map_reports, points, privacy
from ..sandbox import SandboxError

router = APIRouter()

# Max photo upload, same as the existing POST /api/report in app/main.py. Certainty: verified (copied).
MAX_PHOTO_BYTES = 15 * 1024 * 1024


def _sandbox():
    """The app's Sandbox client, imported late because app.main imports this module while it starts."""
    from ..main import sb

    return sb


def _city_request(category: str, lon: float, lat: float, note: str, photo_url: str | None) -> str:
    """Create the City request for an obstacle/damage map report, as POST /api/report does. No token in it."""
    label = map_reports.CATEGORIES[category]
    desc = f"Αναφορά από τον χάρτη: {label}\nΣχόλιο πολίτη: {note or '-'}"
    if photo_url:
        desc += f"\nΦωτογραφία (θολωμένα πρόσωπα και πινακίδες): {photo_url}"
    req = _sandbox().create_request(category=map_reports.CITY_CATEGORIES[category], title=f"{label} (αναφορά χάρτη)",
                                    address=f"{lat:.4f}, {lon:.4f}", description=desc, lat=lat, lng=lon)
    return req["id"]


@router.post("/api/map/reports")
async def create_map_report(
    request: Request,
    response: Response,
    category: str = Form(...),
    lon: float = Form(..., ge=-180, le=180),
    lat: float = Form(..., ge=-90, le=90),
    note: str = Form(""),
    work_id: str | None = Form(None),
    photo: UploadFile | None = File(None),
):
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise HTTPException(422, "lon and lat must be finite numbers")
    if category not in map_reports.CATEGORIES:
        raise HTTPException(422, f"unknown category; expected one of {', '.join(map_reports.CATEGORIES)}")
    name, blur = None, {"faces": 0, "plates": 0}
    privacy_status = privacy.PRIVACY_PROCESSED
    if photo is not None and photo.filename:
        raw = await photo.read()
        if len(raw) > MAX_PHOTO_BYTES:
            raise HTTPException(413, "photo too large")
        try:
            p = privacy.process_photo(raw, content_type=photo.content_type)  # fail-closed: faces + plates + EXIF
        except privacy.PrivacyProcessingError as exc:
            if exc.code == "file_too_large":
                raise HTTPException(413, "photo too large") from exc
            if exc.code in ("invalid_image", "invalid_mime", "invalid_format", "invalid_dimensions", "empty_image"):
                raise HTTPException(400, "not a readable image") from exc
            raise HTTPException(503, "privacy processing failed; unprocessed photo rejected") from exc
        except Exception as exc:
            raise HTTPException(400, "not a readable image") from exc
        name = f"{uuid.uuid4().hex}.jpg"
        (config.PHOTO_DIR / name).write_bytes(p["jpeg"])  # only the blurred, EXIF-free copy is ever stored
        privacy_status = p["privacy_status"]
        blur = {"faces": p["faces"], "plates": p["plates"], "status": privacy_status}
    photo_url = f"/photos/{name}" if name else None

    token = points.ensure_token(request, response)
    saved = map_reports.create(
        token, category, lon, lat, note, work_id or None, name,
        district=ckan.district_of(lat, lon),
        privacy_status=privacy_status,
        faces_blurred=blur["faces"],
        plates_blurred=blur["plates"],
    )
    city_request_id = None
    if category in map_reports.CITY_CATEGORIES and not saved["duplicate"]:
        absolute = f"{str(request.base_url).rstrip('/')}{photo_url}" if photo_url else None
        city_request_id = _city_request(category, saved["lon"], saved["lat"], note, absolute)
        map_reports.link_city_request(saved["id"], city_request_id)
    return {
        "id": saved["id"],
        "photo_url_blurred": photo_url,
        "points_awarded": saved["points_awarded"],
        "blur": blur,
        "privacy_status": privacy_status,
        "city_request_id": city_request_id,
    }


@router.get("/api/map/reports")
def list_map_reports(bbox: str | None = None, since: str | None = None):
    box = None
    if bbox:
        try:
            box = tuple(float(x) for x in bbox.split(","))
        except ValueError:
            box = ()
        if len(box) != 4 or not all(math.isfinite(x) for x in box) or box[0] > box[2] or box[1] > box[3]:
            raise HTTPException(422, "bbox must be minLon,minLat,maxLon,maxLat")
    ts = None
    if since:
        try:
            ts = map_reports.parse_since(since)
        except ValueError:
            raise HTTPException(422, "since must be an ISO 8601 timestamp")
    status_by_request: dict[str, str] = {}
    try:
        for req in _sandbox().list_requests(mine=True).get("items", []):
            if req.get("id") and req.get("status"):
                status_by_request[str(req["id"])] = str(req["status"])
    except SandboxError:
        pass
    out = map_reports.geojson(box, ts, status_by_request=status_by_request)
    out["source"] = "mock" if _sandbox().mock else "live"
    out["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return out


@router.post("/api/map/reports/{rid}/confirm")
def confirm_map_report(rid: str, request: Request, response: Response):
    token = points.ensure_token(request, response)
    out = map_reports.confirm(rid, token)
    if out is None:
        raise HTTPException(404, "map report not found")
    return out
