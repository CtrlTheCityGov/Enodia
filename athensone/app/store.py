"""Local store (SQLite) for what the sandbox can't hold: photos + AI results.

The sandbox keeps reports in memory and has no photo field, so we keep our
own copy keyed by the sandbox request id. SQLite keeps setup to zero; swap for
PostGIS in production (same columns + a geography(Point)).
"""
import json
import sqlite3
import threading

from . import config

_lock = threading.Lock()
_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute(
    """CREATE TABLE IF NOT EXISTS reports (
        request_id TEXT PRIMARY KEY,
        photo TEXT,
        lat REAL, lng REAL,
        category TEXT, severity INTEGER, confidence REAL,
        accessibility_blocker INTEGER,
        ai_json TEXT,
        faces_blurred INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
)
_conn.commit()


def save(request_id, photo, lat, lng, ai: dict, faces: int):
    with _lock:
        _conn.execute(
            "INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
            (request_id, photo, lat, lng, ai["category"], ai["severity"], ai["confidence"],
             int(ai.get("accessibility_blocker", False)), json.dumps(ai, ensure_ascii=False), faces),
        )
        _conn.commit()


def get(request_id):
    row = _conn.execute("SELECT * FROM reports WHERE request_id=?", (request_id,)).fetchone()
    return _row(row) if row else None


def all_reports():
    return [_row(r) for r in _conn.execute("SELECT * FROM reports ORDER BY created_at DESC")]


def clear():
    with _lock:
        _conn.execute("DELETE FROM reports")
        _conn.commit()


def _row(r):
    d = dict(r)
    d["ai"] = json.loads(d.pop("ai_json") or "{}")
    d["accessibility_blocker"] = bool(d["accessibility_blocker"])
    return d
