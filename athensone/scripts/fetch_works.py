"""Build data/stoa/works.json from Διαύγεια + ΚΗΜΔΗΣ (B2). Run by hand, online, from athensone/:

    .venv/bin/python scripts/fetch_works.py                          # writes data/stoa/works.json
    .venv/bin/python scripts/fetch_works.py --out /tmp/works.json    # dry run somewhere else

Steps: (1) ΚΗΜΔΗΣ contracts of type «Έργα» signed by Δήμος Αθηναίων; (2) the Διαύγεια decisions those contracts
link (ΑΔΑ), plus Διαύγεια payment decisions (Β.2.2) found by subject words; (3) join on ΑΔΑ; (4) keep only works
whose text names a street in STREETS below, and give them that street's line. Nothing is geocoded automatically:
a work with no known street is left out, never placed at a guess. Every value is wrapped as
{value, label: CITED|INFERRED|UNKNOWN, source: {ada}} like data/works_seed.json. Review the output by hand before
the demo (works_type, completion_date and guarantee_months are left for a person to fill from the documents).

Heads-up: once data/stoa/works.json exists, app/works.py prefers it over the SEED file for every works route.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, works_src  # noqa: E402

# Curated street -> LineString table ([lon, lat], WGS84). Each line is three points (first, middle, last node) of
# the longest OSM way with that name inside lat 37.970–37.990, lon 23.722–23.740, from Overpass on Sat 21 Nov 2026
# (way id in the comment). Only one segment of each street: extend by hand if a work covers more of it.
# Data © OpenStreetMap contributors, ODbL. Certainty: the points are real OSM nodes; which block a work covers is
# not known from the decision text.
STREETS: dict[str, list[list[float]]] = {
    "Ερμού": [[23.7288, 37.97636], [23.73176, 37.97599], [23.73374, 37.97574]],  # way 403438001
    "Μητροπόλεως": [[23.73241, 37.97523], [23.72995, 37.97552], [23.72748, 37.97612]],  # way 318678267
    "Αθηνάς": [[23.72698, 37.9799], [23.72653, 37.97817], [23.72614, 37.97671]],  # way 286067599
    "Αιόλου": [[23.72796, 37.97784], [23.72835, 37.97968], [23.72873, 37.9813]],  # way 52493380
    "Πανεπιστημίου": [[23.73382, 37.97933], [23.73304, 37.98023], [23.73291, 37.98037]],  # way 168914464
    "Σταδίου": [[23.72915, 37.9829], [23.72991, 37.98201], [23.73001, 37.98189]],  # way 207971475
    "Ακαδημίας": [[23.73138, 37.98517], [23.73219, 37.98418], [23.73323, 37.98291]],  # way 52493436
    "Πατησίων": [[23.73036, 37.98771], [23.73062, 37.98873], [23.73084, 37.98958]],  # way 311453391
}

# Subject words for Διαύγεια payment searches (Β.2.2). Chosen by hand from real subjects seen on Sat 21 Nov 2026
# («ΛΟΓΑΡΙΑΣΜΟΣ ... ΠΕΖΟΔΡΟΜΙΩΝ», «ΑΡΣΗ ΕΠΙΚΙΝΔΥΝΟΤΗΤΑΣ ΣΕ ΟΔΟΣΤΡΩΜΑΤΑ»). Certainty: a starting list, not complete.
PAYMENT_SUBJECTS = ["ΛΟΓΑΡΙΑΣΜΟΣ", "ΠΕΖΟΔΡΟΜΙΩΝ", "ΟΔΟΣΤΡΩΜΑΤΑ", "ΑΝΑΠΛΑΣΗ"]

# KHMDHS contractType key for «Έργα» (seen as {"key": "10", "value": "Έργα"} on Sat 21 Nov 2026). Certainty: sure.
KHMDHS_WORKS_TYPE = "10"
# ΚΗΜΔΗΣ answered HTTP 429 after ~10 quick calls (Sat 21 Nov 2026); pause between calls. Value: a guess, unverified.
PAUSE_S = 2.0


def fetch_contracts(date_from: str, date_to: str) -> list[dict]:
    out, page = [], 0
    while True:
        raw = works_src.search_khmdhs({"organizations": [config.WORKS_ORG], "contractType": KHMDHS_WORKS_TYPE,
                                       "dateFrom": date_from, "dateTo": date_to}, page)
        out += works_src.parse_khmdhs(raw)
        page += 1
        time.sleep(PAUSE_S)
        if raw.get("last", True) or page >= raw.get("totalPages", 0):
            return out


def fetch_decisions(contracts: list[dict], date_from: str, date_to: str) -> list[dict]:
    decisions: dict[str, dict] = {}
    for k in contracts:
        for ada in k["related_adas"]:
            try:
                for d in works_src.parse_diavgeia({"decisions": [works_src.get_diavgeia_decision(ada)]}):
                    decisions[d["ada"]] = d
            except Exception as e:  # one missing decision must not stop the run
                print(f"  ! Διαύγεια {ada}: {e}", file=sys.stderr)
    for subject in PAYMENT_SUBJECTS:
        raw = works_src.search_diavgeia({"org": config.WORKS_ORG, "type": "Β.2.2", "subject": subject,
                                         "from_issue_date": date_from, "to_issue_date": date_to, "size": 100})
        for d in works_src.parse_diavgeia(raw):
            decisions[d["ada"]] = d
    return list(decisions.values())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from", default="2024-01-01")
    ap.add_argument("--to", dest="date_to", default=date.today().isoformat())
    ap.add_argument("--out", default=str(config.DATA_DIR / "stoa" / "works.json"))
    ap.add_argument("--replace", action="store_true", help="overwrite instead of merging (not recommended)")
    a = ap.parse_args()

    contracts = fetch_contracts(a.date_from, a.date_to)
    print(f"ΚΗΜΔΗΣ: {len(contracts)} contracts")
    decisions = fetch_decisions(contracts, a.date_from, a.date_to)
    print(f"Διαύγεια: {len(decisions)} decisions")
    joined = works_src.join_on_ada(decisions, contracts)
    print(f"joined on ΑΔΑ: {sum(1 for j in joined if j['adam'])} decisions with a contract")
    items = works_src.build_works(contracts, decisions, STREETS)
    print(f"works with a known street: {len(items)} (SPEC wants 10–15; extend STREETS by hand if fewer)")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    doc = {"source": "DIAVGEIA+KHMDHS", "snapshot": today, "organisation": "Δήμος Αθηναίων",
           "note": "Από Διαύγεια και ΚΗΜΔΗΣ OpenData (scripts/fetch_works.py). Οδοί από χειροκίνητο πίνακα (OSM, ODbL). "
                   "Ελέγξτε χειροκίνητα πριν τη χρήση.", "works": items}
    if out.exists() and not a.replace:
        # Never silently replace verified data: merge field by field and keep a backup (app/stoa_ingest.py).
        from app import stoa_ingest

        old = json.loads(out.read_text(encoding="utf-8"))
        backup = out.with_name(f"{out.stem}.backup-{datetime.now():%Y%m%d-%H%M%S}.json")
        backup.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        merged, rep = stoa_ingest.merge_datasets(old.get("works", []), items, today)
        doc = {**old, "snapshot": today, "works": merged}
        doc.setdefault("refresh_log", []).append({"at": today, **{k: v for k, v in rep.items()}})
        print(f"backup: {backup}")
        print(f"merge: +{len(rep['added'])} new, {len(rep['updated'])} updated, {len(rep['conflicts'])} with conflicts, "
              f"{len(rep['kept_missing'])} kept although not in this fetch")
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
