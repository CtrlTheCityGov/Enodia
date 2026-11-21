"""Points wallet (Πόντοι Γειτονιάς), earn side.

Append-only SQLite ledger backed by a random pseudonymous HttpOnly cookie (`ao_token`).
No login, no penalties, no per-person rankings. The token lives only in our local DB
and is never sent to the AthensGov Sandbox or logged.
"""
from __future__ import annotations

# --- T7: Points fixes ---
import os
import re
# --- /T7 ---
import secrets

from fastapi import Request, Response

from . import store

# Cookie name for the random pseudonymous wallet token.
# Source: athensone/docs/DECISIONS.md (A-5). Certainty: verified.
COOKIE_NAME = "ao_token"

# Random byte length passed to secrets.token_urlsafe (~192 bits of entropy, 32 chars).
# Source: Python stdlib secrets recommendation (standard 192-bit opaque token). Certainty: verified.
TOKEN_BYTES = 24
# --- T7: Points fixes ---
# Exact length of secrets.token_urlsafe(24): 24 bytes * 4/3 = 32 base64url chars, no '=' padding.
# Source: Python stdlib secrets.token_urlsafe / RFC 4648 §5. Certainty: verified.
TOKEN_LEN = 32
# Matches only the exact URL-safe base64 token format minted by new_token().
# Source: athensone/docs/TASKS.md (T7 card) and Python stdlib secrets.token_urlsafe(24). Certainty: verified.
_TOKEN_RE = re.compile(rf"[A-Za-z0-9_-]{{{TOKEN_LEN}}}")
# --- /T7 ---

# Cookie max-age in seconds (365 days, matching the 12-month tier window).
# Source: athensone/docs/PROPOSAL.pdf p. 6 ("Points expire after 12 months"). Certainty: derived.
COOKIE_MAX_AGE_S = 365 * 24 * 3600

# Points granted per verified civic action.
# Source: athensone/docs/TASKS.md (T2 card) and athensone/docs/PROPOSAL.pdf p. 5. Certainty: verified.
ACTION_POINTS: dict[str, int] = {
    "report_approved": 10,  # Operator approves a citizen report
    "guarantee_claim": 30,  # Engineer opens a Stoa guarantee dossier
    "fix_confirmed": 5,     # Citizen confirms a fix (wired after T1 merge, per DECISIONS.md A-4)
}

# Max credited actions per account per UTC calendar day; None means uncapped.
# Source: athensone/docs/TASKS.md (T2 card: "Daily cap: 3 approved reports per account")
# and athensone/docs/PROPOSAL.pdf p. 5 (report_approved: 3, guarantee_claim: none, fix_confirmed: 3).
# Certainty: verified.
DAILY_CAPS: dict[str, int | None] = {
    "report_approved": 3,
    "guarantee_claim": None,
    "fix_confirmed": 3,
}

# --- B6: Report flow + (A-36 actions and caps) ---
# Map-flow actions (POST /api/map/reports, /confirm, operator approve of a map report's City request).
# Source: docs/SPEC.md «Κανόνες πόντων» and docs/DECISIONS.md A-36. Certainty: verified (SPEC calls them a proposal).
ACTION_POINTS.update({
    "map_report": 5,            # Αναφορά συμβάντος / συμφόρησης (any map category)
    "work_progress_photo": 15,  # Αναφορά προόδου έργου με φωτογραφία
    "confirm_other": 2,         # Επιβεβαίωση αναφοράς άλλου
    "city_confirmed": 20,       # Αναφορά που επιβεβαιώνει ο Δήμος (+20 bonus)
})
# Per-action backstop caps. The SPEC's "10 reports a day" counts map_report + work_progress_photo together;
# app/map_reports.py enforces that combined cap (MAP_REPORTS_DAILY_CAP). confirm_other / city_confirmed: the SPEC
# sets no cap (once per account per report through the ledger's UNIQUE). Source: SPEC «Κανόνες πόντων», A-36.
DAILY_CAPS.update({
    "map_report": 10,
    "work_progress_photo": 10,
    "confirm_other": None,
    "city_confirmed": None,
})
# --- /B6 ---

# Citizen tiers based on 12-month points, checked highest threshold first.
# Source: athensone/docs/TASKS.md (T2 card) and athensone/docs/PROPOSAL.pdf p. 6. Certainty: verified.
TIERS: tuple[tuple[int, str], ...] = (
    (2000, "Πρέσβης"),
    (500, "Φίλος της Γειτονιάς"),
    (0, "Γείτονας"),
)

# Rolling window (days) for tier calculation (~12 months).
# Source: athensone/docs/TASKS.md (T2 card: "500/12 months") and PROPOSAL.pdf p. 6. Certainty: verified.
TIER_WINDOW_DAYS = 365

# Number of recent ledger rows returned by GET /api/points/me.
# Source: athensone/docs/TASKS.md (T2 card: "last 10 entries"). Certainty: verified.
RECENT_ENTRIES_LIMIT = 10

# Default shared collective points target per Δημοτική Κοινότητα (overridden by DISTRICT_TARGET env var).
# Source: athensone/docs/DECISIONS.md (A-9) and TASKS.md (T7 card); 5000 derived from PROPOSAL.pdf p. 6.
# Certainty: verified (default value); official city targets remain to be set by the Municipality.
DISTRICT_TARGET = 5000

# Fallback district label when AthensGov CKAN districts are off or unavailable.
# Source: matches /api/equity in app/main.py. Certainty: verified.
UNKNOWN_DISTRICT = "Άγνωστη περιοχή"


def new_token() -> str:
    """Generate a new random pseudonymous wallet token."""
    return secrets.token_urlsafe(TOKEN_BYTES)


# --- T7: Points fixes ---
def is_valid_token(token: str | None) -> bool:
    """Return True only if token matches the exact 32-char URL-safe base64 format minted by new_token()."""
    return isinstance(token, str) and bool(_TOKEN_RE.fullmatch(token))


def district_target() -> int:
    """Return the collective district points target from DISTRICT_TARGET env var (default 5000)."""
    raw = os.getenv("DISTRICT_TARGET")
    if not raw:
        return DISTRICT_TARGET
    try:
        value = int(raw.strip())
    except ValueError:
        return DISTRICT_TARGET
    return value if value > 0 else DISTRICT_TARGET
# --- /T7 ---


def tier_for(points_12m: int) -> str:
    """Return the Greek tier name for a 12-month rolling point total."""
    for threshold, name in TIERS:
        if points_12m >= threshold:
            return name
    return TIERS[-1][1]


def ensure_token(request: Request, response: Response) -> str:
    """Return the caller's pseudonymous ao_token cookie, minting and setting one on first use."""
    token = request.cookies.get(COOKIE_NAME)
    if is_valid_token(token):
        return token  # type: ignore[return-value]
    token = new_token()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE_S,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return token


def link_report(request_id: str, account: str) -> None:
    """Store the reporter's wallet token next to the report in our local SQLite DB only."""
    if request_id and is_valid_token(account):
        store.save_report_account(request_id, account)


def grant(
    account: str | None,
    action: str,
    ref_id: str,
    verified_by: str,
    district: str | None = None,
    points: int | None = None,
) -> bool:
    """Append a verified points grant to the ledger.

    Exposed as a reusable helper for T2 hooks and follow-up T6 (+5 on fix confirmation, A-4).
    Returns True if a row was added, False if skipped (missing account, duplicate, or daily cap).
    """
    if not account or not ref_id:
        return False
    amount = ACTION_POINTS[action] if points is None else points
    if amount <= 0:
        return False  # rewards only, never penalties (PROPOSAL.pdf p. 6)
    cap = DAILY_CAPS.get(action)
    return store.insert_points(
        account=account,
        district=district,
        action=action,
        ref_id=ref_id,
        points=amount,
        verified_by=verified_by,
        daily_cap=cap,
    )


def grant_for_report(
    request_id: str,
    action: str,
    verified_by: str,
    district: str | None = None,
    points: int | None = None,
) -> bool:
    """Credit points to the citizen who originally submitted `request_id`."""
    account = store.get_report_account(request_id)
    return grant(
        account=account,
        action=action,
        ref_id=request_id,
        verified_by=verified_by,
        district=district,
        points=points,
    )


def wallet(account: str) -> dict:
    """Return balance, current tier and last 10 ledger entries for `account` (never returns the token)."""
    balance = store.points_balance(account)
    balance_12m = store.points_balance_since(account, days=TIER_WINDOW_DAYS)
    entries = store.points_entries(account, limit=RECENT_ENTRIES_LIMIT)
    return {
        "balance": balance,
        "tier": tier_for(balance_12m),
        "entries": entries,
    }


def districts() -> dict:
    """Return aggregated point totals per Δημοτική Κοινότητα vs the shared target (no account IDs)."""
    return {
        "items": store.points_by_district(fallback=UNKNOWN_DISTRICT),
        # --- T7: Points fixes ---
        "target": district_target(),
        # --- /T7 ---
    }
