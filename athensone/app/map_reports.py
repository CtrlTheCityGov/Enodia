"""B6: Waze-style map reports («+» flow), stored in our own SQLite table `map_reports`.

Privacy (SPEC «Privacy»): only the rounded public position (4 decimals, ~10 m) is stored; the reporter is the
random `ao_token` pseudonym, kept in this local DB only and never returned, logged or sent to the sandbox.
Photos are handled by the router through `privacy.process_photo()` before anything touches disk.
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone

from . import config, points
from .geo import haversine_km

# Categories of the «+» radial menu, in SPEC order, with their Greek labels.
# Source: docs/SPEC.md F3 and docs/TASKS_B.md B6. Certainty: verified.
CATEGORIES: dict[str, str] = {
    "congestion": "Συμφόρηση",
    "incident": "Συμβάν",
    "obstacle": "Εμπόδιο",
    "damage": "Ζημιά",
    "work_progress": "Πρόοδος έργου",
}

# Map categories that also become a City request in the sandbox, and the sandbox category used.
# Which categories: TASKS_B.md B6 ("obstacle and damage"). Certainty: verified.
# Which sandbox category: our choice from the sandbox list in app/sandbox.py (obstacles are mostly on the
# pavement; "damage" has no closer match than "other"). Certainty: unverified, owner question.
CITY_CATEGORIES: dict[str, str] = {
    "obstacle": "sidewalk",
    "damage": "other",
}

# Public coordinate precision: 4 decimals ≈ 11 m in latitude. Source: SPEC «Privacy» (~10 m), B6 card. Verified.
PUBLIC_DECIMALS = 4

# Anti-abuse rules. Source: SPEC «Κανόνες πόντων», DECISIONS.md A-36. Certainty: verified.
MAP_REPORTS_DAILY_CAP = 10              # rewarded map reports per account per UTC day
DUPLICATE_RADIUS_KM = 0.05              # 50 m
DUPLICATE_WINDOW = timedelta(minutes=30)

_lock = threading.Lock()
_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute(
    """CREATE TABLE IF NOT EXISTS map_reports (
        id TEXT PRIMARY KEY,
        account TEXT,
        category TEXT NOT NULL,
        lon REAL NOT NULL,
        lat REAL NOT NULL,
        note TEXT,
        work_id TEXT,
        photo TEXT,
        city_request_id TEXT,
        points_awarded INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )"""
)
_conn.execute(
    """CREATE TABLE IF NOT EXISTS map_report_confirmations (
        report_id TEXT NOT NULL,
        account TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (report_id, account)
    )"""
)
_conn.commit()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str) -> datetime:
    """Parse an ISO timestamp; a value without a zone is taken as UTC."""
    ts = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def round_public(lon: float, lat: float) -> tuple[float, float]:
    """Round a position to the public precision (~10 m)."""
    return round(lon, PUBLIC_DECIMALS), round(lat, PUBLIC_DECIMALS)


def is_duplicate(category: str, lon: float, lat: float, others: list[dict], now: datetime) -> bool:
    """True if another report of the same category lies within 50 m and the last 30 minutes."""
    for o in others:
        if o["category"] != category or now - _parse_ts(o["created_at"]) > DUPLICATE_WINDOW:
            continue
        if haversine_km(lat, lon, o["lat"], o["lon"]) <= DUPLICATE_RADIUS_KM:
            return True
    return False


def points_action(category: str, has_photo: bool) -> str:
    """Ledger action for a new report: 15 for work progress with a photo, else 5 (SPEC «Κανόνες πόντων»)."""
    return "work_progress_photo" if category == "work_progress" and has_photo else "map_report"


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _conn.execute(sql, args).fetchall()]


def _rewarded_today(account: str, now: datetime) -> int:
    with _lock:
        row = _conn.execute(
            "SELECT COUNT(*) FROM map_reports WHERE account = ? AND points_awarded > 0 AND substr(created_at, 1, 10) = ?",
            (account, now.date().isoformat()),
        ).fetchone()
    return int(row[0])


def create(
    account: str,
    category: str,
    lon: float,
    lat: float,
    note: str,
    work_id: str | None,
    photo: str | None,
    district: str | None = None,
) -> dict:
    """Store a map report and grant its points. Returns {id, points_awarded, lon, lat} (public position)."""
    now = _now()
    lon, lat = round_public(lon, lat)
    rid = f"MR-{uuid.uuid4().hex[:12]}"
    since = (now - DUPLICATE_WINDOW).isoformat(timespec="microseconds")
    recent = _rows("SELECT category, lon, lat, created_at FROM map_reports WHERE created_at >= ?", (since,))
    dup = is_duplicate(category, lon, lat, recent, now)
    awarded = 0
    if not dup and _rewarded_today(account, now) < MAP_REPORTS_DAILY_CAP:
        action = points_action(category, photo is not None)
        if points.grant(account, action, ref_id=rid, verified_by="map_report", district=district):
            awarded = points.ACTION_POINTS[action]
    with _lock:
        _conn.execute(
            "INSERT INTO map_reports (id, account, category, lon, lat, note, work_id, photo, points_awarded, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rid, account, category, lon, lat, note, work_id, photo, awarded, now.isoformat(timespec="microseconds")),
        )
        _conn.commit()
    return {"id": rid, "points_awarded": awarded, "lon": lon, "lat": lat, "duplicate": dup}


def link_city_request(report_id: str, city_request_id: str) -> None:
    """Remember which sandbox City request was created for a map report (for the +20 bonus)."""
    with _lock:
        _conn.execute("UPDATE map_reports SET city_request_id = ? WHERE id = ?", (city_request_id, report_id))
        _conn.commit()


def _confirmations(report_id: str) -> int:
    with _lock:
        row = _conn.execute(
            "SELECT COUNT(*) FROM map_report_confirmations WHERE report_id = ?", (report_id,)
        ).fetchone()
    return int(row[0])


def confirm(report_id: str, account: str) -> dict | None:
    """Count a confirmation once per account (+2, A-36). The author's own confirmation counts nothing.

    Returns {id, confirmations, points_awarded}, or None if the report doesn't exist.
    """
    found = _rows("SELECT account FROM map_reports WHERE id = ?", (report_id,))
    if not found:
        return None
    awarded = 0
    if found[0]["account"] != account:
        with _lock:
            cur = _conn.execute(
                "INSERT OR IGNORE INTO map_report_confirmations (report_id, account, created_at) VALUES (?, ?, ?)",
                (report_id, account, _now().isoformat(timespec="microseconds")),
            )
            _conn.commit()
        if cur.rowcount == 1 and points.grant(account, "confirm_other", ref_id=report_id, verified_by="peer"):
            awarded = points.ACTION_POINTS["confirm_other"]
    return {"id": report_id, "confirmations": _confirmations(report_id), "points_awarded": awarded}


def on_city_approved(city_request_id: str, district: str | None = None) -> bool:
    """+20 `city_confirmed` to the author of the map report behind an approved City request (once)."""
    found = _rows("SELECT id, account FROM map_reports WHERE city_request_id = ?", (city_request_id,))
    if not found:
        return False
    return points.grant(found[0]["account"], "city_confirmed", ref_id=found[0]["id"], verified_by="operator",
                        district=district)


def geojson(bbox: tuple[float, float, float, float] | None = None, since: datetime | None = None) -> dict:
    """Public FeatureCollection of map reports: id, category, created_at, confirmations (no note, no account)."""
    rows = _rows(
        "SELECT m.id, m.category, m.lon, m.lat, m.created_at, COUNT(c.account) AS confirmations"
        " FROM map_reports m LEFT JOIN map_report_confirmations c ON c.report_id = m.id"
        " GROUP BY m.id ORDER BY m.created_at DESC"
    )
    features = []
    for r in rows:
        if bbox and not (bbox[0] <= r["lon"] <= bbox[2] and bbox[1] <= r["lat"] <= bbox[3]):
            continue
        if since and _parse_ts(r["created_at"]) < since:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
            "properties": {"id": r["id"], "category": r["category"], "created_at": r["created_at"],
                           "confirmations": int(r["confirmations"])},
        })
    return {"type": "FeatureCollection", "features": features}


def parse_since(value: str) -> datetime:
    """Parse the `since` query parameter (ISO 8601). Raises ValueError when it isn't one."""
    return _parse_ts(value)


def clear() -> None:
    """Delete all map reports and confirmations (used by /api/admin/reset)."""
    with _lock:
        _conn.execute("DELETE FROM map_reports")
        _conn.execute("DELETE FROM map_report_confirmations")
        _conn.commit()
