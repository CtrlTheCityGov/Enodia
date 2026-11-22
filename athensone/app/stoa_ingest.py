"""Incremental, non-destructive merge of a freshly fetched works dataset into the existing one.

Used by scripts/fetch_works.py. Rules (mission brief 3.2: "never silently replace verified information"):
  * Records are matched by `id`, else by ΑΔΑ value.
  * For every evidence field ({value, label, source, quote}):
      - a new UNKNOWN/empty value never replaces a known one;
      - a stronger label replaces a weaker one (CITED > INFERRED > UNKNOWN);
      - same strength but a different value → the old value stays and the new one is recorded under
        `conflicts` (the guarantee engine then demands human review);
      - identical values → only `last_verified` moves forward.
  * Records missing from the new fetch are kept (a search window is not proof a decision was withdrawn).
  * Every record carries `provenance: {first_seen, last_verified, retrieved_from}`.
The merge is pure; the caller writes the file and keeps a timestamped backup.
"""
from __future__ import annotations

import copy

RANK = {"CITED": 3, "INFERRED": 2, "UNKNOWN": 0, None: 0}
META_KEYS = ("id", "geometry", "works_type", "works_types", "resolution", "status", "seed", "scope",
             "geometry_basis", "contractor_note", "final_acceptance", "provenance")


def _known(f) -> bool:
    return isinstance(f, dict) and f.get("value") not in (None, "") and f.get("label") != "UNKNOWN"


def _key(w: dict) -> str:
    ada = (w.get("ada") or {}).get("value") if isinstance(w.get("ada"), dict) else w.get("ada")
    return w.get("id") or f"ADA:{ada}"


def merge_field(old, new, retrieved_at: str, source_name: str) -> tuple[dict | None, str]:
    """Returns (merged_field, outcome) with outcome in kept|filled|upgraded|confirmed|conflict."""
    if not _known(new):
        return copy.deepcopy(old), "kept"
    if not _known(old):
        return copy.deepcopy(new), "filled"
    if old.get("value") == new.get("value"):
        out = copy.deepcopy(old)
        if RANK.get(new.get("label"), 0) > RANK.get(old.get("label"), 0):
            out.update(label=new["label"], source=new.get("source"), quote=new.get("quote") or old.get("quote"))
            return out, "upgraded"
        return out, "confirmed"
    if RANK.get(new.get("label"), 0) > RANK.get(old.get("label"), 0):
        out = copy.deepcopy(new)
        out.setdefault("conflicts", []).append({"value": old["value"], "source": old.get("source"),
                                                "label": old.get("label"), "superseded_at": retrieved_at})
        return out, "upgraded"
    out = copy.deepcopy(old)
    alts = out.setdefault("conflicts", [])
    entry = {"value": new["value"], "source": new.get("source"), "label": new.get("label"),
             "seen_at": retrieved_at, "via": source_name}
    if not any(a.get("value") == entry["value"] for a in alts):
        alts.append(entry)
    return out, "conflict"


def merge_datasets(old_works: list[dict], new_works: list[dict], retrieved_at: str,
                   source_name: str = "DIAVGEIA+KHMDHS") -> tuple[list[dict], dict]:
    by_key = {_key(w): copy.deepcopy(w) for w in old_works}
    by_ada = {((w.get("ada") or {}).get("value")): _key(w) for w in old_works if isinstance(w.get("ada"), dict)}
    report = {"added": [], "updated": {}, "conflicts": {}, "kept_missing": []}
    seen = set()
    for nw in new_works:
        k = _key(nw)
        if k not in by_key:
            k = by_ada.get((nw.get("ada") or {}).get("value"), k)
        if k not in by_key:
            rec = copy.deepcopy(nw)
            rec["provenance"] = {"first_seen": retrieved_at, "last_verified": retrieved_at, "retrieved_from": source_name}
            by_key[k] = rec
            report["added"].append(k)
            seen.add(k)
            continue
        seen.add(k)
        cur = by_key[k]
        for name, f in nw.items():
            if name in META_KEYS or not isinstance(f, dict) or "value" not in f and "label" not in f:
                continue
            merged, outcome = merge_field(cur.get(name), f, retrieved_at, source_name)
            if merged is not None:
                cur[name] = merged
            if outcome in ("filled", "upgraded"):
                report["updated"].setdefault(k, []).append(name)
            elif outcome == "conflict":
                report["conflicts"].setdefault(k, []).append(name)
        prov = cur.setdefault("provenance", {"first_seen": None, "retrieved_from": source_name})
        prov["last_verified"] = retrieved_at
    report["kept_missing"] = [k for k in by_key if k not in seen and not str(k).startswith("W-SEED")]
    return list(by_key.values()), report
