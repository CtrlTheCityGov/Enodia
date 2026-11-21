"""Build data/transit/static.json (metro + suburban lines and stations) from OpenStreetMap. Run once:

    python scripts/fetch_transit.py

SPEC «Εξωτερικές πηγές» Μετρό/Προαστιακός: GTFS static of OASA/STASY if available, else OSM.
Checked Sat 21 Nov 2026: https://www.oasa.gr/static/gtfs/google_transit.zip -> HTTP 404, so OSM it is.
Pulls route relations route=subway|train|light_rail of the networks «Μετρό Αθήνας» and «Προαστιακός Αθήνας»
(InterCity trains are skipped: not in the SPEC) and the railway=station nodes they serve.
Data © OpenStreetMap contributors, ODbL. The output records source "OSM" and the snapshot date.
"""
import argparse
import json
import math
from datetime import date
from pathlib import Path

import httpx

# Same endpoint as scripts/fetch_env.py; the mirror is tried if the main server times out.
# Checked Sat 21 Nov 2026: overpass-api.de answered; overpass.private.coffee gave 502. Certainty: sure (on that day).
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
# Overpass answers 406 without a User-Agent (seen Sat 21 Nov 2026, scripts/fetch_env.py); generic one is enough.
HEADERS = {"User-Agent": "AthensOne/0.1 (Apps4Athens hackathon prototype)", "Accept": "application/json"}
# OSM `network` values of the relations we keep. Source: Overpass answer Sat 21 Nov 2026. Certainty: sure.
NETWORKS = {"Μετρό Αθήνας", "Προαστιακός Αθήνας"}
# A station belongs to a line if one of the line's stop members lies within this distance.
# Source: our choice (stop_position nodes sit on the track, station nodes in the hall, ~50-200 m apart). Unverified.
STOP_MATCH_M = 300.0

Q = """[out:json][timeout:180];
relation["route"~"^(subway|train|light_rail)$"]({b})->.r;
.r out geom;
node["railway"="station"]({b})->.st;
.st out;
"""


def _dist_m(a: list[float], b: list[float]) -> float:
    """Equirectangular distance in metres between two [lon, lat] points (good enough below a few km)."""
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * k, a[1] - b[1]) * 111_320


def _elevator(tags: dict) -> bool | None:
    """Card B3: OSM `elevator`, else `wheelchair`, else None (unknown, never guessed)."""
    for key in ("elevator", "wheelchair"):
        v = tags.get(key)
        if v == "yes":
            return True
        if v == "no":
            return False
    return None


def build(elements: list[dict]) -> dict:
    """Turn an Overpass answer into {lines, stations} FeatureCollections."""
    lines: dict[str, dict] = {}  # ref -> feature (both directions merged)
    seen_ways: dict[str, set] = {}
    stops_by_ref: dict[str, list[list[float]]] = {}
    for e in elements:
        t = e.get("tags", {})
        if e["type"] != "relation" or t.get("network") not in NETWORKS:
            continue
        ref, color = t.get("ref"), t.get("colour")
        if not ref or not color or len(color) != 7 or not color.startswith("#"):
            print("skip (no ref/colour):", e["id"], t.get("name"))  # unknown colour: drop, never invent one
            continue
        feat = lines.setdefault(ref, {
            "type": "Feature",
            "geometry": {"type": "MultiLineString", "coordinates": []},
            # Colour from the OSM `colour` tag of the route relation (matches STASY/Hellenic Train maps). Sure.
            "properties": {"ref": ref, "name": t.get("name", ref).split(":")[0], "color": color.upper(),
                           "mode": t["route"], "network": t["network"]},
        })
        for m in e.get("members", []):
            if m["type"] == "way" and m.get("geometry") and not m.get("role", "").startswith("platform"):
                if m["ref"] in seen_ways.setdefault(ref, set()):
                    continue
                seen_ways[ref].add(m["ref"])
                feat["geometry"]["coordinates"].append(
                    [[round(g["lon"], 5), round(g["lat"], 5)] for g in m["geometry"]])
            elif m["type"] == "node" and m.get("role", "").startswith("stop") and "lon" in m:
                stops_by_ref.setdefault(ref, []).append([m["lon"], m["lat"]])

    stations = []
    for e in elements:
        t = e.get("tags", {})
        if e["type"] != "node" or t.get("railway") != "station" or not t.get("name"):
            continue
        pt = [round(e["lon"], 6), round(e["lat"], 6)]
        served = sorted(r for r, stops in stops_by_ref.items() if any(_dist_m(pt, s) <= STOP_MATCH_M for s in stops))
        if not served:
            continue  # not a metro/suburban station (tram, InterCity-only, disused)
        twin = next((s for s in stations if s["properties"]["name"] == t["name"]
                     and _dist_m(pt, s["geometry"]["coordinates"]) <= STOP_MATCH_M), None)
        if twin:  # one interchange mapped as several halls (e.g. Πειραιάς M1/M3/Προαστιακός): keep one point
            p = twin["properties"]
            p["lines"] = sorted(set(p["lines"]) | set(served))
            el = _elevator(t)
            if el is True or p["elevator"] is None:  # any hall with a lift -> True; else first known value
                p["elevator"] = el if el is not None else p["elevator"]
            continue
        stations.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": pt},
            "properties": {"name": t["name"], "name_en": t.get("name:en"), "lines": served,
                           "elevator": _elevator(t), "osm_id": e["id"]},
        })
    return {
        "lines": {"type": "FeatureCollection", "features": list(lines.values())},
        "stations": {"type": "FeatureCollection", "features": stations},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    # Attica, wide enough for the Προαστιακός (Kiato/Chalkida ends come in via `out geom` anyway).
    ap.add_argument("--bbox", default="37.85,23.55,38.15,23.95", help="south,west,north,east")
    ap.add_argument("--out", default="data/transit/static.json")
    a = ap.parse_args()
    last_err: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            r = httpx.post(url, data={"data": Q.format(b=a.bbox)}, headers=HEADERS, timeout=200)
            r.raise_for_status()
            break
        except httpx.HTTPError as exc:
            print("Overpass failed:", url, exc)
            last_err = exc
    else:
        raise SystemExit(f"no Overpass server answered: {last_err}")
    snapshot = date.today().isoformat()
    out = {"source": "OSM", "snapshot": snapshot, "bbox": a.bbox,
           "note": "© OpenStreetMap contributors (ODbL). Μετρό Αθήνας + Προαστιακός Αθήνας route relations.",
           **build(r.json()["elements"])}
    for fc in (out["lines"], out["stations"]):  # every feature carries its source (CLAUDE.md: source on every answer)
        for f in fc["features"]:
            f["properties"]["source"] = f"OSM {snapshot}"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(a.out, len(out["lines"]["features"]), "lines,", len(out["stations"]["features"]), "stations")


if __name__ == "__main__":
    main()
