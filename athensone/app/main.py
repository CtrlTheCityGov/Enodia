"""AthensOne AI backend. Run:  uvicorn app.main:app --reload --port 8000

The browser only talks to this server. The sandbox API key never leaves it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import httpx

from . import ckan, config, env, interop, privacy, routing, store, vision, works
from .geo import cluster, haversine_km
from .sandbox import Sandbox, SandboxError
# --- T2: Points wallet, earn side ---
from fastapi import Response
from . import points
# --- /T2 ---
# --- B6: Report flow + ---
from . import map_reports
# --- /B6 ---

app = FastAPI(title="Enodia", version="0.1")
sb = Sandbox()

OPEN = ("submitted", "received", "in_progress")
COOL_WORDS = ("δροσ", "ζέστ", "καύσων", "κλιματ", "cool", "heat", "hot", "λέσχ")


@app.exception_handler(SandboxError)
async def _sandbox_error(_req, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=502, content={"error": {"code": "sandbox", "message": str(exc)}})


# ------------------------------------------------------------------ meta
@app.get("/api/health")
def health():
    return {"ok": True, "mock": sb.mock, "persona": sb.persona, "vision": config.VISION_PROVIDER,
            "valhalla": config.VALHALLA_URL}


@app.get("/api/me")
def me():
    return sb.me()


# ------------------------------------------------------------------ ask
class AskIn(BaseModel):
    text: str
    lat: float | None = None
    lng: float | None = None


@app.post("/api/ask")
def ask(q: AskIn):
    res = sb.search(q.text)
    answer = res.get("answer") or {}
    out = {
        "answer": answer.get("text") or "Δεν βρήκα επίσημη απάντηση. Δοκιμάστε άλλη διατύπωση ή καλέστε το 1595.",
        "sources": answer.get("sources") or [{"title": h.get("title"), "url": h.get("url")} for h in res.get("results", [])[:3]],
        "source_kind": res.get("source"),  # "live" (cityofathens.gr) or "mock"
        "service": None,
        "cool_places": [],
    }
    try:
        svc = (sb.services(q.text, size=1).get("items") or [None])[0]
        if svc and svc.get("score", 0) > 0:
            out["service"] = sb.service(svc["id"])
    except SandboxError:
        pass
    if any(w in q.text.lower() for w in COOL_WORDS):
        lat, lng = q.lat or config.DEMO_START["lat"], q.lng or config.DEMO_START["lng"]
        out["cool_places"] = cool_places(lat, lng)["items"]
    return out


# ------------------------------------------------------------------ places + routes
@app.get("/api/cool-places")
def cool_places(lat: float, lng: float):
    items = sb.pois(category="friendship_club", lat=lat, lng=lng, radius_km=3).get("items", [])
    if not items:  # no club nearby -> libraries are air-conditioned too
        items = sb.pois(category="library", lat=lat, lng=lng, radius_km=3).get("items", [])
    return {"items": items[:5]}


@app.get("/api/pois")
def pois(category: str | None = None, lat: float | None = None, lng: float | None = None, radius_km: float = 2):
    return sb.pois(category=category, lat=lat, lng=lng, radius_km=radius_km)


def active_hazards():
    """Open reports that block accessibility -> fed to the router."""
    status = {r["id"]: r["status"] for r in sb.list_requests(mine=True).get("items", [])}
    return [
        {"id": r["request_id"], "lat": r["lat"], "lng": r["lng"], "category": r["category"]}
        for r in store.all_reports()
        if r["accessibility_blocker"] and status.get(r["request_id"], "submitted") in OPEN
    ]


@app.get("/api/hazards")
def hazards():
    return {"items": active_hazards()}


@app.get("/api/route")
def get_route(from_lat: float, from_lng: float, to_lat: float, to_lng: float,
              profile: str = "wheelchair", avoid: bool = True):
    hz = active_hazards() if avoid else []
    return routing.route({"lat": from_lat, "lng": from_lng}, {"lat": to_lat, "lng": to_lng}, hz, profile)


# ------------------------------------------------------------------ navigation: accessibility + environment
_weather: dict = {}


def weather(lat, lng):
    """Current temperature + UV from Open-Meteo (no key), cached 15 min. None if off/unreachable."""
    if config.WEATHER == "off":
        return None
    k = (round(lat, 2), round(lng, 2))
    hit = _weather.get(k)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        r = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=4, params={
            "latitude": lat, "longitude": lng, "current": "temperature_2m,uv_index", "timezone": "Europe/Athens"})
        r.raise_for_status()
        cur = r.json()["current"]
        w = {"temp_c": cur.get("temperature_2m"), "uv": cur.get("uv_index"), "source": "Open-Meteo"}
    except Exception:
        w = None
    _weather[k] = (time.time() + 900, w)
    return w


@app.get("/api/navigate")
def navigate(from_lat: float, from_lng: float, to_lat: float, to_lng: float, profile: str = "wheelchair",
             shade: bool = True, air: bool = True, rest: bool = True, heat: bool | None = None,
             max_detour: float = 1.4):
    """Best route to a destination for this person: step-free profile + reported hazards excluded (hard rules),
    then ranked on shade, busy-road exposure and places to rest (soft preferences). Explainable, no AI."""
    frm, to = {"lat": from_lat, "lng": from_lng}, {"lat": to_lat, "lng": to_lng}
    hz = active_hazards()
    pad = 0.004
    bbox = (min(from_lng, to_lng) - pad, min(from_lat, to_lat) - pad, max(from_lng, to_lng) + pad, max(from_lat, to_lat) + pad)
    polys = env.busy_polygons(bbox) if air else None
    cands = routing.candidates(frm, to, hz, profile, polys)

    w = weather((from_lat + to_lat) / 2, (from_lng + to_lng) / 2)
    air_q = ckan.nearest_air((from_lat + to_lat) / 2, (from_lng + to_lng) / 2)  # City's own station, if one is near
    if air_q and air_q.get("temp_c") is not None:  # prefer the City's sensor over the forecast model
        w = {"temp_c": air_q["temp_c"], "uv": (w or {}).get("uv"),
             "source": f"AthensGov σταθμός {air_q.get('name') or air_q['station_id']}"}
    auto_heat = bool(w and w.get("temp_c") is not None and w["temp_c"] >= config.HEAT_C)
    hot = auto_heat if heat is None else heat

    # cool places (Friendship Clubs, libraries) count as rest stops: air-conditioned, with toilets
    try:
        mid = ((from_lat + to_lat) / 2, (from_lng + to_lng) / 2)
        cool = [(p["lng"], p["lat"], "cool_place") for cat in ("friendship_club", "library")
                for p in sb.pois(category=cat, lat=mid[0], lng=mid[1], radius_km=2).get("items", [])
                if haversine_km(p["lat"], p["lng"], to_lat, to_lng) > 0.04 and haversine_km(p["lat"], p["lng"], from_lat, from_lng) > 0.04]
    except SandboxError:
        cool = []

    ws = (1.2 if hot else 0.8) if shade else 0.0
    wa = (1.2 if (air_q and (air_q.get("aqi") or 0) >= 4) else 0.8) if air else 0.0
    fastest = min(c["duration_min"] for c in cands)
    for c in cands:
        m = env.score_line(c["geojson"]["coordinates"], cool, hz)
        c["metrics"] = m
        rest_pen = 0.0
        if rest:
            rest_pen = max(0, m["max_gap_m"] - 250) / 250 * (0.5 if hot else 0.3) - 0.04 * min(m["rest_points"], 4)
        c["score"] = round(c["duration_min"] * (1 + ws * (1 - m["shade_pct"] / 100) + wa * m["busy_pct"] / 100 + rest_pen)
                           + 100 * m["hazards_on_route"], 2)
        c["too_long"] = c["duration_min"] > fastest * max_detour
    ok = [c for c in cands if not c["too_long"]] or cands
    best = min(ok, key=lambda c: c["score"])
    fast = min(cands, key=lambda c: c["duration_min"])
    for c in cands:
        c["chosen"], c["fastest"] = c is best, c is fast
    expl = _explain(best, fast, shade, air, rest, hot)
    if air_q and air_q.get("aqi"):
        expl += f" Ποιότητα αέρα: {air_q['aqi_el']} (AQI {air_q['aqi']}/6, σταθμός {air_q.get('name') or air_q['station_id']})."
    return {"chosen": cands.index(best), "candidates": cands, "explanation_el": expl, "air_quality": air_q,
            "prefs": {"profile": profile, "shade": shade, "air": air, "rest": rest, "heat": hot, "heat_auto": auto_heat},
            "weather": w, "env": env.meta(), "routing": best["source"], "avoided_hazards": len(hz)}


def _explain(best, fast, shade, air, rest, hot):
    b, f = best["metrics"], fast["metrics"]
    if best is fast:
        s = "Η συντομότερη διαδρομή είναι και η καλύτερη για τις ρυθμίσεις σας"
    else:
        parts = []
        if shade and b["shade_pct"] > f["shade_pct"]:
            parts.append(f"{b['shade_pct']}% σκιά αντί {f['shade_pct']}%")
        if air and b["busy_pct"] < f["busy_pct"]:
            parts.append(f"{b['busy_pct']}% δίπλα σε δρόμους με κίνηση αντί {f['busy_pct']}%")
        if rest and b["max_gap_m"] < f["max_gap_m"]:
            parts.append(f"το πολύ {b['max_gap_m']} m χωρίς στάση αντί {f['max_gap_m']} m")
        extra = round(best["duration_min"] - fast["duration_min"])
        s = "Προτείνουμε αυτή τη διαδρομή: " + (", ".join(parts) or "καλύτερη συνολικά") + \
            (f", με {extra}′ περισσότερο" if extra > 0 else "")
    n = b["rest_points"]
    s += ". " + ("Κανένα σημείο για ξεκούραση στη διαδρομή." if n == 0 else
                 "1 σημείο για ξεκούραση στη διαδρομή." if n == 1 else f"{n} σημεία για ξεκούραση στη διαδρομή.")
    if hot:
        s += " Ζέστη: δώσαμε προτεραιότητα στη σκιά."
    return s


@app.get("/api/env/geojson")
def env_geojson(min_lng: float = 23.69, min_lat: float = 37.955, max_lng: float = 23.78, max_lat: float = 38.02):
    return env.geojson((min_lng, min_lat, max_lng, max_lat))


# --- T3: Heat alert banner ---
import math

# Source for UNKNOWN fallback: CLAUDE.md hard rules & TASKS.md T3 test_heat_no_data (certainty: sure).
HEAT_UNKNOWN_SOURCE = "UNKNOWN"
# Fallback station source label when name and station_id are absent: TASKS.md T8 card (certainty: sure).
HEAT_STATION_FALLBACK_SOURCE = "AthensGov σταθμός"


def _heat_reading(lat: float, lng: float) -> tuple[float | None, str]:
    """Current temperature (°C) and source: City's nearest CKAN sensor first, then Open-Meteo, else UNKNOWN."""
    air_q = ckan.nearest_air(lat, lng)
    if air_q and air_q.get("temp_c") is not None:
        # T8: tolerate station dicts missing both name and station_id (TASKS.md T8; certainty: sure).
        raw_name = air_q.get("name")
        label = raw_name.strip() if isinstance(raw_name, str) else raw_name
        if not label:
            sid = air_q.get("station_id")
            label = sid.strip() if isinstance(sid, str) else sid
        if label is not None and label != "":
            return air_q["temp_c"], f"{HEAT_STATION_FALLBACK_SOURCE} {label}"
        return air_q["temp_c"], HEAT_STATION_FALLBACK_SOURCE
    w = weather(lat, lng)
    if w and w.get("temp_c") is not None:
        return w["temp_c"], w.get("source") or "Open-Meteo"
    return None, HEAT_UNKNOWN_SOURCE


def _shaded_minutes(lat: float, lng: float, to_lat: float, to_lng: float) -> float | None:
    """Duration in minutes of the best shaded step-free route to a cool place (mirrors navigate() heat mode)."""
    frm, to = {"lat": lat, "lng": lng}, {"lat": to_lat, "lng": to_lng}
    try:
        hz = active_hazards()
    except SandboxError:
        hz = []
    # Padding 0.004 deg (~400 m), heat shade weight 1.2, hazard penalty 100, max detour 1.4x:
    # all copied from navigate() (app/main.py:141,146,168,178; certainty: sure).
    pad = 0.004
    bbox = (min(lng, to_lng) - pad, min(lat, to_lat) - pad, max(lng, to_lng) + pad, max(lat, to_lat) + pad)
    cands = routing.candidates(frm, to, hz, "wheelchair", env.busy_polygons(bbox))
    if not cands:
        return None
    fastest = min(c["duration_min"] for c in cands)
    scored = []
    for c in cands:
        m = env.score_line(c["geojson"]["coordinates"], [], hz)
        score = c["duration_min"] * (1 + 1.2 * (1 - m["shade_pct"] / 100)) + 100 * m["hazards_on_route"]
        scored.append((c["duration_min"] > fastest * 1.4, score, c["duration_min"]))
    ok = [s for s in scored if not s[0]] or scored
    return min(ok, key=lambda s: s[1])[2]


@app.get("/api/heat")
def heat(lat: float, lng: float) -> dict:
    """Heat alert check: temperature, source, nearest cool place, and shaded walking minutes to it."""
    # T8: reject non-finite coordinates (inf, -inf, nan) before geo/routing math (TASKS.md T8; certainty: sure).
    if not (math.isfinite(lat) and math.isfinite(lng)):
        raise HTTPException(status_code=422, detail="lat and lng must be finite numbers")

    temp_c, source = _heat_reading(lat, lng)
    forced = bool(config.HEAT_FORCE)
    # Threshold config.HEAT_C = 33 °C (source: app/config.py:44 and TASKS.md T3 card; certainty: sure).
    hot = forced or (temp_c is not None and temp_c >= config.HEAT_C)

    try:
        items = cool_places(lat, lng)["items"]
    except SandboxError:
        items = []
    place = items[0] if items else None

    minutes: float | None = None
    # T8 / A-12: skip routing and leave minutes null when not hot (DECISIONS.md A-12; certainty: sure).
    if hot and place is not None and place.get("lat") is not None and place.get("lng") is not None:
        minutes = _shaded_minutes(lat, lng, place["lat"], place["lng"])

    return {
        "hot": hot,
        "temp_c": temp_c,
        "source": source,
        "forced": forced,
        "cool_place": place,
        "minutes": minutes,
    }
# --- /T3 ---


# ------------------------------------------------------------------ AthensGov open data (CKAN)
def _ckan(fn):
    try:
        return fn()
    except ckan.Unavailable as e:
        return JSONResponse(status_code=503, content={"error": {"code": "ckan_unavailable", "message": str(e)}})


@app.get("/api/city/status")
def city_status():
    return ckan.status()


@app.get("/api/city/districts")
def city_districts():
    return _ckan(ckan.districts)


@app.get("/api/city/neighbourhoods")
def city_neighbourhoods():
    return _ckan(ckan.neighbourhoods)


@app.get("/api/city/air")
def city_air():
    return _ckan(ckan.air_latest)


@app.get("/api/city/wifi")
def city_wifi():
    def go():
        items, src = ckan.wifi_stations()
        return {"items": items, "source": src}
    return _ckan(go)


# ------------------------------------------------------------------ equity (Aequitas-style check on service)
def _hours(a, b):
    from datetime import datetime
    try:
        return (datetime.fromisoformat(b.replace("Z", "+00:00")) - datetime.fromisoformat(a.replace("Z", "+00:00"))).total_seconds() / 3600
    except Exception:
        return None


@app.get("/api/equity")
def equity():
    """Per district: reports, share resolved, median hours to first action. Unequal service shows up here."""
    groups: dict = {}
    for r in (_merge(x) for x in sb.list_requests(mine=True).get("items", [])):
        d = r.get("district_name") or "Άγνωστη περιοχή"
        g = groups.setdefault(d, {"district": d, "reports": 0, "resolved": 0, "first_action_h": []})
        g["reports"] += 1
        g["resolved"] += r.get("status") == "resolved"
        # --- T1: "Is it fixed?" loop ---
        _equity_track_reopen(g, r)
        # --- end T1 ---
        hist = r.get("history") or []
        if len(hist) > 1:
            h = _hours(hist[0]["at"], hist[1]["at"])
            if h is not None:
                g["first_action_h"].append(h)
    rows = []
    for g in groups.values():
        hs = sorted(g.pop("first_action_h"))
        g["median_hours_to_first_action"] = round(hs[len(hs) // 2], 2) if hs else None
        g["resolved_share"] = round(g["resolved"] / g["reports"], 2) if g["reports"] else None
        # --- T1: "Is it fixed?" loop ---
        _equity_finalize_reopen(g)
        # --- end T1 ---
        rows.append(g)
    rows.sort(key=lambda g: -g["reports"])
    return {"items": rows, "district_source": "AthensGov municipal-districts-athens" if ckan.enabled() else "off"}


# ------------------------------------------------------------------ open standards out
@app.get("/open311/v2/services.json")
def o311_services():
    from .sandbox import CATEGORIES
    return interop.o311_services(CATEGORIES)


@app.get("/open311/v2/requests.json")
def o311_requests(request: Request, status: str | None = None):
    base = str(request.base_url).rstrip("/")
    out = [interop.o311_request(_merge(r), base) for r in sb.list_requests(mine=True).get("items", [])]
    return [o for o in out if not status or o["status"] == status]


@app.get("/open311/v2/requests/{rid}.json")
def o311_request(rid: str, request: Request):
    return [interop.o311_request(_merge(sb.get_request(rid)), str(request.base_url).rstrip("/"))]


@app.get("/ngsi-ld/v1/entities")
def ngsi_entities(type: str = "ServiceRequest"):
    if type == "ServiceRequest":
        data = [interop.ngsi_service_request(_merge(r)) for r in sb.list_requests(mine=True).get("items", [])]
    elif type == "WorksRecord":
        data = [interop.ngsi_works(c) for c in works.all_cards()]
    elif type == "AirQualityObserved":
        try:
            data = [interop.ngsi_air(s) for s in ckan.air_latest()["items"]]
        except ckan.Unavailable:
            data = []
    else:
        raise HTTPException(400, "type must be ServiceRequest, WorksRecord or AirQualityObserved")
    return JSONResponse(content=data, media_type="application/ld+json")


@app.get("/dcat/catalog.jsonld")
def dcat(request: Request):
    return JSONResponse(content=interop.dcat_catalog(str(request.base_url).rstrip("/")), media_type="application/ld+json")


# ------------------------------------------------------------------ reports
@app.post("/api/report")
async def report(request: Request, response: Response, photo: UploadFile = File(...), lat: float | None = Form(None),
                 lng: float | None = Form(None), address: str = Form(""), note: str = Form("")):
    raw = await photo.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(413, "photo too large")
    try:
        p = privacy.process_photo(raw)
    except Exception:
        raise HTTPException(400, "not a readable image")
    if lat is None or lng is None:
        if not p["gps"]:
            raise HTTPException(400, "no location: send lat/lng or a photo with GPS")
        lat, lng = p["gps"]
    if not (37.9 <= lat <= 38.1 and 23.6 <= lng <= 23.9):
        raise HTTPException(400, "location outside the Municipality of Athens area")

    name = f"{uuid.uuid4().hex}.jpg"
    (config.PHOTO_DIR / name).write_bytes(p["jpeg"])  # only the blurred, EXIF-free copy is ever stored
    photo_url = f"{str(request.base_url).rstrip('/')}/photos/{name}"
    ai = vision.classify(p["jpeg"], note)

    # duplicate check against the city's own API: same category, open, within ~50 m
    near = sb.list_requests(lat=lat, lng=lng, radius_km=config.DUPLICATE_RADIUS_KM, category=ai["category"])
    dup = next((r for r in near.get("items", []) if r.get("status") in OPEN), None)
    if dup:
        sb.upvote(dup["id"])
        return {"duplicate_of": dup["id"], "request": sb.get_request(dup["id"]), "ai": ai,
                "photo_url": photo_url, "faces_blurred": p["faces"], "gps_from_photo": bool(p["gps"])}

    desc = (f"{ai['summary_el']}\n\nΣχόλιο πολίτη: {note or '-'}\nΦωτογραφία (θολωμένα πρόσωπα): {photo_url}\n"
            f"AI: {ai['category']} · σοβαρότητα {ai['severity']}/5 · βεβαιότητα {ai['confidence']:.0%}")
    req = sb.create_request(category=ai["category"], title=ai["title_el"],
                            address=address or f"{lat:.5f}, {lng:.5f}", description=desc, lat=lat, lng=lng)
    store.save(req["id"], name, lat, lng, ai, p["faces"])
    # --- T2: Points wallet, earn side ---
    token = points.ensure_token(request, response)
    points.link_report(req["id"], token)
    # --- /T2 ---
    return {"duplicate_of": None, "request": req, "ai": ai, "photo_url": photo_url,
            "faces_blurred": p["faces"], "gps_from_photo": bool(p["gps"])}


@app.get("/api/reports/export")
def export_reports_csv():
    """Export triaged reports as UTF-8 CSV for municipal operator handoff."""
    import csv
    import io
    from fastapi.responses import Response

    items = list_reports()["items"]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "status", "category", "district_name", "lat", "lng", "ai_confidence", "created_at"])
    for r in items:
        writer.writerow([
            r.get("id", ""),
            r.get("status", ""),
            r.get("category", ""),
            r.get("district_name", ""),
            r.get("lat", ""),
            r.get("lng", ""),
            r.get("ai_confidence", ""),
            r.get("created_at", ""),
        ])
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="athensone-reports.csv"'},
    )


@app.get("/api/reports/{rid}")
def get_report(rid: str):
    return _merge(sb.get_request(rid))


@app.get("/api/reports")
def list_reports():
    items = [_merge(r) for r in sb.list_requests(mine=True).get("items", [])]
    located = [r for r in items if r.get("lat") is not None]
    for r, c in zip(located, cluster([(r["lat"], r["lng"]) for r in located], radius_km=0.1)):
        r["cluster"] = c
    sizes = {}
    for r in located:
        sizes[r["cluster"]] = sizes.get(r["cluster"], 0) + 1
    for r in located:
        r["cluster_size"] = sizes[r["cluster"]]
    order = {"submitted": 0, "received": 1, "in_progress": 2, "resolved": 3, "rejected": 4}
    items.sort(key=lambda r: (order.get(r["status"], 9), -(r.get("local") or {}).get("severity", 0)))
    return {"items": items, "confidence_threshold": config.CONFIDENCE_THRESHOLD}


class Decision(BaseModel):
    note: str | None = None


def _require_transition(rid: str, disallowed: tuple[str, ...]) -> None:
    """Reject operator status transitions from terminal states in `disallowed`."""
    current = sb.get_request(rid).get("status")
    if current in disallowed:
        raise HTTPException(409, "Invalid status transition")


@app.post("/api/reports/{rid}/approve")
def approve(rid: str, d: Decision | None = None):
    _require_transition(rid, ("resolved", "rejected"))
    note = (d.note if d and d.note else "Εγκρίθηκε από υπάλληλο του Δήμου · το συνεργείο ειδοποιήθηκε")
    out = _merge(sb.update_request(rid, status="in_progress", note=note))
    # --- T2: Points wallet, earn side ---
    points.grant_for_report(rid, action="report_approved", verified_by="operator", district=out.get("district_name"))
    # --- /T2 ---
    # --- B6: Report flow + (city_confirmed, map reports only) ---
    map_reports.on_city_approved(rid, district=out.get("district_name"))
    # --- /B6 ---
    return out


@app.post("/api/reports/{rid}/resolve")
def resolve(rid: str):
    _require_transition(rid, ("rejected",))
    updated = sb.update_request(rid, status="resolved", note="Το πρόβλημα αποκαταστάθηκε")
    # --- T1: "Is it fixed?" loop ---
    store.ask_confirmation(rid)
    # --- end T1 ---
    return _merge(updated)


@app.post("/api/reports/{rid}/reject")
def reject(rid: str, d: Decision | None = None):
    _require_transition(rid, ("resolved",))
    return _merge(sb.update_request(rid, status="rejected", note=(d.note if d and d.note else "Απορρίφθηκε από υπάλληλο")))


# --- T1: "Is it fixed?" loop ---
# Reopen note text (source: docs/TASKS.md T1 card; certainty: exact spec).
REOPEN_NOTE = "Ο πολίτης αναφέρει ότι δεν διορθώθηκε"
# Maximum confirmation photo size in bytes: 15 MB (source: matches /api/report upload cap in app/main.py; certainty: high).
CONFIRM_MAX_PHOTO_BYTES = 15 * 1024 * 1024


def _confirmation_view(request_id: str) -> dict | None:
    conf = store.get_confirmation(request_id)
    if conf and conf.get("photo"):
        conf["photo_url"] = f"/photos/{conf['photo']}"
    return conf


def _equity_track_reopen(group: dict, report: dict) -> None:
    conf = report.get("confirmation")
    # --- T6: Confirmation points and reopen history ---
    # Keep reopens recorded in sandbox history even after a later re-resolve resets confirmations.fixed
    # (source: docs/TASKS.md T6 card & docs/DECISIONS.md A-6; certainty: verified).
    reopened_in_history = any(
        isinstance(h, dict) and h.get("note") == REOPEN_NOTE
        for h in (report.get("history") or [])
    )
    reopened = bool(conf and conf.get("fixed") is False) or reopened_in_history
    asked = conf is not None or report.get("status") == "resolved" or reopened
    # --- /T6 ---
    group["_t1_asked"] = group.get("_t1_asked", 0) + int(asked)
    group["_t1_reopened"] = group.get("_t1_reopened", 0) + int(reopened)


def _equity_finalize_reopen(group: dict) -> None:
    asked = group.pop("_t1_asked", 0)
    reopened = group.pop("_t1_reopened", 0)
    group["reopen_rate"] = round(reopened / asked, 2) if asked else None


# --- T6: Confirmation points and reopen history ---
# Action & verifier for the +5 fix-confirmation points grant
# (source: docs/TASKS.md T6 card, docs/DECISIONS.md A-4 & A-17, app/points.py ACTION_POINTS["fix_confirmed"]=5; certainty: verified).
CONFIRM_POINTS_ACTION = "fix_confirmed"
CONFIRM_POINTS_VERIFIED_BY = "system"


def _grant_confirm_points(request: Request, request_id: str, district: str | None) -> bool:
    """Grant +5 fix_confirmed points only when the caller's ao_token matches the reporter's stored token (A-17)."""
    caller = request.cookies.get(points.COOKIE_NAME)
    reporter = store.get_report_account(request_id)
    if not caller or not reporter or caller != reporter:
        return False
    return points.grant(
        account=reporter,
        action=CONFIRM_POINTS_ACTION,
        ref_id=request_id,
        verified_by=CONFIRM_POINTS_VERIFIED_BY,
        district=district,
    )
# --- /T6 ---


@app.post("/api/reports/{rid}/confirm")
async def confirm_report(
    rid: str,
    request: Request,
    fixed: bool = Form(...),
    photo: UploadFile | None = File(None),
):
    """Citizen confirms whether a resolved report was actually fixed (FixMyStreet-style state loop)."""
    try:
        req = sb.get_request(rid)
    except SandboxError as exc:
        if str(exc).startswith("404"):
            raise HTTPException(404, "report not found")
        raise

    photo_name: str | None = None
    faces_blurred = 0
    if photo is not None:
        raw = await photo.read()
        if raw:
            if len(raw) > CONFIRM_MAX_PHOTO_BYTES:
                raise HTTPException(413, "photo too large")
            try:
                processed = privacy.process_photo(raw)
            except Exception:
                raise HTTPException(400, "not a readable image")
            photo_name = f"{uuid.uuid4().hex}.jpg"
            # Only the blurred, EXIF-free JPEG is ever written to disk.
            (config.PHOTO_DIR / photo_name).write_bytes(processed["jpeg"])
            faces_blurred = processed["faces"]

    if not fixed:
        req = sb.update_request(rid, status="in_progress", note=REOPEN_NOTE)

    store.record_confirmation(rid, fixed=fixed, photo=photo_name)
    merged = _merge(req)
    # --- T6: Confirmation points and reopen history ---
    if fixed:
        _grant_confirm_points(request, rid, merged.get("district_name"))
    # --- /T6 ---
    photo_url = f"{str(request.base_url).rstrip('/')}/photos/{photo_name}" if photo_name else None
    return {
        "request": merged,
        "confirmation": merged["confirmation"],
        "photo_url": photo_url,
        "faces_blurred": faces_blurred,
    }
# --- end T1 ---


def _merge(r: dict) -> dict:
    local = store.get(r["id"])
    if local:
        local["photo_url"] = f"/photos/{local['photo']}"
        local["needs_check"] = local["confidence"] < config.CONFIDENCE_THRESHOLD
    r["local"] = local
    # --- T1: "Is it fixed?" loop ---
    r["confirmation"] = _confirmation_view(r["id"])
    # --- end T1 ---
    # Stoa: is there a public works record here that could still be under the contractor's guarantee?
    cat = (local or {}).get("category") or r.get("category") or r.get("category_name")
    try:
        r["guarantee"] = works.for_report(r.get("lat"), r.get("lng"), cat)
    except FileNotFoundError:
        r["guarantee"] = None
    r["district_name"] = ckan.district_of(r.get("lat"), r.get("lng"))  # AthensGov municipal-districts-athens
    return r


# ------------------------------------------------------------------ Stoa: public works memory
@app.get("/api/works")
def works_near(lat: float, lng: float, radius_m: float = 300):
    return {"items": works.near(lat, lng, radius_m), **works.meta()}


@app.get("/api/works/geojson")
def works_geojson():
    return works.geojson()


@app.get("/api/works/radar")
def works_radar(days: int = 90):
    return works.radar(days)


@app.get("/api/works/{wid}")
def works_one(wid: str):
    c = next((c for c in works.all_cards() if c["id"] == wid), None)
    if not c:
        raise HTTPException(404, "unknown works id")
    return c


@app.post("/api/reports/{rid}/dossier")
def dossier(rid: str):
    """Draft claim dossier for the engineer. Never sent anywhere by the system."""
    r = _merge(sb.get_request(rid))
    if not r.get("guarantee"):
        raise HTTPException(404, "no works record linked to this report")
    # --- T2: Points wallet, earn side ---
    # --- T7: Points fixes ---
    if r.get("status") != "rejected":
        points.grant_for_report(rid, action="guarantee_claim", verified_by="engineer", district=r.get("district_name"))
    # --- /T7 ---
    # --- /T2 ---
    return {
        "text": works.dossier(r, r["guarantee"]),
        "sent": False,
        "source": "mock" if sb.mock else "live",
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


# --- T4: Ask Stoa, cited answers ---
from . import stoa_ask  # noqa: E402


class StoaAskIn(BaseModel):
    q: str


@app.post("/api/stoa/ask")
def api_stoa_ask(body: StoaAskIn):
    return stoa_ask.ask(body.q)
# --- /T4 ---


# ------------------------------------------------------------------ smart map layers
@app.get("/api/layers")
def layers():
    """One map, many layers (Athens One). 'live' layers are built; 'roadmap' ones are shown, not faked."""
    wm = works.meta()
    return {"items": [
        {"id": "reports", "name_el": "Αναφορές & εμπόδια", "status": "live", "source": "mock" if sb.mock else "AthensGov Sandbox"},
        {"id": "places", "name_el": "Δροσερά μέρη", "status": "live", "source": "mock" if sb.mock else "AthensGov Sandbox"},
        {"id": "works", "name_el": "Έργα & εγγυήσεις", "status": "live", "source": wm["source"], "snapshot": wm["snapshot"]},
        {"id": "env", "name_el": "Σκιά & στάσεις", "status": "live", "source": env.meta()["source"], "snapshot": env.meta()["snapshot"]},
        {"id": "air", "name_el": "Ποιότητα αέρα", "status": "live" if ckan.enabled() else "off", "source": "AthensGov env-all-stations"},
        {"id": "wifi", "name_el": "Δημοτικό WiFi", "status": "live" if ckan.enabled() else "off", "source": "AthensGov wifi-stations-registry"},
        {"id": "parking", "name_el": "Στάθμευση", "status": "roadmap", "needs": "δεδομένα αισθητήρων / parking του Δήμου"},
        {"id": "clean", "name_el": "Αποκομιδή", "status": "roadmap", "needs": "δρομολόγια και GPS απορριμματοφόρων"},
        {"id": "events", "name_el": "Εκδηλώσεις", "status": "roadmap", "needs": "βάση εκδηλώσεων του Δήμου"},
    ]}


# --- T2: Points wallet, earn side ---
@app.get("/api/points/me")
def points_me(request: Request, response: Response):
    token = points.ensure_token(request, response)
    return points.wallet(token)


@app.get("/api/points/districts")
def points_districts():
    return points.districts()
# --- /T2 ---


# ------------------------------------------------------------------ admin
@app.post("/api/admin/reset")
def reset():
    store.clear()
    # --- B6: Report flow + ---
    map_reports.clear()
    # --- /B6 ---
    return sb.reset()


# ------------------------------------------------------------------ static
app.mount("/photos", StaticFiles(directory=config.PHOTO_DIR), name="photos")
app.mount("/web", StaticFiles(directory=config.ROOT / "web", html=True), name="web")


@app.get("/")
def root():
    return RedirectResponse("/web/citizen.html")


# --- B: routers discovered from app/routers/ (A-32) ---
import importlib as _importlib
import pkgutil as _pkgutil

from . import routers as _routers

for _m in sorted(_pkgutil.iter_modules(_routers.__path__), key=lambda m: m.name):
    app.include_router(_importlib.import_module(f"{_routers.__name__}.{_m.name}").router)
# --- /B ---
