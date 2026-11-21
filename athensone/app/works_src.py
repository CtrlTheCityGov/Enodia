"""B2: works adapters for Διαύγεια (decisions) and ΚΗΜΔΗΣ (contracts), plus the GET /api/map/works shaping.

Two halves:
- Upstream side (used only by scripts/fetch_works.py, run by hand online): one function per upstream call
  (`search_diavgeia`, `search_khmdhs`), pure parsers (`parse_diavgeia`, `parse_khmdhs`), the join on ΑΔΑ
  (`join_on_ada`) and `build_works`, which turns joined rows into records in the data/works_seed.json schema.
- Serving side (used by app/routers/works_map.py): `map_feature` turns one `works.card()` into a Feature with the
  12 SPEC «Backend contracts» `GET /works` fields. It never calls the network: it reads what works.py already loads.

Upstream shapes were checked online on Sat 21 Nov 2026 (responses saved in tests/fixtures/B2/):
- Διαύγεια `GET {DIAVGEIA_URL}/search.json?org=6013&subject=...` -> {"info": {...}, "decisions": [...]}; each
  decision has `ada`, `subject`, `issueDate` (ms since epoch, midnight UTC), `decisionTypeId`, `extraFieldValues`.
- ΚΗΜΔΗΣ `POST {KHMDHS_URL}/contract?page=0` with a JSON ContractSearchCriteria (OpenAPI at /v3/api-docs) ->
  Spring page {"content": [...], "totalPages": ...}; each contract has `referenceNumber` (ΑΔΑΜ, e.g.
  26SYMV019449260), `contractRelatedADA` {number1..3}, `diavgeiaADA`, `decisionRelatedAda`, dates and amounts.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone

import httpx

from . import config, works

# A generic client name: Overpass rejects requests without a User-Agent (seen Sat 21 Nov 2026); Διαύγεια and
# ΚΗΜΔΗΣ accepted this one. No personal contact details (CLAUDE.md privacy rule).
USER_AGENT = "AthensOne/0.1 (Apps4Athens hackathon prototype)"


# ------------------------------------------------------------------ upstream calls (fetch_works.py only)
def search_diavgeia(params: dict) -> dict:
    """One Διαύγεια OpenData search page. `params` are the documented query params (org, subject, type,
    from_issue_date, to_issue_date, page, size). Note: without from/to dates Διαύγεια searches the last 6 months
    only (seen in `info.query`, Sat 21 Nov 2026)."""
    r = httpx.get(f"{config.DIAVGEIA_URL}/search.json", params=params, timeout=config.WORKS_HTTP_TIMEOUT_S,
                  headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def get_diavgeia_decision(ada: str) -> dict:
    """One Διαύγεια decision by ΑΔΑ (same decision shape as in a search result)."""
    r = httpx.get(f"{config.DIAVGEIA_URL}/decisions/{ada}.json", timeout=config.WORKS_HTTP_TIMEOUT_S,
                  headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def search_khmdhs(criteria: dict, page: int = 0) -> dict:
    """One ΚΗΜΔΗΣ OpenData contract search page (POST /contract, body = ContractSearchCriteria)."""
    r = httpx.post(f"{config.KHMDHS_URL}/contract", params={"page": page}, json=criteria,
                   timeout=config.WORKS_HTTP_TIMEOUT_S,
                   headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------ parsers (pure)
def _ms_to_date(ms) -> str | None:
    # issueDate is ms since epoch at midnight UTC (1785369600000 -> 2026-07-30; checked on Sat 21 Nov 2026).
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def _decision_amount(extra: dict) -> float | None:
    """Euro amount of a decision, or None when the decision carries none (never 0 for 'unknown').
    Δ.1 ανάθεση -> awardAmount; Β.1.3 ανάληψη υποχρέωσης -> amountWithVAT; Β.2.2 πληρωμή -> sum of
    sponsor[].expenseAmount. Field names seen in real responses on Sat 21 Nov 2026."""
    for key in ("awardAmount", "amountWithVAT"):
        amt = (extra.get(key) or {}).get("amount")
        if amt is not None:
            return float(amt)
    paid = [(s.get("expenseAmount") or {}).get("amount") for s in (extra.get("sponsor") or [])]
    paid = [float(a) for a in paid if a is not None]
    return round(sum(paid), 2) if paid else None


def parse_diavgeia(raw: dict) -> list[dict]:
    """Διαύγεια search response -> [{ada, subject, date, amount, type, payee_vat, url}]."""
    out = []
    for d in raw.get("decisions") or []:
        if not d.get("ada") or not d.get("subject"):
            continue
        extra = d.get("extraFieldValues") or {}
        payees = [((s.get("sponsorAFMName") or {}).get("afm")) for s in (extra.get("sponsor") or [])]
        out.append({
            "ada": d["ada"],
            "subject": " ".join(d["subject"].split()),  # subjects carry line breaks and runs of spaces
            "date": _ms_to_date(d.get("issueDate")),
            "amount": _decision_amount(extra),
            "type": d.get("decisionTypeId"),
            "payee_vat": [p for p in payees if p],  # company VAT numbers of the payees (Β.2.2 only)
            "url": d.get("documentUrl") or f"https://diavgeia.gov.gr/doc/{d['ada']}",  # form seen in real responses
        })
    return out


def _contract_adas(c: dict) -> list[str]:
    rel = c.get("contractRelatedADA") or {}
    cands = [c.get("diavgeiaADA"), rel.get("number1"), rel.get("number2"), rel.get("number3"),
             c.get("decisionRelatedAda")]
    seen: list[str] = []
    for a in cands:
        if a and a not in seen:
            seen.append(a)
    return seen


def parse_khmdhs(raw: dict) -> list[dict]:
    """ΚΗΜΔΗΣ contract page -> [{ada, related_adas, adam, contractor, contractor_vat, amount_contract_eur,
    title, start_date, end_date, signed_date}]. `ada` is the first linked Διαύγεια ΑΔΑ (diavgeiaADA, then
    contractRelatedADA.number1..3, then decisionRelatedAda); None when the contract links none."""
    out = []
    for c in raw.get("content") or []:
        if c.get("cancelled"):
            continue
        members = ((c.get("contractingDataDetails") or {}).get("contractingMembersDataList")) or []
        names = [m.get("name") for m in members if m.get("name")]
        total = c.get("totalCostWithVAT")
        adas = _contract_adas(c)
        out.append({
            "ada": adas[0] if adas else None,
            "related_adas": adas,
            "adam": c.get("referenceNumber"),
            "contractor": " · ".join(names) if names else None,
            "contractor_vat": [m.get("vatNumber") for m in members if m.get("vatNumber")],
            # With VAT, to compare with Διαύγεια payments (expenseAmount includes VAT: unverified, from the
            # amounts seen, e.g. 51835.5 on a 1st λογαριασμός). Certainty: medium.
            "amount_contract_eur": float(total) if total is not None else None,
            "title": " ".join((c.get("title") or "").split()) or None,
            "start_date": c.get("startDate"),
            "end_date": None if c.get("noEndDate") else c.get("endDate"),
            "signed_date": c.get("contractSignedDate"),
        })
    return out


def join_on_ada(decisions: list[dict], contracts: list[dict]) -> list[dict]:
    """Every decision, with the contract that links its ΑΔΑ (contract fields None when no contract does)."""
    by_ada: dict[str, dict] = {}
    for k in contracts:
        for a in k.get("related_adas") or ([k["ada"]] if k.get("ada") else []):
            by_ada.setdefault(a, k)
    out = []
    for d in decisions:
        k = by_ada.get(d["ada"]) or {}
        out.append({**d, "adam": k.get("adam"), "contractor": k.get("contractor"),
                    "contractor_vat": k.get("contractor_vat") or [],
                    "amount_contract_eur": k.get("amount_contract_eur"), "contract_title": k.get("title"),
                    "start_date": k.get("start_date"), "end_date": k.get("end_date")})
    return out


# ------------------------------------------------------------------ build works records (pure)
def norm(s: str) -> str:
    """Upper case without accents, for matching street names in decision text ('Ερμού' -> 'ΕΡΜΟΥ')."""
    s = unicodedata.normalize("NFD", s or "")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").upper()


def _ev(value, ada: str | None, label: str = "CITED") -> dict:
    if value is None:
        return {"value": None, "label": "UNKNOWN"}
    return {"value": value, "label": label, "source": {"ada": ada}}


def build_works(contracts: list[dict], decisions: list[dict], streets: dict[str, list]) -> list[dict]:
    """One works record (data/works_seed.json schema) per contract whose text names a street in `streets`.

    `streets` maps a street name to a [[lon, lat], ...] LineString (curated by hand). Contracts that name no
    known street are left out: no geometry is guessed. Payments (Β.2.2) count towards `amount_paid_eur` when their
    payee VAT number is the contractor's and they are dated on or after the contract start; that join is a
    heuristic, so the value is labelled INFERRED, not CITED."""
    by_ada = {d["ada"]: d for d in decisions}
    out = []
    for k in contracts:
        text = norm(" ".join(filter(None, [k.get("title")] +
                                    [by_ada[a]["subject"] for a in k.get("related_adas", []) if a in by_ada])))
        street = next((name for name in streets if norm(name) in text), None)
        if not street:
            continue
        ada = k.get("ada")
        paid = [d for d in decisions if d.get("type") == "Β.2.2" and d.get("amount") is not None
                and set(d.get("payee_vat") or []) & set(k.get("contractor_vat") or [])
                and (not k.get("start_date") or (d.get("date") or "") >= k["start_date"])]
        paid_sum = round(sum(d["amount"] for d in paid), 2) if paid else None
        out.append({
            "id": f"W-{k['adam']}" if k.get("adam") else f"W-{ada}",
            "works_type": None,  # set by hand: the contract text does not say sidewalk/asphalt/... reliably
            "resolution": "street",
            "title": _ev(k.get("title"), ada),
            "street": _ev(street, ada, "INFERRED"),  # matched by name in the text, not quoted from a document
            "contractor": _ev(k.get("contractor"), ada),
            "amount_contract_eur": _ev(k.get("amount_contract_eur"), ada),
            "amount_paid_eur": _ev(paid_sum, paid[0]["ada"] if paid else None, "INFERRED"),
            "start_date": _ev(k.get("start_date"), ada),
            "end_date": _ev(k.get("end_date"), ada),
            "completion_date": {"value": None, "label": "UNKNOWN"},  # needs the πρωτόκολλο παραλαβής, by hand
            "guarantee_months": {"value": None, "label": "UNKNOWN"},
            "final_acceptance": False,
            "ada": _ev(ada, ada),
            "adam": _ev(k.get("adam"), ada),
            "geometry": {"type": "LineString", "coordinates": streets[street]},
        })
    return out


# ------------------------------------------------------------------ serving: SPEC GET /works shape
def _lines(geometry: dict) -> list[list]:
    """[[lon, lat], ...] lists of a LineString / MultiLineString / Point, for distance and bbox checks."""
    t, c = geometry.get("type"), geometry.get("coordinates") or []
    if t == "Point":
        return [[c]]
    if t == "LineString":
        return [c]
    if t == "MultiLineString":
        return list(c)
    return []


def status_of(card: dict, today_iso: str) -> str | None:
    """planned before start_date, in_progress up to end_date (inclusive), completed after it (B2 card).
    The end is end_date, else the certified completion_date. Not enough dates -> None (unknown, never guessed)."""
    start = works._v(card.get("start_date"))
    end = works._v(card.get("end_date")) or works._v(card.get("completion_date"))
    if start and today_iso < start:
        return "planned"
    if end and today_iso > end:
        return "completed"
    if start and end:
        return "in_progress"
    return None


def distance_m(lat: float, lng: float, geometry: dict) -> float:
    return min((works._dist_m(lat, lng, line) for line in _lines(geometry) if line), default=float("inf"))


def in_bbox(geometry: dict, bbox: tuple[float, float, float, float]) -> bool:
    """True when the feature's extent overlaps bbox (minLon, minLat, maxLon, maxLat)."""
    pts = [p for line in _lines(geometry) for p in line]
    if not pts:
        return False
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    return not (max(lons) < bbox[0] or min(lons) > bbox[2] or max(lats) < bbox[1] or min(lats) > bbox[3])


def _ada(card: dict) -> str | None:
    # The work's own ΑΔΑ when the record has one (fetch_works.py output), else the ΑΔΑ its title is cited from.
    return works._v(card.get("ada")) or ((card.get("title") or {}).get("source") or {}).get("ada")


def map_feature(card: dict, today_iso: str, open_reports: list[tuple[float, float]]) -> dict:
    """One works.card() -> Feature with the 12 SPEC fields. Unknown values are None, never 0."""
    geom = card["geometry"]
    near = sum(1 for lat, lng in open_reports if distance_m(lat, lng, geom) <= config.WORKS_REPORT_RADIUS_M)
    props = {
        "id": card["id"],
        "title": works._v(card.get("title")),
        "status": status_of(card, today_iso),
        "contractor": works._v(card.get("contractor")),
        "amount_contract_eur": works._v(card.get("amount_contract_eur")),
        "amount_paid_eur": works._v(card.get("amount_paid_eur")),
        "ada": _ada(card),
        "adam": works._v(card.get("adam")),
        "start_date": works._v(card.get("start_date")),
        "end_date": works._v(card.get("end_date")),
        "guarantee_end": card["clock"]["until"],
        "reports_count": near,
    }
    return {"type": "Feature", "geometry": geom, "properties": props}
