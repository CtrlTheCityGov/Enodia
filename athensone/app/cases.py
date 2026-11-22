"""Case store: duplicate links, workflow stage, audit log, match reviews and dossier snapshots.

One *case* per canonical City request (sandbox request id). Every citizen submission is kept:
  - the first one creates the City request (the canonical case);
  - later ones near it (same category, open, within the duplicate radius) are stored and *linked* to it
    (case_links), adding their photo/note as supporting evidence. Nothing is merged destructively;
    an operator can unlink a submission, which then becomes its own City request.

The workflow and every consequential action are recorded in case_events (who, when, why, from→to stage).
SQLite, same DB file as app/store.py. Swap for PostGIS/Postgres in production (same tables).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from . import config

# ------------------------------------------------------------------ workflow vocabulary
STAGES = ("NEW", "TRIAGED", "STOA_INVESTIGATION", "EVIDENCE_REVIEW", "ENGINEER_DECISION", "LEGAL_REVIEW",
          "APPROVED_ACTION", "RESOLVED", "CITIZEN_NOTIFIED", "REJECTED")
STAGE_EL = {
    "NEW": "Νέα", "TRIAGED": "Διαλογή", "STOA_INVESTIGATION": "Διερεύνηση Stoa", "EVIDENCE_REVIEW": "Έλεγχος τεκμηρίων",
    "ENGINEER_DECISION": "Απόφαση μηχανικού", "LEGAL_REVIEW": "Νομική Υπηρεσία", "APPROVED_ACTION": "Εγκεκριμένη ενέργεια",
    "RESOLVED": "Επιλύθηκε", "CITIZEN_NOTIFIED": "Ενημερώθηκε ο πολίτης", "REJECTED": "Απορρίφθηκε",
}
# What a citizen sees for each stage (no internal reasoning, no contractor names).
PUBLIC_STAGE_EL = {
    "NEW": "Παραλήφθηκε", "TRIAGED": "Σε αξιολόγηση", "STOA_INVESTIGATION": "Σε αξιολόγηση",
    "EVIDENCE_REVIEW": "Σε αξιολόγηση", "ENGINEER_DECISION": "Σε αξιολόγηση από μηχανικό",
    "LEGAL_REVIEW": "Σε αξιολόγηση", "APPROVED_ACTION": "Προγραμματίστηκε αποκατάσταση",
    "RESOLVED": "Αποκαταστάθηκε", "CITIZEN_NOTIFIED": "Αποκαταστάθηκε", "REJECTED": "Δεν προχώρησε",
}
TERMINAL = ("CITIZEN_NOTIFIED", "REJECTED")

# action -> (allowed from-stages or None for any non-terminal, to-stage or None to stay, needs_reason, role)
ACTIONS: dict[str, tuple[tuple[str, ...] | None, str | None, bool, str | None]] = {
    "triage":             (("NEW",), "TRIAGED", False, None),
    "reclassify":         (None, None, True, None),
    "start_investigation": (("NEW", "TRIAGED", "EVIDENCE_REVIEW", "ENGINEER_DECISION"), "STOA_INVESTIGATION", False, None),
    "accept_match":       (("STOA_INVESTIGATION", "EVIDENCE_REVIEW", "ENGINEER_DECISION"), "EVIDENCE_REVIEW", False, "engineer"),
    "reject_match":       (("STOA_INVESTIGATION", "EVIDENCE_REVIEW", "ENGINEER_DECISION"), "EVIDENCE_REVIEW", True, "engineer"),
    "request_investigation": (("STOA_INVESTIGATION", "EVIDENCE_REVIEW", "ENGINEER_DECISION"), "EVIDENCE_REVIEW", True, "engineer"),
    "generate_dossier":   (("EVIDENCE_REVIEW", "ENGINEER_DECISION"), "ENGINEER_DECISION", False, "engineer"),
    "decide_municipal_repair": (("TRIAGED", "STOA_INVESTIGATION", "EVIDENCE_REVIEW", "ENGINEER_DECISION"), "APPROVED_ACTION", True, "engineer"),
    "decide_refer_contractor": (("ENGINEER_DECISION",), "LEGAL_REVIEW", True, "engineer"),
    "escalate_legal":     (("EVIDENCE_REVIEW", "ENGINEER_DECISION"), "LEGAL_REVIEW", True, "engineer"),
    "legal_approve":      (("LEGAL_REVIEW",), "APPROVED_ACTION", True, "legal"),
    "legal_return":       (("LEGAL_REVIEW",), "ENGINEER_DECISION", True, "legal"),
    "resolve":            (("APPROVED_ACTION",), "RESOLVED", False, None),
    "notify_citizen":     (("RESOLVED", "REJECTED"), None, True, None),
    "reject_report":      (("NEW", "TRIAGED", "STOA_INVESTIGATION", "EVIDENCE_REVIEW", "ENGINEER_DECISION"), "REJECTED", True, None),
    "reopen":             (("RESOLVED", "CITIZEN_NOTIFIED"), "TRIAGED", True, None),
}
ACTION_EL = {
    "created": "Δημιουργία υπόθεσης", "linked": "Συνδέθηκε υποστηρικτική αναφορά", "unlinked": "Αποσύνδεση αναφοράς",
    "triage": "Διαλογή", "reclassify": "Αλλαγή κατηγορίας", "start_investigation": "Έναρξη διερεύνησης Stoa",
    "accept_match": "Αποδοχή αντιστοίχισης έργου", "reject_match": "Απόρριψη αντιστοίχισης έργου",
    "request_investigation": "Αίτημα περαιτέρω διερεύνησης", "generate_dossier": "Σύνταξη φακέλου τεκμηρίων",
    "decide_municipal_repair": "Απόφαση: αποκατάσταση από τον Δήμο", "decide_refer_contractor": "Απόφαση: παραπομπή σε ανάδοχο",
    "escalate_legal": "Παραπομπή στη Νομική Υπηρεσία", "legal_approve": "Έγκριση Νομικής Υπηρεσίας",
    "legal_return": "Επιστροφή από Νομική Υπηρεσία", "resolve": "Επίλυση", "notify_citizen": "Ενημέρωση πολίτη",
    "reject_report": "Απόρριψη αναφοράς", "reopen": "Επανάνοιγμα", "legacy_status": "Αλλαγή κατάστασης",
}

_lock = threading.Lock()
_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS cases (
        request_id TEXT PRIMARY KEY, stage TEXT NOT NULL, classification_json TEXT NOT NULL,
        lat REAL, lng REAL, origin TEXT, origin_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        public_message TEXT, decision TEXT);
    CREATE TABLE IF NOT EXISTS case_links (
        child_id TEXT PRIMARY KEY, child_kind TEXT NOT NULL, canonical_request_id TEXT NOT NULL,
        lat REAL, lng REAL, note TEXT, photo TEXT, distance_m REAL, created_at TEXT NOT NULL,
        unlinked_at TEXT, unlinked_by TEXT, unlink_reason TEXT, own_request_id TEXT);
    CREATE TABLE IF NOT EXISTS case_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL, at TEXT NOT NULL, actor TEXT NOT NULL,
        role TEXT, action TEXT NOT NULL, stage_from TEXT, stage_to TEXT, reason TEXT, payload_json TEXT);
    CREATE TABLE IF NOT EXISTS match_reviews (
        request_id TEXT NOT NULL, work_id TEXT NOT NULL, verdict TEXT NOT NULL, actor TEXT NOT NULL,
        reason TEXT, at TEXT NOT NULL, PRIMARY KEY (request_id, work_id));
    CREATE TABLE IF NOT EXISTS dossiers (
        id TEXT PRIMARY KEY, request_id TEXT NOT NULL, created_at TEXT NOT NULL, actor TEXT NOT NULL,
        kind TEXT NOT NULL, data_json TEXT NOT NULL, html TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS ix_links_canon ON case_links(canonical_request_id);
    CREATE INDEX IF NOT EXISTS ix_events_req ON case_events(request_id);
    """
)
_conn.commit()


class WorkflowError(ValueError):
    """Raised for an action that is not allowed now (HTTP 409/422 in the router)."""

    def __init__(self, message: str, code: int = 409):
        super().__init__(message)
        self.code = code


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _conn.execute(sql, args).fetchall()]


def _exec(sql: str, args: tuple = ()) -> None:
    with _lock:
        _conn.execute(sql, args)
        _conn.commit()


# ------------------------------------------------------------------ cases
def ensure(request_id: str, classification: dict, lat: float | None, lng: float | None,
           origin: str, origin_id: str | None = None, actor: str = "system") -> dict:
    """Create the case for a new City request (idempotent)."""
    if not get(request_id):
        t = now()
        _exec("INSERT OR IGNORE INTO cases (request_id, stage, classification_json, lat, lng, origin, origin_id,"
              " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
              (request_id, "NEW", json.dumps(classification, ensure_ascii=False), lat, lng, origin, origin_id, t, t))
        log(request_id, actor, "created", None, "NEW", None, {"origin": origin, "origin_id": origin_id,
                                                               "classification": classification})
    return get(request_id)


def get(request_id: str) -> dict | None:
    rows = _rows("SELECT * FROM cases WHERE request_id = ?", (request_id,))
    if not rows:
        return None
    c = rows[0]
    c["classification"] = json.loads(c.pop("classification_json"))
    return c


def all_cases() -> list[dict]:
    return [get(r["request_id"]) for r in _rows("SELECT request_id FROM cases")]


def set_classification(request_id: str, classification: dict) -> None:
    _exec("UPDATE cases SET classification_json = ?, updated_at = ? WHERE request_id = ?",
          (json.dumps(classification, ensure_ascii=False), now(), request_id))


def _set_stage(request_id: str, stage: str) -> None:
    _exec("UPDATE cases SET stage = ?, updated_at = ? WHERE request_id = ?", (stage, now(), request_id))


def set_public_message(request_id: str, msg: str) -> None:
    _exec("UPDATE cases SET public_message = ?, updated_at = ? WHERE request_id = ?", (msg, now(), request_id))


def set_decision(request_id: str, decision: str) -> None:
    _exec("UPDATE cases SET decision = ?, updated_at = ? WHERE request_id = ?", (decision, now(), request_id))


# ------------------------------------------------------------------ events
def log(request_id: str, actor: str, action: str, stage_from: str | None, stage_to: str | None,
        reason: str | None = None, payload: dict | None = None, role: str | None = None) -> None:
    _exec("INSERT INTO case_events (request_id, at, actor, role, action, stage_from, stage_to, reason, payload_json)"
          " VALUES (?,?,?,?,?,?,?,?,?)",
          (request_id, now(), actor, role, action, stage_from, stage_to, reason,
           json.dumps(payload or {}, ensure_ascii=False)))


def events(request_id: str) -> list[dict]:
    out = _rows("SELECT * FROM case_events WHERE request_id = ? ORDER BY id", (request_id,))
    for e in out:
        e["payload"] = json.loads(e.pop("payload_json") or "{}")
        e["action_el"] = ACTION_EL.get(e["action"], e["action"])
    return out


def allowed_actions(stage: str) -> list[str]:
    if stage in TERMINAL and stage != "CITIZEN_NOTIFIED":
        pass
    out = []
    for a, (frm, _to, _r, _role) in ACTIONS.items():
        if frm is None:
            if stage not in TERMINAL:
                out.append(a)
        elif stage in frm:
            out.append(a)
    return out


def transition(request_id: str, action: str, actor: str, role: str | None, reason: str | None,
               payload: dict | None = None) -> tuple[str, str]:
    """Validate and record one workflow action. Returns (stage_from, stage_to). Preconditions that depend on
    other data (accepted match, dossier present) are checked by the caller before calling this."""
    case = get(request_id)
    if not case:
        raise WorkflowError("no case for this report", 404)
    if action not in ACTIONS:
        raise WorkflowError(f"unknown action {action!r}", 422)
    frm, to, needs_reason, need_role = ACTIONS[action]
    stage = case["stage"]
    if action not in allowed_actions(stage):
        raise WorkflowError(f"action {action!r} is not allowed at stage {stage}")
    if not (actor or "").strip():
        raise WorkflowError("actor is required: every decision records who made it", 422)
    if needs_reason and not (reason or "").strip():
        raise WorkflowError("a reason is required for this action", 422)
    if need_role and role != need_role:
        raise WorkflowError(f"this action requires role {need_role!r}", 403)
    new = to or stage
    if new != stage:
        _set_stage(request_id, new)
    log(request_id, actor.strip(), action, stage, new, (reason or "").strip() or None, payload, role)
    return stage, new


# ------------------------------------------------------------------ duplicate links
def link(child_id: str, child_kind: str, canonical_request_id: str, lat: float | None, lng: float | None,
         note: str | None, photo: str | None, distance_m: float | None) -> None:
    _exec("INSERT OR REPLACE INTO case_links (child_id, child_kind, canonical_request_id, lat, lng, note, photo,"
          " distance_m, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
          (child_id, child_kind, canonical_request_id, lat, lng, note, photo, distance_m, now()))
    log(canonical_request_id, "system", "linked", None, None, None,
        {"child_id": child_id, "child_kind": child_kind, "distance_m": distance_m})


def links(canonical_request_id: str, include_unlinked: bool = False) -> list[dict]:
    sql = "SELECT * FROM case_links WHERE canonical_request_id = ?"
    if not include_unlinked:
        sql += " AND unlinked_at IS NULL"
    out = _rows(sql + " ORDER BY created_at", (canonical_request_id,))
    for r in out:
        r["photo_url"] = f"/photos/{r['photo']}" if r.get("photo") else None
    return out


def active_link_targets() -> dict[str, str]:
    """{child_id: canonical_request_id} for every live (not unlinked) duplicate link, in one query.
    Lets the citizen map show a linked duplicate pin with its canonical case's status (Wave 3)."""
    rows = _rows("SELECT child_id, canonical_request_id FROM case_links WHERE unlinked_at IS NULL")
    return {str(r["child_id"]): str(r["canonical_request_id"]) for r in rows}


def link_of(child_id: str) -> dict | None:
    rows = _rows("SELECT * FROM case_links WHERE child_id = ?", (child_id,))
    return rows[0] if rows else None


def unlink(child_id: str, actor: str, reason: str, own_request_id: str | None) -> dict:
    row = link_of(child_id)
    if not row or row["unlinked_at"]:
        raise WorkflowError("this submission is not linked to a case", 404)
    if not (actor or "").strip() or not (reason or "").strip():
        raise WorkflowError("actor and reason are required to reverse a merge", 422)
    _exec("UPDATE case_links SET unlinked_at = ?, unlinked_by = ?, unlink_reason = ?, own_request_id = ? "
          "WHERE child_id = ?", (now(), actor.strip(), reason.strip(), own_request_id, child_id))
    log(row["canonical_request_id"], actor.strip(), "unlinked", None, None, reason.strip(),
        {"child_id": child_id, "own_request_id": own_request_id})
    return link_of(child_id)


def support_count(canonical_request_id: str) -> int:
    """Citizen submissions behind a case: the original plus linked duplicates."""
    return 1 + len(links(canonical_request_id))


# ------------------------------------------------------------------ match reviews
def review_match(request_id: str, work_id: str, verdict: str, actor: str, reason: str | None) -> None:
    _exec("INSERT OR REPLACE INTO match_reviews (request_id, work_id, verdict, actor, reason, at) VALUES (?,?,?,?,?,?)",
          (request_id, work_id, verdict, actor, reason, now()))


def reviews(request_id: str) -> dict[str, dict]:
    return {r["work_id"]: r for r in _rows("SELECT * FROM match_reviews WHERE request_id = ?", (request_id,))}


def all_reviews() -> list[dict]:
    """Every human match verdict: the correction log the matcher can learn from later."""
    return _rows("SELECT * FROM match_reviews ORDER BY at")


# ------------------------------------------------------------------ dossiers
def save_dossier(request_id: str, actor: str, kind: str, data: dict, html: str) -> str:
    did = f"DOS-{uuid.uuid4().hex[:10]}"
    _exec("INSERT INTO dossiers (id, request_id, created_at, actor, kind, data_json, html) VALUES (?,?,?,?,?,?,?)",
          (did, request_id, now(), actor, kind, json.dumps(data, ensure_ascii=False), html))
    return did


def dossiers(request_id: str) -> list[dict]:
    return _rows("SELECT id, request_id, created_at, actor, kind FROM dossiers WHERE request_id = ? ORDER BY created_at",
                 (request_id,))


def dossier(dossier_id: str) -> dict | None:
    rows = _rows("SELECT * FROM dossiers WHERE id = ?", (dossier_id,))
    if not rows:
        return None
    d = rows[0]
    d["data"] = json.loads(d.pop("data_json"))
    return d


def clear() -> None:
    with _lock:
        for t in ("cases", "case_links", "case_events", "match_reviews", "dossiers"):
            _conn.execute(f"DELETE FROM {t}")
        _conn.commit()
