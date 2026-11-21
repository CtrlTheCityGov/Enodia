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
        # --- T2: Points wallet, earn side ---
        _conn.execute("DELETE FROM points_ledger")
        _conn.execute("DELETE FROM report_accounts")
        # --- /T2 ---
        _conn.commit()


def _row(r):
    d = dict(r)
    d["ai"] = json.loads(d.pop("ai_json") or "{}")
    d["accessibility_blocker"] = bool(d["accessibility_blocker"])
    return d


# --- T2: Points wallet, earn side ---
_conn.execute(
    """CREATE TABLE IF NOT EXISTS points_ledger (
        id INTEGER PRIMARY KEY,
        account TEXT NOT NULL,
        district TEXT,
        action TEXT NOT NULL,
        ref_id TEXT NOT NULL,
        points INTEGER NOT NULL,
        verified_by TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(account, action, ref_id)
    )"""
)
_conn.execute(
    """CREATE TABLE IF NOT EXISTS report_accounts (
        request_id TEXT PRIMARY KEY,
        account TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
)
_conn.commit()


def save_report_account(request_id: str, account: str) -> None:
    with _lock:
        _conn.execute(
            "INSERT OR IGNORE INTO report_accounts (request_id, account) VALUES (?, ?)",
            (request_id, account),
        )
        _conn.commit()


def get_report_account(request_id: str) -> str | None:
    with _lock:
        row = _conn.execute(
            "SELECT account FROM report_accounts WHERE request_id = ?",
            (request_id,),
        ).fetchone()
    return row["account"] if row else None


def insert_points(
    account: str,
    district: str | None,
    action: str,
    ref_id: str,
    points: int,
    verified_by: str,
    daily_cap: int | None = None,
) -> bool:
    with _lock:
        exists = _conn.execute(
            "SELECT 1 FROM points_ledger WHERE account = ? AND action = ? AND ref_id = ?",
            (account, action, ref_id),
        ).fetchone()
        if exists:
            return False
        if daily_cap is not None:
            today_count = _conn.execute(
                """SELECT COUNT(*) FROM points_ledger
                   WHERE account = ? AND action = ? AND date(created_at) = date('now')""",
                (account, action),
            ).fetchone()[0]
            if today_count >= daily_cap:
                return False
        cur = _conn.execute(
            """INSERT OR IGNORE INTO points_ledger
               (account, district, action, ref_id, points, verified_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account, district, action, ref_id, points, verified_by),
        )
        _conn.commit()
        return cur.rowcount == 1


def points_balance(account: str) -> int:
    with _lock:
        row = _conn.execute(
            "SELECT COALESCE(SUM(points), 0) FROM points_ledger WHERE account = ?",
            (account,),
        ).fetchone()
    return int(row[0])


def points_balance_since(account: str, days: int) -> int:
    with _lock:
        row = _conn.execute(
            """SELECT COALESCE(SUM(points), 0) FROM points_ledger
               WHERE account = ? AND datetime(created_at) >= datetime('now', ?)""",
            (account, f"-{int(days)} days"),
        ).fetchone()
    return int(row[0])


def points_entries(account: str, limit: int = 10) -> list[dict]:
    with _lock:
        rows = _conn.execute(
            """SELECT id, district, action, ref_id, points, verified_by, created_at
               FROM points_ledger
               WHERE account = ?
               ORDER BY id DESC
               LIMIT ?""",
            (account, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def points_by_district(fallback: str) -> list[dict]:
    with _lock:
        rows = _conn.execute(
            """SELECT COALESCE(NULLIF(district, ''), ?) AS district,
                      SUM(points) AS points
               FROM points_ledger
               GROUP BY COALESCE(NULLIF(district, ''), ?)
               ORDER BY points DESC, district ASC""",
            (fallback, fallback),
        ).fetchall()
    return [{"district": r["district"], "points": int(r["points"])} for r in rows]
# --- /T2 ---
