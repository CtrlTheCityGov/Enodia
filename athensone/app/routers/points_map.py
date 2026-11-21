"""B7: SPEC `GET /points` and `POST /points/redeem` under /api/map/ (A-33), identity from the ao_token cookie (A-34).

The existing /api/points/me and /api/points/districts stay untouched; this module only reads them.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .. import points, rewards

router = APIRouter()

# History rows returned to the panel (earn + redeem, newest first); same size as /api/points/me.
# Source: points.RECENT_ENTRIES_LIMIT (T2 card: "last 10 entries"). Certainty: verified.
HISTORY_LIMIT = points.RECENT_ENTRIES_LIMIT

# Greek label per ledger action. T2 actions from points.ACTION_POINTS, map actions from DECISIONS.md A-36.
# Certainty: verified (action ids); wording is ours.
REASONS: dict[str, str] = {
    "report_approved": "Εγκεκριμένη αναφορά",
    "guarantee_claim": "Φάκελος εγγύησης έργου",
    "fix_confirmed": "Επιβεβαίωση επισκευής",
    "map_report": "Αναφορά στον χάρτη",
    "confirm_other": "Επιβεβαίωση αναφοράς άλλου",
    "work_progress_photo": "Φωτογραφία προόδου έργου",
    "city_confirmed": "Επιβεβαίωση από τον Δήμο",
}


class RedeemIn(BaseModel):
    reward_id: str | None = None


def _ts(sqlite_ts: str) -> str:
    """SQLite UTC 'YYYY-MM-DD HH:MM:SS' → ISO 8601 with Z."""
    return sqlite_ts.replace(" ", "T") + "Z"


def _history(account: str, ledger: list[dict]) -> list[dict]:
    """Earned rows (+) and redemptions (−) merged, newest first."""
    titles = {r["id"]: r["title"] for r in rewards.load_rewards()}
    rows = [
        {"ts": _ts(e["created_at"]), "delta": int(e["points"]), "reason": REASONS.get(e["action"], e["action"])}
        for e in ledger
    ]
    rows += [
        {
            "ts": _ts(r["created_at"]),
            "delta": -int(r["cost"]),
            "reason": "Εξαργύρωση: " + titles.get(r["reward_id"], r["reward_id"]),
        }
        for r in rewards.redemption_entries(account, HISTORY_LIMIT)
    ]
    rows.sort(key=lambda row: row["ts"], reverse=True)
    return rows[:HISTORY_LIMIT]


def _district(ledger: list[dict]) -> dict:
    """The account's latest district (from its newest ledger row) and that district's shared progress."""
    name = next((e["district"] for e in ledger if e.get("district")), None) or points.UNKNOWN_DISTRICT
    totals = points.districts()
    goal = totals["target"]
    total = next((i["points"] for i in totals["items"] if i["district"] == name), 0)
    return {"name": name, "progress_pct": min(100, round(100 * total / goal)), "goal": goal}


@router.get("/api/map/points")
def map_points(request: Request, response: Response) -> dict:
    account = points.ensure_token(request, response)
    ledger = points.wallet(account)["entries"]
    return {
        "balance": rewards.balance(account),
        "district": _district(ledger),
        "history": _history(account, ledger),
        "rewards": rewards.load_rewards(),
    }


@router.post("/api/map/points/redeem")
def map_points_redeem(body: RedeemIn, request: Request, response: Response) -> dict:
    account = points.ensure_token(request, response)
    reward = rewards.find_reward(body.reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="Άγνωστη ανταμοιβή")
    return rewards.redeem(account, reward)


@router.get("/api/map/points/leaderboard")
def map_points_leaderboard() -> dict:
    """Ranked municipal-district civic points leaderboard."""
    totals = points.districts()
    goal = totals["target"]
    ranked = sorted(totals["items"], key=lambda i: (-int(i.get("points", 0)), str(i.get("district", ""))))
    items = [
        {
            "rank": idx + 1,
            "district": row["district"],
            "points": int(row["points"]),
            "progress_pct": min(100, round(100 * int(row["points"]) / goal)) if goal else 0,
        }
        for idx, row in enumerate(ranked)
    ]
    return {"target": goal, "districts": items}
