"""Case API: the operator's investigation view, the auditable decision workflow, the Stoa dossier and the public
citizen tracker.

  GET  /api/cases                         operator inbox summary (one row per canonical case)
  GET  /api/cases/{rid}                   full case: report, supporting submissions, Stoa matches, guarantee,
                                          workflow stage, allowed actions, audit trail, dossiers
  POST /api/cases/{rid}/actions           {action, actor, role?, reason?, work_id?, category?, subtype?, message?}
  POST /api/cases/{rid}/links/{child}/unlink   {actor, reason}: reverse a duplicate merge
  GET  /api/cases/{rid}/dossiers/{id}     the stored dossier as a printable HTML document
  GET  /api/stoa/reviews                  every human match verdict (correction log)
  GET  /api/track/{tid}                   public status for a citizen (MR-…, PH-… or REQ-… id), no internal data
  POST /api/admin/demo-seed               reset + deterministic demo scenario (DEMO_MODE only)

Operator endpoints require X-Operator-Key when OPERATOR_KEY is set (fail-closed). Nothing here sends anything to
a contractor or anyone else: the system records decisions; people act on them.
"""
from __future__ import annotations

import io
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .. import cases, categories, ckan, config, dossier, map_reports, points, store, stoa_match, works
from ..sandbox import SandboxError

router = APIRouter()


def _main():
    from .. import main  # late import: app.main imports this package while it starts

    return main


def _require_operator(request: Request) -> None:
    _main()._require_operator(request)


# ------------------------------------------------------------------ helpers used by app.main and the map router
def find_canonical(city_category: str, lat: float, lng: float) -> tuple[str, float] | None:
    """Open City request of the same category within the duplicate radius, nearest first. Unlinked
    submissions are never re-attached to the case they were removed from."""
    sb = _main().sb
    try:
        near = sb.list_requests(lat=lat, lng=lng, radius_km=config.DUPLICATE_RADIUS_KM, category=city_category)
    except SandboxError:
        return None
    open_ = [r for r in near.get("items", []) if r.get("status") in _main().OPEN]
    open_.sort(key=lambda r: r.get("distance_km", 0))
    return (open_[0]["id"], round(1000 * open_[0].get("distance_km", 0), 1)) if open_ else None


def _today():
    return works.today()


def _card_brief(c: dict) -> dict:
    keep = ("id", "works_type", "works_type_el", "title", "contractor", "ada", "adam", "amount_contract_eur",
            "amount_paid_eur", "start_date", "completion_date", "guarantee_months", "decision_type",
            "final_acceptance_evidence", "geometry", "status", "seed", "contractor_note")
    out = {k: c.get(k) for k in keep if k in c}
    ada = (c.get("ada") or {}).get("value")
    out["source_url"] = dossier.source_url(ada)
    out["is_seed"] = str(ada or "").upper().startswith("SEED") or bool(c.get("seed"))
    return out


def _classification_for(r: dict) -> dict:
    local = store.get(r["id"])
    cat = (local or {}).get("category") or r.get("category") or r.get("category_name")
    return categories.normalise(cat, None, r.get("description") or "")


def stoa_for(r: dict, cls: dict, rid: str) -> dict:
    try:
        wl = works.dataset().get("works", [])
    except FileNotFoundError:
        wl = []
    res = stoa_match.match(r.get("lat"), r.get("lng"), cls.get("stoa_works_types") or [], wl, _today(),
                           district=r.get("district_name"), reviews=cases.reviews(rid))
    cards = {c["id"]: c for c in works.all_cards()} if wl else {}
    for cand in res["candidates"]:
        cand["work"] = _card_brief(cards.get(cand["work_id"], {}))
    if res["best"]:
        res["best"] = next(c for c in res["candidates"] if c["work_id"] == res["best"]["work_id"])
    return res


def ensure_case(r: dict) -> dict:
    c = cases.get(r["id"])
    if not c:
        mr = map_reports.by_city_request(r["id"])
        origin = "map" if mr else ("photo" if store.get(r["id"]) else "sandbox")
        c = cases.ensure(r["id"], _classification_for(r), r.get("lat"), r.get("lng"), origin, (mr or {}).get("id"))
    return c


def summary(r: dict) -> dict:
    """Small case summary attached to each item of GET /api/reports."""
    c = ensure_case(r)
    st = stoa_for(r, c["classification"], r["id"])
    best = st["best"]
    return {"stage": c["stage"], "stage_el": cases.STAGE_EL[c["stage"]], "support_count": cases.support_count(r["id"]),
            "classification": c["classification"],
            "stoa": {"match_type": st["match_type"], "match_type_el": st["match_type_el"],
                     "candidates": len(st["candidates"]),
                     "best": best and {"work_id": best["work_id"], "confidence": best["confidence"],
                                       "guarantee_state": best["guarantee"]["state"],
                                       "accepted": best["accepted"]}}}


def view(rid: str) -> dict:
    m = _main()
    try:
        r = m._merge(m.sb.get_request(rid))
    except SandboxError as exc:
        if str(exc).startswith("404"):
            raise HTTPException(404, "report not found")
        raise
    c = ensure_case(r)
    st = stoa_for(r, c["classification"], rid)
    local, mr = r.get("local"), r.get("map_report")
    photo = (local or {}).get("photo_url") or (mr or {}).get("photo_url_blurred") or r.get("photo_url")
    return {
        "report": {k: r.get(k) for k in ("id", "title", "address", "lat", "lng", "status", "created_at", "updated_at",
                                         "description", "category", "upvotes", "history", "district_name")},
        "photo_url": photo, "local": local, "map_report": mr, "confirmation": r.get("confirmation"),
        "stage": c["stage"], "stage_el": cases.STAGE_EL[c["stage"]], "decision": c.get("decision"),
        "public_message": c.get("public_message"),
        "classification": c["classification"],
        "supporting": cases.links(rid), "support_count": cases.support_count(rid),
        "unlinked": [x for x in cases.links(rid, include_unlinked=True) if x["unlinked_at"]],
        "stoa": st, "events": cases.events(rid), "dossiers": cases.dossiers(rid),
        "allowed_actions": cases.allowed_actions(c["stage"]),
        "data_source": {"reports": "mock" if m.sb.mock else "live", **works.meta()},
        "generated_at": cases.now(),
    }


# ------------------------------------------------------------------ operator inbox + case view
@router.get("/api/cases")
def list_cases(request: Request):
    _require_operator(request)
    items = _main().list_reports()["items"]
    return {"items": [{"id": r["id"], "title": r.get("title"), "status": r.get("status"), **(r.get("case") or {})}
                      for r in items]}


@router.get("/api/cases/{rid}")
def get_case(rid: str, request: Request):
    _require_operator(request)
    return view(rid)


class ActionIn(BaseModel):
    action: str
    actor: str = ""
    role: str | None = None
    reason: str | None = None
    work_id: str | None = None
    category: str | None = None
    subtype: str | None = None
    message: str | None = None


def _sb_status(rid: str, status: str, note: str) -> None:
    m = _main()
    try:
        m.sb.update_request(rid, status=status, note=note)
    except SandboxError:
        pass


def _reward_approved(rid: str, v: dict) -> None:
    """Same citizen rewards as the older approve endpoint (points are granted by people's decisions only)."""
    district = v["report"].get("district_name")
    points.grant_for_report(rid, action="report_approved", verified_by="operator", district=district)
    map_reports.on_city_approved(rid, district=district)


@router.post("/api/cases/{rid}/actions")
def act(rid: str, body: ActionIn, request: Request):
    _require_operator(request)
    v = view(rid)
    a = body.action
    cand = None
    if a in ("accept_match", "reject_match"):
        cand = next((c for c in v["stoa"]["candidates"] if c["work_id"] == body.work_id), None)
        if not cand:
            raise HTTPException(422, "work_id is not a candidate for this report")
    if a == "reclassify" and body.category not in categories.SANDBOX:
        raise HTTPException(422, f"category must be one of {', '.join(categories.SANDBOX)}")
    accepted = next((c for c in v["stoa"]["candidates"] if c["accepted"]), None)
    if a == "decide_refer_contractor":
        if not accepted:
            raise HTTPException(409, "referral to a contractor needs an engineer-accepted works match")
        if not v["dossiers"] or v["dossiers"][-1]["kind"] != "claim_draft":
            raise HTTPException(409, "the latest dossier does not support a claim (missing completion date or "
                                     "accepted match): request the missing documents or decide a municipal repair")
    payload = {k: getattr(body, k) for k in ("work_id", "category", "subtype", "message") if getattr(body, k)}
    try:
        frm, to = cases.transition(rid, a, body.actor, body.role, body.reason, payload)
    except cases.WorkflowError as exc:
        raise HTTPException(exc.code, str(exc))

    actor = body.actor.strip()
    if a in ("accept_match", "reject_match"):
        cases.review_match(rid, body.work_id, "accept" if a == "accept_match" else "reject", actor, body.reason)
    elif a == "reclassify":
        cls = categories.normalise(body.category, None, "")
        cls.update(method="operator", confidence=1.0, needs_review=False,
                   reasons=[f"Ορίστηκε από {actor}: {body.reason}"],
                   original_category=v["classification"].get("original_category"),
                   original_subtype=v["classification"].get("original_subtype"))
        cases.set_classification(rid, cls)
    elif a == "generate_dossier":
        nv = view(rid)
        acc = next((c for c in nv["stoa"]["candidates"] if c["accepted"]), None)
        wrec = next((w for w in works.dataset().get("works", []) if acc and w["id"] == acc["work_id"]), None)
        data = dossier.build(nv, wrec, acc, _today(), actor)
        html = dossier.render_html(data)
        did = cases.save_dossier(rid, actor, "claim_draft" if data["can_draft_claim"] else "evidence_summary", data, html)
        return {"ok": True, "stage": to, "dossier_id": did, "can_draft_claim": data["can_draft_claim"],
                "url": f"/api/cases/{rid}/dossiers/{did}"}
    elif a == "decide_municipal_repair":
        cases.set_decision(rid, "municipal_repair")
        _sb_status(rid, "in_progress", "Προγραμματίστηκε αποκατάσταση από τον Δήμο")
        _reward_approved(rid, v)
    elif a == "decide_refer_contractor":
        cases.set_decision(rid, "contractor_referral_pending_legal")
    elif a == "legal_approve":
        dec = v.get("decision") or ""
        cases.set_decision(rid, "contractor_referral_approved" if "contractor" in dec else "approved")
        _sb_status(rid, "in_progress", "Εγκρίθηκε ενέργεια αποκατάστασης")
        _reward_approved(rid, v)
    elif a == "resolve":
        _sb_status(rid, "resolved", "Το πρόβλημα αποκαταστάθηκε")
        store.ask_confirmation(rid)
    elif a == "reject_report":
        _sb_status(rid, "rejected", "Η αναφορά δεν προχώρησε")
    elif a == "notify_citizen":
        cases.set_public_message(rid, (body.message or body.reason or "").strip())
        if frm == "RESOLVED":
            cases._set_stage(rid, "CITIZEN_NOTIFIED")
            to = "CITIZEN_NOTIFIED"
    elif a == "reopen":
        _sb_status(rid, "in_progress", "Επανάνοιγμα υπόθεσης")
    return {"ok": True, "stage": to}


class UnlinkIn(BaseModel):
    actor: str = ""
    reason: str = ""


@router.post("/api/cases/{rid}/links/{child_id}/unlink")
def unlink(rid: str, child_id: str, body: UnlinkIn, request: Request):
    """Reverse an incorrect duplicate merge: the submission gets its own City request and its own case."""
    _require_operator(request)
    row = cases.link_of(child_id)
    if not row or row["canonical_request_id"] != rid or row["unlinked_at"]:
        raise HTTPException(404, "this submission is not linked to this case")
    if not body.actor.strip() or not body.reason.strip():
        raise HTTPException(422, "actor and reason are required to reverse a merge")
    canon = view(rid)
    cls = canon["classification"]
    m = _main()
    req = m.sb.create_request(category=cls["city_category"], title=f"{cls['label_el']} (αποσυνδέθηκε από {rid})",
                              address=f"{row['lat']:.4f}, {row['lng']:.4f}",
                              description=f"Σχόλιο πολίτη: {row.get('note') or '-'}", lat=row["lat"], lng=row["lng"])
    cases.unlink(child_id, body.actor, body.reason, req["id"])
    if row["child_kind"] == "map":
        map_reports.link_city_request(child_id, req["id"])
    cases.ensure(req["id"], cls, row["lat"], row["lng"], row["child_kind"], child_id, actor=body.actor.strip())
    return {"ok": True, "own_request_id": req["id"]}


@router.get("/api/cases/{rid}/dossiers/{did}", response_class=HTMLResponse)
def get_dossier(rid: str, did: str, request: Request):
    _require_operator(request)
    d = cases.dossier(did)
    if not d or d["request_id"] != rid:
        raise HTTPException(404, "dossier not found")
    return HTMLResponse(d["html"], headers={"Content-Disposition": f'inline; filename="stoa-{rid}-{did}.html"',
                                            "Cache-Control": "no-store"})


@router.get("/api/stoa/reviews")
def stoa_reviews(request: Request):
    _require_operator(request)
    return {"items": cases.all_reviews()}


# ------------------------------------------------------------------ public citizen tracker
def _resolve_tracking(tid: str) -> tuple[str | None, dict]:
    info: dict = {"submitted_as": tid}
    if tid.startswith("MR-"):
        link = cases.link_of(tid)
        if link and not link["unlinked_at"]:
            info["linked"] = True
            return link["canonical_request_id"], info
        if link and link.get("own_request_id"):
            return link["own_request_id"], info
        row = next((r for r in map_reports.all_reports() if r["id"] == tid), None)
        if not row:
            raise HTTPException(404, "unknown tracking id")
        info["category"] = row["category"]
        return row.get("city_request_id"), info
    if tid.startswith("PH-"):
        link = cases.link_of(tid)
        if not link:
            raise HTTPException(404, "unknown tracking id")
        info["linked"] = not link["unlinked_at"]
        return (link["canonical_request_id"] if info["linked"] else link.get("own_request_id")), info
    return tid, info


@router.get("/api/track/{tid}")
def track(tid: str):
    """What a citizen may see: stage, coarse location, support count and public updates. No notes, no names,
    no contractor or guarantee details."""
    rid, info = _resolve_tracking(tid)
    if rid is None:
        return {"id": tid, "stage": "RECORDED", "stage_el": "Καταχωρήθηκε στον χάρτη", "updates": [],
                "city_case": None, "note": "Αυτή η κατηγορία εμφανίζεται μόνο στον χάρτη· δεν δημιουργεί αίτημα στον Δήμο."}
    m = _main()
    try:
        r = m.sb.get_request(rid)
    except SandboxError as exc:
        if str(exc).startswith("404"):
            raise HTTPException(404, "unknown tracking id")
        raise
    c = ensure_case(r)
    pub = cases.PUBLIC_STAGE_EL
    updates = [{"at": e["at"], "text": pub.get(e["stage_to"], "")} for e in cases.events(rid)
               if e["stage_to"] and e["stage_to"] != e["stage_from"] and e["action"] != "created"]
    updates.insert(0, {"at": r.get("created_at"), "text": "Η αναφορά καταχωρήθηκε"})
    dedup, seen = [], set()
    for u in updates:
        if u["text"] and u["text"] not in seen:
            dedup.append(u)
            seen.add(u["text"])
    if c.get("public_message"):
        dedup.append({"at": c["updated_at"], "text": c["public_message"], "from_city": True})
    lat, lng = r.get("lat"), r.get("lng")
    # Ask "is it fixed?" only until the citizen has answered for this resolution (Wave 3): a new resolve calls
    # store.ask_confirmation(), which resets `fixed` to None and lets the question come back.
    conf = store.get_confirmation(rid)
    answered = conf is not None and conf.get("fixed") is not None
    return {"id": tid, "city_case": rid, "linked_to_existing": bool(info.get("linked")),
            "stage": c["stage"], "stage_el": pub[c["stage"]], "category_el": c["classification"].get("label_el"),
            "support_count": cases.support_count(rid),
            "location": {"lat": round(lat, 3), "lng": round(lng, 3)} if lat is not None else None,
            "updates": dedup, "can_confirm_fix": r.get("status") == "resolved" and not answered,
            "fix_confirmed": conf.get("fixed") if conf else None}


# ------------------------------------------------------------------ demo scenario
DEMO = {
    # Ermou pavement, inside the representative segment of the REAL Diavgeia record W-DIAV-001 (ΑΔΑ Ψ0ΣΝΩ6Μ-5ΙΖ),
    # and on the SEED street work W-SEED-001. Completion not published → guarantee UNKNOWN (honest gap).
    "ermou": {"lat": 37.97570, "lng": 23.73300, "note": "Σπασμένες πλάκες στο πεζοδρόμιο, κίνδυνος πτώσης"},
    # Ymittou, on SEED work W-SEED-002 with a complete synthetic contract → guarantee computed (clearly SEED).
    "ymittou": {"lat": 37.96925, "lng": 23.74620, "note": "Υποχώρηση πλακών πεζοδρομίου μπροστά στη στάση"},
}


def _demo_photo(label: str) -> bytes:
    """A synthetic, plainly labelled placeholder 'photo' (no real person or place in it)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 420), (176, 170, 160))
    d = ImageDraw.Draw(img)
    for i in range(0, 640, 80):
        d.line([(i, 0), (i - 120, 420)], fill=(140, 136, 128), width=3)
    for j in range(0, 420, 70):
        d.line([(0, j), (640, j + 20)], fill=(140, 136, 128), width=3)
    d.polygon([(260, 160), (380, 150), (420, 250), (300, 290), (240, 230)], fill=(92, 86, 80))
    d.rectangle([0, 380, 640, 420], fill=(20, 24, 31))
    d.text((12, 392), f"ΔΟΚΙΜΑΣΤΙΚΗ ΕΙΚΟΝΑ DEMO · {label}", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


@router.post("/api/admin/demo-seed")
def demo_seed(request: Request):
    """Reset everything and create the canonical demo cases. Deterministic; only in DEMO_MODE with the mock sandbox."""
    _require_operator(request)
    m = _main()
    if not (config.DEMO_MODE and m.sb.mock):
        raise HTTPException(403, "demo seeding is only available in DEMO_MODE with the mock sandbox")
    m.reset()
    out = {}
    from fastapi.testclient import TestClient  # in-process call keeps one code path for real and demo reports

    client = TestClient(m.app, base_url=str(request.base_url).rstrip("/"))
    for key, (subtype, label) in {"ermou": ("sidewalk", "Ερμού"), "ymittou": ("sidewalk", "Υμηττού")}.items():
        p = DEMO[key]
        res = client.post("/api/map/reports", data={"category": "damage", "subtype": subtype, "lon": p["lng"],
                                                    "lat": p["lat"], "note": p["note"]},
                          files={"photo": (f"demo-{key}.jpg", _demo_photo(label), "image/jpeg")})
        if res.status_code != 200:
            raise HTTPException(500, f"demo seed failed for {key}: {res.text}")
        out[key] = res.json()
    return {"ok": True, "demo": True, "created": out,
            "next": "Υποβάλετε νέα αναφορά «Ζημιά → Πεζοδρόμιο» στην Ερμού για να δείξετε τη σύνδεση διπλότυπων."}
