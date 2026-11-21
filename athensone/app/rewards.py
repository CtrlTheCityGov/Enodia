"""Points redemption (B7): reward catalogue from data/rewards.json and the `redemptions` table.

Balance shown to the citizen = earned ledger sum (points.wallet) minus the cost of every redemption.
The ledger stays append-only; a redemption is its own row here, keyed by the same pseudonymous `ao_token`
(A-34). The voucher code is random and never derived from the token.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone

from . import config, points

# Reward catalogue file. Source: B7 card (TASKS_B.md). Certainty: verified.
REWARDS_PATH = config.DATA_DIR / "rewards.json"

# Voucher alphabet without look-alike characters (no 0/O, 1/I/L) so it can be read aloud at a counter.
# Source: own choice for readability. Certainty: n/a (design choice).
VOUCHER_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
# Random characters per voucher: 8 of 31 symbols, about 39 bits, enough for a demo catalogue.
# Source: own estimate (31**8 ~ 8.5e11). Certainty: derived.
VOUCHER_LEN = 8

# Same UTC format as SQLite CURRENT_TIMESTAMP in points_ledger, so both sort together in the history.
# Source: SQLite docs (CURRENT_TIMESTAMP = "YYYY-MM-DD HH:MM:SS" UTC). Certainty: verified.
TS_FORMAT = "%Y-%m-%d %H:%M:%S"

# Own connection to the same SQLite file as app/store.py (the card wants the table in its own module).
_lock = threading.Lock()
_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute(
    """CREATE TABLE IF NOT EXISTS redemptions (
        id INTEGER PRIMARY KEY,
        account TEXT NOT NULL,
        reward_id TEXT NOT NULL,
        cost INTEGER NOT NULL,
        voucher_code TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    )"""
)
_conn.commit()


def load_rewards() -> list[dict]:
    """Return the reward catalogue as [{id, title, cost}] in file order."""
    raw = json.loads(REWARDS_PATH.read_text(encoding="utf-8"))
    return [{"id": r["id"], "title": r["title"], "cost": int(r["cost"])} for r in raw["rewards"]]


def find_reward(reward_id: str | None) -> dict | None:
    """Return the reward with this id, or None."""
    return next((r for r in load_rewards() if r["id"] == reward_id), None)


def new_voucher_code() -> str:
    """Random voucher like `AO-7KQ2-MX9P`; uses `secrets`, never the account token."""
    body = "".join(secrets.choice(VOUCHER_ALPHABET) for _ in range(VOUCHER_LEN))
    return f"AO-{body[:4]}-{body[4:]}"


def redeemed_total(account: str) -> int:
    """Sum of the costs of all redemptions of `account`."""
    row = _conn.execute(
        "SELECT COALESCE(SUM(cost), 0) AS total FROM redemptions WHERE account = ?", (account,)
    ).fetchone()
    return int(row["total"])


def redemption_entries(account: str, limit: int) -> list[dict]:
    """Latest redemptions of `account`, newest first."""
    rows = _conn.execute(
        """SELECT reward_id, cost, created_at FROM redemptions
           WHERE account = ? ORDER BY id DESC LIMIT ?""",
        (account, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def balance(account: str) -> int:
    """Spendable balance: earned ledger sum minus redeemed costs."""
    return points.wallet(account)["balance"] - redeemed_total(account)


def redeem(account: str, reward: dict) -> dict:
    """Redeem `reward` for `account`. Not enough points → ok False and nothing written."""
    with _lock:  # check and insert together, so two clicks can't spend the same points twice
        current = balance(account)
        if current < reward["cost"]:
            return {"ok": False, "balance": current, "voucher_code": None}
        code = new_voucher_code()
        _conn.execute(
            """INSERT INTO redemptions (account, reward_id, cost, voucher_code, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (account, reward["id"], reward["cost"], code, datetime.now(timezone.utc).strftime(TS_FORMAT)),
        )
        _conn.commit()
        return {"ok": True, "balance": current - reward["cost"], "voucher_code": code}


def clear() -> None:
    """Delete all redemptions (used by /api/admin/reset)."""
    with _lock:
        _conn.execute("DELETE FROM redemptions")
        _conn.commit()
