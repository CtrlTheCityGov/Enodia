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
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        privacy_status TEXT NOT NULL DEFAULT 'processed'
    )"""
)
_rep_cols = {r[1] for r in _conn.execute("PRAGMA table_info(reports)").fetchall()}
if "privacy_status" not in _rep_cols:
    _conn.execute("ALTER TABLE reports ADD COLUMN privacy_status TEXT NOT NULL DEFAULT 'processed'")
_conn.commit()


def save(request_id, photo, lat, lng, ai: dict, faces: int, privacy_status: str = "processed"):
    with _lock:
        _conn.execute(
            "INSERT OR REPLACE INTO reports "
            "(request_id, photo, lat, lng, category, severity, confidence, accessibility_blocker, ai_json, faces_blurred, created_at, privacy_status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,?)",
            (request_id, photo, lat, lng, ai["category"], ai["severity"], ai["confidence"],
             int(ai.get("accessibility_blocker", False)), json.dumps(ai, ensure_ascii=False), faces, privacy_status),
        )
        _conn.commit()


def get(request_id):
    row = _conn.execute("SELECT * FROM reports WHERE request_id=?", (request_id,)).fetchone()
    return _row(row) if row else None


def all_reports(include_supporting: bool = False):
    """Canonical photo reports. Supporting duplicates (ids PH-…, linked in app/cases.py) are evidence of an
    existing case, not separate hazards, so they are left out unless asked for."""
    sql = "SELECT * FROM reports" + ("" if include_supporting else " WHERE request_id NOT LIKE 'PH-%'")
    return [_row(r) for r in _conn.execute(sql + " ORDER BY created_at DESC")]


def clear():
    with _lock:
        _conn.execute("DELETE FROM reports")
        # --- T1: "Is it fixed?" loop ---
        _conn.execute("DELETE FROM confirmations")
        # --- end T1 ---
        # --- T2: Points wallet, earn side ---
        _conn.execute("DELETE FROM points_ledger")
        _conn.execute("DELETE FROM report_accounts")
        # --- /T2 ---
        # --- B7: Points pill + panel, redeem ---
        _conn.execute("CREATE TABLE IF NOT EXISTS redemptions (id INTEGER PRIMARY KEY, account TEXT NOT NULL, reward_id TEXT NOT NULL, cost INTEGER NOT NULL, voucher_code TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)")
        _conn.execute("DELETE FROM redemptions")
        # --- /B7 ---
        _conn.commit()


def _row(r):
    d = dict(r)
    d["ai"] = json.loads(d.pop("ai_json") or "{}")
    d["accessibility_blocker"] = bool(d["accessibility_blocker"])
    return d


# --- T1: "Is it fixed?" loop ---
# Sandbox only tracks submitted/received/in_progress/resolved/rejected, so citizen
# confirmation state lives in SQLite (source: docs/TASKS.md T1, sure).
from datetime import datetime, timedelta, timezone  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

# The points daily cap counts by the Athens calendar day (B16 card, T2; IANA zone name, sure).
ATHENS_TZ = ZoneInfo("Europe/Athens")

_conn.execute(
    """CREATE TABLE IF NOT EXISTS confirmations (
        request_id TEXT PRIMARY KEY,
        asked_at TEXT NOT NULL,
        answered_at TEXT,
        fixed INTEGER,
        photo TEXT
    )"""
)
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _athens_day_utc_bounds() -> tuple[str, str]:
    """UTC start and end of today's Europe/Athens calendar day, as "YYYY-MM-DD HH:MM:SS" (the SQLite
    CURRENT_TIMESTAMP format of points_ledger.created_at). "Now" comes from _now_iso() so tests can freeze it."""
    now_athens = datetime.fromisoformat(_now_iso()).astimezone(ATHENS_TZ)
    start = now_athens.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)  # wall-clock +1 day; ZoneInfo applies the right offset on DST days
    fmt = "%Y-%m-%d %H:%M:%S"
    return start.astimezone(timezone.utc).strftime(fmt), end.astimezone(timezone.utc).strftime(fmt)


def _conf_row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["fixed"] = None if d["fixed"] is None else bool(d["fixed"])
    return d


def ask_confirmation(request_id: str) -> dict:
    now = _now_iso()
    with _lock:
        _conn.execute(
            "INSERT OR REPLACE INTO confirmations (request_id, asked_at, answered_at, fixed, photo) "
            "VALUES (?, ?, NULL, NULL, NULL)",
            (request_id, now),
        )
        _conn.commit()
    return get_confirmation(request_id)


def record_confirmation(request_id: str, fixed: bool, photo: str | None = None) -> dict:
    now = _now_iso()
    with _lock:
        existing = _conn.execute(
            "SELECT asked_at FROM confirmations WHERE request_id=?", (request_id,)
        ).fetchone()
        asked_at = existing["asked_at"] if existing else now
        _conn.execute(
            "INSERT OR REPLACE INTO confirmations (request_id, asked_at, answered_at, fixed, photo) "
            "VALUES (?, ?, ?, ?, ?)",
            (request_id, asked_at, now, int(fixed), photo),
        )
        _conn.commit()
    return get_confirmation(request_id)


def get_confirmation(request_id: str) -> dict | None:
    row = _conn.execute(
        "SELECT request_id, asked_at, answered_at, fixed, photo FROM confirmations WHERE request_id=?",
        (request_id,),
    ).fetchone()
    return _conf_row(row) if row else None
# --- end T1 ---
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
            day_start, day_end = _athens_day_utc_bounds()
            # datetime() normalises the stored UTC text before comparing it with the Athens-day bounds.
            today_count = _conn.execute(
                """SELECT COUNT(*) FROM points_ledger
                   WHERE account = ? AND action = ? AND datetime(created_at) >= ? AND datetime(created_at) < ?""",
                (account, action, day_start, day_end),
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
