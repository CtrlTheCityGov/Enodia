"""Build data/env/features.json from OpenStreetMap (Overpass). Run once on the team laptop:

    python scripts/fetch_env.py                       # Municipality of Athens bbox
    python scripts/fetch_env.py --bbox 37.960,23.735,37.975,23.755   # just Pangrati, faster

Pulls: trees (+ tree rows), parks/gardens/green areas, benches, drinking water,
wheelchair-accessible toilets, places tagged wheelchair=yes (the data Wheelmap shows),
and busy roads (motorway/trunk/primary/secondary).
Data © OpenStreetMap contributors, ODbL. The app labels it "OSM" with the snapshot date.
"""
import argparse
import json
from datetime import date
from pathlib import Path

import httpx

OVERPASS = "https://overpass-api.de/api/interpreter"
Q = """[out:json][timeout:180];
(
  node["natural"="tree"]({b});
  way["natural"="tree_row"]({b});
  node["amenity"="bench"]({b});
  node["amenity"="drinking_water"]({b});
  node["amenity"="toilets"]["wheelchair"="yes"]({b});
  node["wheelchair"="yes"]["amenity"]({b});
  node["wheelchair"="yes"]["shop"]({b});
  way["leisure"~"^(park|garden|playground)$"]({b});
  way["landuse"~"^(grass|forest|recreation_ground|village_green)$"]({b});
  way["natural"="wood"]({b});
  way["highway"~"^(motorway|trunk|primary|secondary)$"]({b});
);
out geom;"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", default="37.955,23.690,38.020,23.780", help="south,west,north,east")
    ap.add_argument("--out", default="data/env/features.json")
    a = ap.parse_args()
    # Overpass answers 406 to clients without a User-Agent (seen Sat 21 Nov 2026); a generic one is enough.
    headers = {"User-Agent": "AthensOne/0.1 (Apps4Athens hackathon prototype)", "Accept": "application/json"}
    r = httpx.post(OVERPASS, data={"data": Q.format(b=a.bbox)}, headers=headers, timeout=200)
    r.raise_for_status()
    f = {k: [] for k in ("tree", "park", "bench", "drinking_water", "toilets_wheelchair", "busy_road", "accessible_place")}
    for e in r.json()["elements"]:
        t = e.get("tags", {})
        if e["type"] == "node":
            pt = [round(e["lon"], 6), round(e["lat"], 6)]
            if t.get("natural") == "tree":
                f["tree"].append(pt)
            elif t.get("amenity") == "bench":
                f["bench"].append(pt)
            elif t.get("amenity") == "drinking_water":
                f["drinking_water"].append(pt)
            elif t.get("amenity") == "toilets" and t.get("wheelchair") == "yes":
                f["toilets_wheelchair"].append(pt)
            elif t.get("wheelchair") == "yes":  # Wheelmap-style: places tagged wheelchair-accessible in OSM
                f["accessible_place"].append(pt + [t.get("name") or t.get("amenity") or t.get("shop") or ""])
            continue
        geom = [[round(g["lon"], 6), round(g["lat"], 6)] for g in e.get("geometry", [])]
        if len(geom) < 2:
            continue
        if t.get("natural") == "tree_row":
            f["tree"] += geom
        elif "highway" in t:
            f["busy_road"].append(geom)
        elif len(geom) >= 4 and geom[0] == geom[-1]:
            f["park"].append(geom[:-1])
    out = {"source": "OSM", "snapshot": date.today().isoformat(), "bbox": a.bbox,
           "note": "© OpenStreetMap contributors (ODbL). Shade = tree canopy proxy; busy roads = noise/exhaust proxy.",
           "features": f}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(a.out, {k: len(v) for k, v in f.items()})


if __name__ == "__main__":
    main()
