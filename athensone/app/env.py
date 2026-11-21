"""Environmental + comfort layer for routing: shade, busy roads, places to rest.

Data file (first one found):
  1. $ENV_FEATURES_PATH
  2. data/env/features.json   <- built by scripts/fetch_env.py from OpenStreetMap (source "OSM")
  3. data/env_seed.json       <- small fictional demo set (source "SEED", always labelled)

What we score along a route (sampled every ~15 m), and what it stands for:
  shade_pct     share of the route within 12 m of a tree or inside a park/green area
                (proxy: tree canopy only; building shadows are not modelled yet)
  busy_pct      share of the route within 20 m of a primary/secondary/trunk road
                (proxy for traffic noise and exhaust; not a sensor reading)
  rest_points   benches, drinking water, accessible toilets, cool places within 30 m of the route
  max_gap_m     longest stretch with no rest point (matters for older people in the heat)
These are estimates from map data and say so in the UI.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from . import config

K = 111_320.0
CELL = 0.0004  # ~35-45 m grid cells

SHADE_M, BUSY_M, REST_M = 12, 20, 30

_cache: dict = {}


def _path() -> Path | None:
    for p in (os.getenv("ENV_FEATURES_PATH"), config.DATA_DIR / "env" / "features.json",
              config.DATA_DIR / "env_seed.json"):
        if p and Path(p).exists():
            return Path(p)
    return None


class _Grid:
    """Tiny spatial hash for 'is there a point within r metres?' queries."""

    def __init__(self, pts):
        self.g: dict = {}
        for lng, lat in pts:
            self.g.setdefault((int(lng / CELL), int(lat / CELL)), []).append((lng, lat))
        self.n = len(pts)

    def near(self, lng, lat, r_m):
        cx, cy = int(lng / CELL), int(lat / CELL)
        kx = K * math.cos(math.radians(lat))
        span = int(r_m / (CELL * K * 0.75)) + 1
        best = None
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                for p in self.g.get((cx + dx, cy + dy), ()):
                    d = math.hypot((p[0] - lng) * kx, (p[1] - lat) * K)
                    if d <= r_m and (best is None or d < best[0]):
                        best = (d, p)
        return best


def _densify(line, step_m=8):
    out = []
    for (x1, y1), (x2, y2) in zip(line, line[1:]):
        kx = K * math.cos(math.radians(y1))
        n = max(1, int(math.hypot((x2 - x1) * kx, (y2 - y1) * K) / step_m))
        out += [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n)]
    if line:
        out.append(tuple(line[-1]))
    return out


def _in_poly(x, y, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-15) + x1:
            inside = not inside
    return inside


def load() -> dict:
    p = _path()
    key = (str(p), p.stat().st_mtime) if p else None
    if _cache.get("key") == key and "d" in _cache:
        return _cache["d"]
    raw = json.loads(p.read_text(encoding="utf-8")) if p else {"source": "NONE", "features": {}}
    f = raw.get("features", {})
    rest = [(*pt[:2], kind) for kind in ("bench", "drinking_water", "toilets_wheelchair") for pt in f.get(kind, [])]
    d = {
        "meta": {"source": raw.get("source", "NONE"), "snapshot": raw.get("snapshot"), "note": raw.get("note"),
                 "counts": {k: len(v) for k, v in f.items()}},
        "raw": f,
        "trees": _Grid([tuple(t[:2]) for t in f.get("tree", [])]),
        "parks": [ring for ring in f.get("park", [])],
        "busy": _Grid([pt for line in f.get("busy_road", []) for pt in _densify(line)]),
        "rest": rest,
        "rest_grid": _Grid([(x, y) for x, y, _ in rest]),
    }
    d["park_bbox"] = [(min(x for x, _ in r), min(y for _, y in r), max(x for x, _ in r), max(y for _, y in r))
                      for r in d["parks"]]
    _cache.update(key=key, d=d)
    return d


def meta() -> dict:
    return load()["meta"]


def _in_park(d, x, y):
    return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] and _in_poly(x, y, r)
               for r, b in zip(d["parks"], d["park_bbox"]))


def score_line(coords, extra_rest=(), hazards=()) -> dict:
    """Metrics for one route ([[lng,lat],...]). extra_rest: [(lng,lat,kind)] e.g. cool places."""
    d = load()
    samples = _densify(coords, 15)
    if not samples:
        return {}
    shaded = sum(1 for x, y in samples if d["trees"].near(x, y, SHADE_M) or _in_park(d, x, y))
    busy = sum(1 for x, y in samples if d["busy"].near(x, y, BUSY_M))
    # rest points: index along the route where each one is reached
    rest_pts = list(d["rest"]) + list(extra_rest)
    grid = _Grid([(x, y) for x, y, _ in rest_pts]) if extra_rest else d["rest_grid"]
    kinds = {(x, y): k for x, y, k in rest_pts}
    seen, hits = set(), []
    for i, (x, y) in enumerate(samples):
        h = grid.near(x, y, REST_M)
        if h:
            hits.append(i)
            seen.add(h[1])
    step = 15
    gaps = [b - a for a, b in zip([0] + hits, hits + [len(samples) - 1])]
    on_route_hazards = sum(1 for h in hazards
                           if any(math.hypot((h["lng"] - x) * K * math.cos(math.radians(y)), (h["lat"] - y) * K) < 20
                                  for x, y in samples))
    by_kind: dict = {}
    for p in seen:
        by_kind[kinds.get(p, "other")] = by_kind.get(kinds.get(p, "other"), 0) + 1
    return {
        "shade_pct": round(100 * shaded / len(samples)),
        "busy_pct": round(100 * busy / len(samples)),
        "rest_points": len(seen),
        "rest_by_kind": by_kind,
        "max_gap_m": max(gaps) * step if gaps else 0,
        "hazards_on_route": on_route_hazards,
    }


def geojson(bbox=None) -> dict:
    """Env features for the map layer (optionally clipped to bbox = (minlng,minlat,maxlng,maxlat))."""
    d = load()
    f = d["raw"]

    def keep(x, y):
        return bbox is None or (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3])

    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": t[:2]}, "properties": {"kind": "tree"}}
             for t in f.get("tree", []) if keep(*t[:2])]
    for kind in ("bench", "drinking_water", "toilets_wheelchair"):
        feats += [{"type": "Feature", "geometry": {"type": "Point", "coordinates": p[:2]}, "properties": {"kind": kind}}
                  for p in f.get(kind, []) if keep(*p[:2])]
    feats += [{"type": "Feature", "geometry": {"type": "Point", "coordinates": p[:2]},
               "properties": {"kind": "accessible_place", "name": p[2] if len(p) > 2 else ""}}
              for p in f.get("accessible_place", []) if keep(*p[:2])]
    feats += [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": ln}, "properties": {"kind": "busy_road"}}
              for ln in f.get("busy_road", []) if any(keep(*pt) for pt in ln)]
    feats += [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [r + r[:1]]}, "properties": {"kind": "park"}}
              for r in f.get("park", []) if any(keep(*pt) for pt in r)]
    return {"type": "FeatureCollection", "features": feats, "meta": d["meta"]}


def busy_polygons(bbox, max_polys=40, half_width_m=18):
    """Thin rectangles around busy-road segments inside bbox, for Valhalla exclude_polygons."""
    out = []
    for line in load()["raw"].get("busy_road", []):
        for (x1, y1), (x2, y2) in zip(line, line[1:]):
            if not (bbox[0] <= (x1 + x2) / 2 <= bbox[2] and bbox[1] <= (y1 + y2) / 2 <= bbox[3]):
                continue
            kx = K * math.cos(math.radians(y1))
            dx, dy = (x2 - x1) * kx, (y2 - y1) * K
            L = math.hypot(dx, dy) or 1
            ox, oy = -dy / L * half_width_m / kx, dx / L * half_width_m / K
            out.append([[x1 + ox, y1 + oy], [x2 + ox, y2 + oy], [x2 - ox, y2 - oy], [x1 - ox, y1 - oy], [x1 + ox, y1 + oy]])
            if len(out) >= max_polys:
                return out
    return out
