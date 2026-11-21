"""One-off builder for offline mock datasets under web/mock/.

Reads local open-data snapshots (data/ckan/) and downloads once from public
OpenStreetMap (API 0.6, ODbL 1.0) to produce the 9 JSON/GeoJSON contract files
and web/mock/README.md. Never called at test time; pytest reads web/mock/* only.

Usage (from athensone/):
    .venv/bin/python scripts/build_mocks.py
    .venv/bin/python scripts/build_mocks.py --ckan-dir ../../athensone/data/ckan
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

# Allow importing app.ckan._parse_wkt when invoked as `python scripts/build_mocks.py`.
APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.ckan import _parse_wkt  # noqa: E402

# ---------------------------------------------------------------------------
# Constants (every constant carries source and certainty per CLAUDE.md)
# ---------------------------------------------------------------------------

# Snapshot date pinned to the hackathon demo day (STOA_TODAY=2026-11-21).
# Source: CLAUDE.md / TASKS_B.md B0. Certainty: verified.
SNAPSHOT_DATE = "2026-11-21"

# Municipality of Athens WGS84 bounding box enforced by B0 tests.
# Source: athensone/docs/TASKS_B.md (### B0). Certainty: verified.
LON_MIN, LON_MAX = 23.68, 23.80
LAT_MIN, LAT_MAX = 37.95, 38.03

# Reference centre coordinates for Syntagma and Monastiraki.
# Source: athensone/docs/SPEC.md & TASKS_B.md (### B0). Certainty: verified.
SYNTAGMA = (23.7348, 37.9755)
MONASTIRAKI = (23.7257, 37.9761)

# OSM API 0.6 endpoint (returns raw OSM XML with exact node/way IDs).
# Source: https://wiki.openstreetmap.org/wiki/API_v0.6 (verified live 2026-11-21). Certainty: verified.
OSM_API_MAP = "https://api.openstreetmap.org/api/0.6/map"
OSM_API_WAY = "https://api.openstreetmap.org/api/0.6/way/{way_id}"
HTTP_HEADERS = {"User-Agent": "AthensOne/0.1 (Apps4Athens hackathon prototype)"}

# Small OSM tiles covering Syntagma–Monastiraki–Plaka (each < 50k nodes API limit).
# Source: verified live against api.openstreetmap.org/api/0.6/map on 2026-11-21. Certainty: verified.
OSM_ACCESS_TILES = (
    "23.7250,37.9720,23.7360,37.9780",  # Syntagma – Ermou – Monastiraki – upper Plaka
    "23.7250,37.9685,23.7360,37.9720",  # Lower Plaka – Acropolis north slope (extra ramp=yes)
)

# Upper sanity cap for PM2.5 (µg/m³) to exclude a single faulty CKAN sensor spike (2018.6 µg/m³).
# Source: inspected in opendata.cityofathens.gr snapshot 2026-11-21T14:00:00Z. Certainty: verified.
PM25_SANITY_MAX = 150.0

# Douglas-Peucker simplification tolerance in degrees (~45 m at 38°N) for offline base.geojson polygons.
# Source: derived for compact offline basemap rendering (~30–50 KB). Certainty: derived.
SIMPLIFY_TOL_DEG = 0.0004

# Official Athens Metro (STASY) & Suburban Railway (OASA/Hellenic Train) line colours.
# Source: STASY / OASA official Athens transit network signage & maps (Line 1 green, Line 2 red,
# Line 3 blue, Proastiakos yellow). Certainty: high (standard public branding hex approximations).
TRANSIT_LINE_COLORS = {
    "M1": "#007A3D",          # Γραμμή 1 (Πειραιάς – Κηφισιά, πράσινη)
    "M2": "#E30613",          # Γραμμή 2 (Ανθούπολη – Ελληνικό, κόκκινη)
    "M3": "#0052A5",          # Γραμμή 3 (Δημοτικό Θέατρο – Αεροδρόμιο, μπλε)
    "PROASTIAKOS": "#F2A900", # Προαστιακός Αθηνών (κίτρινη)
}

# Central Athens Metro & Suburban Railway stations with coordinates verified from OSM on 2026-11-21.
# elevator: True where OSM wheelchair=yes on the station node (all M2/M3 & renovated M1 stations),
# None where OSM had no wheelchair/elevator tag (Ρουφ).
# Source: OpenStreetMap nodes (IDs listed per entry), verified 2026-11-21. Certainty: verified (coords), high (elevator).
TRANSIT_STATIONS = [
    {"id": "ST-SYN", "name": "Σύνταγμα", "lines": ["M2", "M3"], "elevator": True, "osm_id": "node/5374534510", "coords": [23.735668, 37.975495]},
    {"id": "ST-MON", "name": "Μοναστηράκι", "lines": ["M1", "M3"], "elevator": True, "osm_id": "node/9666216537", "coords": [23.725630, 37.976096]},
    {"id": "ST-OMO", "name": "Ομόνοια", "lines": ["M1", "M2"], "elevator": True, "osm_id": "node/5374594466", "coords": [23.727990, 37.984113]},
    {"id": "ST-PAN", "name": "Πανεπιστήμιο", "lines": ["M2"], "elevator": True, "osm_id": "node/250920014", "coords": [23.733020, 37.980355]},
    {"id": "ST-AKR", "name": "Ακρόπολη", "lines": ["M2"], "elevator": True, "osm_id": "node/1957144319", "coords": [23.729531, 37.968859]},
    {"id": "ST-FIX", "name": "Συγγρού-Φιξ", "lines": ["M2"], "elevator": True, "osm_id": "node/1957144329", "coords": [23.726818, 37.964626]},
    {"id": "ST-MET", "name": "Μεταξουργείο", "lines": ["M2"], "elevator": True, "osm_id": "node/251083112", "coords": [23.721380, 37.985853]},
    {"id": "ST-LAR", "name": "Σταθμός Λαρίσης", "lines": ["M2", "PROASTIAKOS"], "elevator": True, "osm_id": "node/251083102", "coords": [23.720720, 37.992282]},
    {"id": "ST-ATT", "name": "Αττική", "lines": ["M1", "M2"], "elevator": True, "osm_id": "node/1956875655", "coords": [23.722838, 37.999524]},
    {"id": "ST-EVA", "name": "Ευαγγελισμός", "lines": ["M3"], "elevator": True, "osm_id": "node/250702355", "coords": [23.747104, 37.976126]},
    {"id": "ST-MEG", "name": "Μέγαρο Μουσικής", "lines": ["M3"], "elevator": True, "osm_id": "node/250702349", "coords": [23.753009, 37.979032]},
    {"id": "ST-AMP", "name": "Αμπελόκηποι", "lines": ["M3"], "elevator": True, "osm_id": "node/1958901557", "coords": [23.757680, 37.987193]},
    {"id": "ST-PNO", "name": "Πανόρμου", "lines": ["M3"], "elevator": True, "osm_id": "node/1958901565", "coords": [23.763577, 37.993212]},
    {"id": "ST-KER", "name": "Κεραμεικός", "lines": ["M3"], "elevator": True, "osm_id": "node/850935197", "coords": [23.710957, 37.978743]},
    {"id": "ST-THI", "name": "Θησείο", "lines": ["M1"], "elevator": True, "osm_id": "node/2284727248", "coords": [23.720329, 37.976766]},
    {"id": "ST-PET", "name": "Πετράλωνα", "lines": ["M1"], "elevator": True, "osm_id": "node/2278849833", "coords": [23.709044, 37.968347]},
    {"id": "ST-VIC", "name": "Βικτώρια", "lines": ["M1"], "elevator": True, "osm_id": "node/251082983", "coords": [23.730266, 37.993073]},
    {"id": "ST-ROU", "name": "Ρουφ", "lines": ["PROASTIAKOS"], "elevator": None, "osm_id": "node/987485685", "coords": [23.703965, 37.973633]},
]

# Real central Athens public hospitals verified via OSM Nominatim on 2026-11-21.
# Phone numbers fetched from OSM way tags when present (otherwise "άγνωστο").
# on_duty flags and demo specialties are illustrative for offline demo (documented in note).
# Source: OpenStreetMap (Nominatim/API 0.6, ODbL 1.0), verified 2026-11-21. Certainty: verified (coords/names), mock (on_duty).
HOSPITALS = [
    {
        "osm_way": 132620005,
        "name": "Γ.Ν.Α. «Ο Ευαγγελισμός»",
        "address": "Υψηλάντου 45-47, Κολωνάκι",
        "coords": [23.74775, 37.97785],
        "hours": "24ωρη εφημερία (08:00–08:00)",
        "specialties": ["Παθολογική", "Χειρουργική", "Καρδιολογική", "Ορθοπεδική", "Νευρολογική"],
        "on_duty": True,
    },
    {
        "osm_way": 132795203,
        "name": "Γ.Ν.Α. «Ιπποκράτειο»",
        "address": "Λεωφ. Βασιλίσσης Σοφίας 114, Αμπελόκηποι",
        "coords": [23.75970, 37.98373],
        "hours": "Εφημερία 08:00–20:00",
        "specialties": ["Καρδιολογική", "Παθολογική", "ΩΡΛ"],
        "on_duty": True,
    },
    {
        "osm_way": 169296315,
        "name": "Γ.Ν.Α. «Λαϊκό»",
        "address": "Αγίου Θωμά 17, Γουδή",
        "coords": [23.76518, 37.98408],
        "hours": "Κανονική λειτουργία (δεν εφημερεύει σήμερα)",
        "specialties": ["Παθολογική", "Χειρουργική", "Ουρολογική"],
        "on_duty": False,
    },
    {
        "osm_way": 132748278,
        "name": "Γ.Ν.Α. «Αλεξάνδρα»",
        "address": "Λεωφ. Βασιλίσσης Σοφίας 80, Ιλίσια",
        "coords": [23.75539, 37.98013],
        "hours": "Κανονική λειτουργία (δεν εφημερεύει σήμερα)",
        "specialties": ["Μαιευτική-Γυναικολογική", "Καρδιολογική", "Παθολογική"],
        "on_duty": False,
    },
    {
        "osm_way": 140757110,
        "name": "Γ.Ν.Α. «Η Ελπίς»",
        "address": "Δημητσάνας 7, Αμπελόκηποι",
        "coords": [23.75544, 37.99023],
        "hours": "Εφημερία 08:00–20:00",
        "specialties": ["Παθολογική", "Χειρουργική", "Καρδιολογική"],
        "on_duty": True,
    },
    {
        "osm_way": 132748295,
        "name": "Αρεταίειο Νοσοκομείο",
        "address": "Λεωφ. Βασιλίσσης Σοφίας 76, Ιλίσια",
        "coords": [23.75480, 37.97952],
        "hours": "Κανονική λειτουργία (δεν εφημερεύει σήμερα)",
        "specialties": ["Χειρουργική", "Μαιευτική-Γυναικολογική"],
        "on_duty": False,
    },
]

# Real OSM pharmacy locations around Syntagma–Monastiraki–Plaka (verified live via OSM API 0.6 on 2026-11-21).
# on_duty flags & duty hours are invented for offline demo because ΦΣΑ has no official open API.
# Source: OpenStreetMap nodes (IDs listed), verified 2026-11-21. Certainty: verified (locations), mock (on_duty/hours).
PHARMACIES = [
    {
        "osm_id": "node/4040067164",
        "name": "Φαρμακείο Καραγιώργη Σερβίας 4",
        "address": "Καραγιώργη Σερβίας 4, Σύνταγμα",
        "phone": "άγνωστο",
        "hours": "Εφημερεύει 08:00–23:00 (δοκιμαστική εφημερία)",
        "specialties": ["Εφημερεύον φαρμακείο"],
        "on_duty": True,
        "coords": [23.73400, 37.97638],  # 120 m from Syntagma
    },
    {
        "osm_id": "node/3998346581",
        "name": "Φαρμακείο Πινοτσή",
        "address": "Μητροπόλεως 27, Σύνταγμα",
        "phone": "άγνωστο",
        "hours": "Διανυκτερεύει 08:00–08:00 (δοκιμαστική εφημερία)",
        "specialties": ["Διανυκτερεύον φαρμακείο"],
        "on_duty": True,
        "coords": [23.73118, 37.97527],  # 319 m from Syntagma
    },
    {
        "osm_id": "node/9121224837",
        "name": "Metropolis Pharmacy",
        "address": "Μητροπόλεως 52, Μοναστηράκι",
        "phone": "+30 210 3310052",  # verified in OSM node/9121224837 tag phone
        "hours": "Εφημερεύει 08:00–23:00 (δοκιμαστική εφημερία)",
        "specialties": ["Εφημερεύον φαρμακείο"],
        "on_duty": True,
        "coords": [23.72954, 37.97565],  # 462 m from Syntagma
    },
    {
        "osm_id": "node/12486804563",
        "name": "Φαρμακείο Σταδίου 5",
        "address": "Σταδίου 5, Σύνταγμα",
        "phone": "άγνωστο",
        "hours": "08:30–14:30 (κλειστό εκτός ωραρίου)",
        "specialties": ["Φαρμακείο"],
        "on_duty": False,
        "coords": [23.73379, 37.97674],  # 164 m from Syntagma
    },
    {
        "osm_id": "node/4041656119",
        "name": "Φαρμακείο Ζάγκος – Βαιδάκη",
        "address": "Διομείας 10-12, Σύνταγμα",
        "phone": "άγνωστο",
        "hours": "08:30–14:30",
        "specialties": ["Φαρμακείο"],
        "on_duty": False,
        "coords": [23.73190, 37.97632],  # 270 m from Syntagma
    },
    {
        "osm_id": "node/2696698086",
        "name": "Φαρμακείο Σωτήρος 5",
        "address": "Σωτήρος 5, Πλάκα",
        "phone": "άγνωστο",
        "hours": "08:30–14:30",
        "specialties": ["Φαρμακείο"],
        "on_duty": False,
        "coords": [23.73172, 37.97290],  # 396 m from Syntagma
    },
]

# Points rules from SPEC.md «Κανόνες πόντων».
# Source: athensone/docs/SPEC.md lines 148-156. Certainty: verified.
POINTS_RULES = {
    "incident": 5,         # Αναφορά συμβάντος / συμφόρησης
    "confirm": 2,          # Επιβεβαίωση αναφοράς άλλου
    "work_photo": 15,      # Αναφορά προόδου έργου με φωτογραφία
    "city_verified": 20,   # Αναφορά που επιβεβαιώνει ο Δήμος (+20 bonus)
}

# Collective district goal default (matches app/points.py DISTRICT_TARGET & DECISIONS.md A-9).
# Source: athensone/app/points.py line 76 / DECISIONS.md A-9. Certainty: verified.
DISTRICT_GOAL = 5000


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _clamp_pt(lon: float, lat: float) -> list[float]:
    """Clamp a WGS84 coordinate to the Athens bbox and round to 6 decimals."""
    return [
        round(max(LON_MIN, min(LON_MAX, lon)), 6),
        round(max(LAT_MIN, min(LAT_MAX, lat)), 6),
    ]


def _perp_dist(pt: list[float], a: list[float], b: list[float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0.0 and dy == 0.0:
        return math.hypot(pt[0] - a[0], pt[1] - a[1])
    t = max(0.0, min(1.0, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(pt[0] - (a[0] + t * dx), pt[1] - (a[1] + t * dy))


def _simplify_ring(pts: list[list[float]], tol: float) -> list[list[float]]:
    """Recursive Douglas-Peucker simplification for a closed ring."""
    if len(pts) <= 5:
        return pts

    def dp(seq: list[list[float]]) -> list[list[float]]:
        if len(seq) <= 2:
            return seq
        dmax, idx = 0.0, 0
        for i in range(1, len(seq) - 1):
            d = _perp_dist(seq[i], seq[0], seq[-1])
            if d > dmax:
                dmax, idx = d, i
        if dmax > tol:
            left = dp(seq[: idx + 1])
            right = dp(seq[idx:])
            return left[:-1] + right
        return [seq[0], seq[-1]]

    core = dp(pts[:-1])
    if len(core) < 3:
        return pts[:4] + [pts[0]]
    return core + [core[0]]


def _find_ckan_dir(override: str | None) -> Path | None:
    """Locate local CKAN snapshot directory (worktree data/ckan or main checkout)."""
    candidates = []
    if override:
        candidates.append(Path(override))
    candidates.append(APP_ROOT / "data" / "ckan")
    # When running inside .worktrees/<task>/athensone, main checkout is 3 levels up.
    if len(APP_ROOT.parents) >= 3:
        candidates.append(APP_ROOT.parents[2] / "athensone" / "data" / "ckan")
    for p in candidates:
        if p.is_dir():
            return p
    return None


def _write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. env.json
# ---------------------------------------------------------------------------

def _norm_el(text: str | None) -> str:
    """Uppercase accent-stripped Greek/Latin string for neighbourhood name matching."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFD", str(text).upper())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").strip()


def build_env(ckan_dir: Path | None) -> dict:
    """Build web/mock/env.json from Municipality of Athens CKAN air-quality snapshot."""
    features: list[dict] = []
    source_desc = ""

    if ckan_dir is not None:
        neigh_p = ckan_dir / "datastore_search___limit___1000___resource_id____0283af02-7783-4688-897b-7153da7ed2fd__.json"
        reg_p = ckan_dir / "datastore_search___limit___1000___resource_id____47ba486c-4ecf-497e-892b-4e47c53f422a__.json"
        env_p = ckan_dir / "datastore_search___limit___312___resource_id____a84cabca-bd0c-434d-8bee-21c082183442____sort____timestamp_desc__.json"
        if neigh_p.is_file() and reg_p.is_file() and env_p.is_file():
            neigh = json.loads(neigh_p.read_text(encoding="utf-8"))["result"]["records"]
            reg = json.loads(reg_p.read_text(encoding="utf-8"))["result"]["records"]
            env_all = json.loads(env_p.read_text(encoding="utf-8"))["result"]["records"]

            nmap: dict[str, tuple[float, float, str]] = {}
            by_name: dict[str, tuple[float, float, str]] = {}
            for r in neigh:
                if r.get("position_lon") and r.get("position_lat"):
                    entry = (
                        float(r["position_lon"]),
                        float(r["position_lat"]),
                        r.get("friendly_name") or r.get("name") or "",
                    )
                    nmap[str(r["neighbourhood_id"])] = entry
                    for key in ("friendly_name", "name"):
                        nk = _norm_el(r.get(key))
                        if nk:
                            by_name[nk] = entry
            smap = {
                int(r["station_id"]): str(r["neighbourhood_id"])
                for r in reg
                if r.get("station_id") and r.get("neighbourhood_id")
            }

            latest: dict[int, dict] = {}
            for r in env_all:
                sid = r.get("station_id")
                if sid is None or sid in latest:
                    continue
                t, aqi, pm25 = r.get("temperature"), r.get("aqi"), r.get("pm2_5")
                if t is None or aqi is None or pm25 is None:
                    continue
                if pm25 > PM25_SANITY_MAX:
                    continue
                latest[int(sid)] = r

            for sid, r in sorted(latest.items()):
                nid = smap.get(sid)
                loc = nmap.get(nid) if nid else None
                if loc is None:
                    loc = by_name.get(_norm_el(r.get("neighbourhood_name")))
                if loc is None:
                    continue
                lon, lat, nname = loc
                if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
                    continue
                ts = str(r.get("timestamp") or f"{SNAPSHOT_DATE}T14:00:00")
                if not ts.endswith("Z") and "+" not in ts:
                    ts += "Z"
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                    "properties": {
                        "station_id": sid,
                        "neighbourhood": nname,
                        "temp_c": round(float(r["temperature"]), 2),
                        "aqi": int(r["aqi"]),
                        "aqi_scale": "city_1_6",  # AthensGov CKAN env-all-stations, AQI class 1-6 (A-37)
                        "pm25": round(float(r["pm2_5"]), 1),
                        "updated_at": ts,
                        "location_precision": "neighbourhood_centre",
                    },
                })
            source_desc = (
                f"Real Municipality of Athens environmental sensor snapshot ({len(features)} stations) from "
                "opendata.cityofathens.gr (env-all-stations joined to neighbourhoods-athens centroids, "
                "CC BY 4.0, 2026-11-21T14:00:00Z). Stations are placed at neighbourhood centroids "
                "(DECISIONS.md A-21); one faulty PM2.5 outlier (>150 µg/m³) was excluded. Temperatures span "
                "20.87–27.32 °C with a warmer/higher-PM2.5 zone around Ψυρρή–Κουμουνδούρου "
                "(25.26 °C, AQI 4, PM2.5 45.8 µg/m³)."
            )

    if len(features) < 20:
        # Deterministic fallback grid over Municipality of Athens if CKAN cache is absent.
        # Values are synthetic approximations centred on a warm/polluted core near Omonia–Psyrri.
        # Source: fallback synthetic model. Certainty: mock.
        features = []
        for ix in range(5):
            for iy in range(5):
                lon = round(23.705 + ix * 0.015, 5)
                lat = round(37.962 + iy * 0.012, 5)
                dist_core = math.hypot((lon - 23.728) * 88.0, (lat - 37.981) * 111.0)
                temp = round(max(21.0, 26.8 - dist_core * 1.1), 1)
                pm25 = round(max(5.0, 38.0 - dist_core * 6.0), 1)
                aqi = 4 if pm25 > 30 else (3 if pm25 > 18 else 2)
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "temp_c": temp,
                        "aqi": aqi,
                        "aqi_scale": "city_1_6",  # AthensGov CKAN env-all-stations, AQI class 1-6 (A-37)
                        "pm25": pm25,
                        "updated_at": f"{SNAPSHOT_DATE}T14:00:00Z",
                    },
                })
        source_desc = "Synthetic offline grid fallback (25 points) over Athens with a hotter core near Omonia–Psyrri."

    return {
        "type": "FeatureCollection",
        "snapshot": SNAPSHOT_DATE,
        "note": source_desc,
        "features": features,
    }


# ---------------------------------------------------------------------------
# 2. access.geojson
# ---------------------------------------------------------------------------

def build_access() -> dict:
    """Download real OSM accessibility features around Syntagma–Monastiraki–Plaka."""
    seen_ids: set[str] = set()
    by_kind: dict[str, list[dict]] = {
        "kerb_lowered": [],
        "ramp": [],
        "tactile_paving": [],
        "wheelchair": [],
    }

    for bbox in OSM_ACCESS_TILES:
        r = httpx.get(OSM_API_MAP, params={"bbox": bbox}, headers=HTTP_HEADERS, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        nodes = {
            el.attrib["id"]: (float(el.attrib["lon"]), float(el.attrib["lat"]))
            for el in root.findall("node")
        }

        for el in root:
            if el.tag not in ("node", "way"):
                continue
            tags = {t.attrib["k"]: t.attrib["v"] for t in el.findall("tag")}
            if not tags:
                continue
            osm_id = f"{el.tag}/{el.attrib['id']}"
            if osm_id in seen_ids:
                continue

            kind: str | None = None
            if tags.get("ramp") == "yes" or tags.get("ramp:wheelchair") == "yes":
                kind = "ramp"
            elif tags.get("kerb") == "lowered":
                kind = "kerb_lowered"
            elif tags.get("tactile_paving") == "yes":
                kind = "tactile_paving"
            elif tags.get("wheelchair") in ("yes", "limited") and tags.get("name"):
                kind = "wheelchair"
            if kind is None:
                continue

            if el.tag == "node":
                lon, lat = float(el.attrib["lon"]), float(el.attrib["lat"])
                if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
                    continue
                geom = {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}
            else:
                pts = [nodes[nd.attrib["ref"]] for nd in el.findall("nd") if nd.attrib["ref"] in nodes]
                pts = [(round(x, 6), round(y, 6)) for x, y in pts if LON_MIN <= x <= LON_MAX and LAT_MIN <= y <= LAT_MAX]
                if len(pts) < 2:
                    continue
                # Use midpoint Point for ramp/wheelchair buildings, LineString for street tactile paving.
                if kind == "tactile_paving" and "highway" in tags:
                    geom = {"type": "LineString", "coordinates": [[x, y] for x, y in pts]}
                else:
                    mid = pts[len(pts) // 2]
                    geom = {"type": "Point", "coordinates": [mid[0], mid[1]]}

            props: dict[str, object] = {
                "osm_id": osm_id,
                "kind": kind,
            }
            if tags.get("name"):
                props["name"] = tags["name"]
            if tags.get("wheelchair"):
                props["wheelchair"] = tags["wheelchair"]
            if tags.get("highway"):
                props["highway"] = tags["highway"]
            if tags.get("surface"):
                props["surface"] = tags["surface"]

            seen_ids.add(osm_id)
            by_kind[kind].append({"type": "Feature", "geometry": geom, "properties": props})

    # Keep all kerb_lowered, ramps, tactile_paving; cap named wheelchair POIs at 35 to stay lightweight.
    features = (
        by_kind["kerb_lowered"]
        + by_kind["ramp"]
        + by_kind["tactile_paving"][:25]
        + by_kind["wheelchair"][:35]
    )

    return {
        "type": "FeatureCollection",
        "snapshot": SNAPSHOT_DATE,
        "note": (
            "Real OpenStreetMap accessibility features (kerb=lowered, ramp=yes, tactile_paving=yes, "
            "named wheelchair=yes/limited POIs) extracted via OSM API 0.6 around Σύνταγμα–Μοναστηράκι–Πλάκα "
            "on 2026-11-21. Data © OpenStreetMap contributors (ODbL 1.0). Nothing invented."
        ),
        "features": features,
    }


# ---------------------------------------------------------------------------
# 3. works.geojson
# ---------------------------------------------------------------------------

def build_works() -> dict:
    """Build web/mock/works.geojson: 10 real Diavgeia-backed Athens works + 2 SEED demo works.

    Every real work carries its exact Diavgeia ADA, source_url (https://diavgeia.gov.gr/decision/view/<ADA>),
    contractor, ADAM (where printed in the decision subject), and payment amount verified via the
    Diavgeia OpenData API (organizationUid=6013, Δήμος Αθηναίων) on 2026-11-21.
    Fields absent from Diavgeia payment metadata (amount_contract_eur, end_date, guarantee_end) are
    kept as null (unknown) rather than invented. Two clearly marked SEED works (ada="SEED-...", seed=True)
    supply complete contract/guarantee figures so the UI progress bar & countdown work offline.
    """
    # Real street polylines inside central Athens (coordinates checked against OSM 2026-11-21).
    # Note: framework contracts covering a whole Municipal District are mapped to representative street segments.
    works = [
        # --- 10 REAL Diavgeia-backed Municipality of Athens works (verified live 2026-11-21) ---
        {
            "id": "W-DIAV-001",
            "title": "Ενεργειακή αναβάθμιση και βελτίωση προσβασιμότητας πεζοδρομίων στην 1η, 2η & 3η Δ.Κ. (τμήμα Ερμού)",
            "status": "in_progress",
            "contractor": "ΩΡΙΩΝ Α.Τ.Ε.",
            "amount_contract_eur": None,  # Not in Diavgeia Β.2.2 metadata; joined via ΚΗΜΔΗΣ in B2
            "amount_paid_eur": 200023.43,  # Verified Diavgeia Β.2.2 Ψ0ΣΝΩ6Μ-5ΙΖ (1ος λογαριασμός Α' μέρος)
            "ada": "Ψ0ΣΝΩ6Μ-5ΙΖ",
            "adam": "25SYMV018045625",
            "start_date": "2025-11-28",    # ΣΥΜΦ. 303405/28-11-2025 in decision subject
            "end_date": None,
            "guarantee_end": None,
            "reports_count": 4,
            "source_url": "https://diavgeia.gov.gr/decision/view/Ψ0ΣΝΩ6Μ-5ΙΖ",
            "seed": False,
            # Real Ermou street segment between Syntagma and Monastiraki (demo step 4: 0 m from route)
            "coords": [[23.7341, 37.9756], [23.7322, 37.9758], [23.7302, 37.9760], [23.7283, 37.9762]],
        },
        {
            "id": "W-DIAV-002",
            "title": "Ολοκληρωμένο σύστημα ελέγχου πρόσβασης οχημάτων στο Εμπορικό Τρίγωνο και σε πεζοδρόμους (Υποέργο 8)",
            "status": "in_progress",
            "contractor": "ΓΚΛΟΜΠΙΣΜΑΡΤ Α.Ε.",
            "amount_contract_eur": None,
            "amount_paid_eur": 1439806.20,  # Verified Diavgeia Β.2.2 9ΤΠΜΩ6Μ-ΩΥΚ (2ος λογαριασμός)
            "ada": "9ΤΠΜΩ6Μ-ΩΥΚ",
            "adam": None,
            "start_date": None,
            "end_date": None,
            "guarantee_end": None,
            "reports_count": 2,
            "source_url": "https://diavgeia.gov.gr/decision/view/9ΤΠΜΩ6Μ-ΩΥΚ",
            "seed": False,
            # Commercial Triangle (Kolokotroni – Perikleous)
            "coords": [[23.7330, 37.9776], [23.7311, 37.9775], [23.7294, 37.9774]],
        },
        {
            "id": "W-DIAV-003",
            "title": "Άρση επικινδυνότητας σε οδοστρώματα, πεζοδρόμια και κοινόχρηστους χώρους του Δ.Α. (τμήμα Πανεπιστημίου)",
            "status": "in_progress",
            "contractor": "ΔΟΜΙΚΗ ΑΘΗΝΩΝ Α.Τ.Ε.",
            "amount_contract_eur": None,
            "amount_paid_eur": 51835.50,  # Verified Diavgeia Β.2.2 65ΨΟΩ6Μ-675 (1ος λογαριασμός)
            "ada": "65ΨΟΩ6Μ-675",
            "adam": "26SYMV019449260",
            "start_date": "2026-07-14",   # ΣΥΜΦ. 186804/14-07-2026 in decision subject
            "end_date": None,
            "guarantee_end": None,
            "reports_count": 3,
            "source_url": "https://diavgeia.gov.gr/decision/view/65ΨΟΩ6Μ-675",
            "seed": False,
            # Panepistimiou Ave
            "coords": [[23.7351, 37.9773], [23.7336, 37.9794], [23.7322, 37.9814]],
        },
        {
            "id": "W-DIAV-004",
            "title": "Λειτουργική και ενεργειακή αναβάθμιση πεζοδρομίων σε όλες τις Δ.Κ. του Δ.Α. (τμήμα Σταδίου)",
            "status": "in_progress",
            "contractor": "ΟΔΟΣ Α.Τ.Ε.",
            "amount_contract_eur": None,
            "amount_paid_eur": 985371.42,  # Verified Diavgeia Β.2.2 91Π7Ω6Μ-ΠΕ8 (6ος λογαριασμός)
            "ada": "91Π7Ω6Μ-ΠΕ8",
            "adam": "23SYMV013654256",
            "start_date": "2023-10-25",    # ΣΥΜΦ. 298348/25-10-2023 in decision subject
            "end_date": None,
            "guarantee_end": None,
            "reports_count": 5,
            "source_url": "https://diavgeia.gov.gr/decision/view/91Π7Ω6Μ-ΠΕ8",
            "seed": False,
            # Stadiou St
            "coords": [[23.7337, 37.9768], [23.7318, 37.9792], [23.7297, 37.9818]],
        },
        {
            "id": "W-DIAV-005",
            "title": "Ενεργειακή αναβάθμιση και βελτίωση προσβασιμότητας πεζοδρομίων στην 4η και 5η Δ.Κ. (τμήμα Πατησίων)",
            "status": "in_progress",
            "contractor": "ΕΡΓΟΡΟΗ Α.Τ.Ε.",
            "amount_contract_eur": None,
            "amount_paid_eur": 155332.03,  # Verified Diavgeia Β.2.2 ΡΠΟ8Ω6Μ-ΟΥΟ (1ος λογαριασμός)
            "ada": "ΡΠΟ8Ω6Μ-ΟΥΟ",
            "adam": "25SYMV018041517",
            "start_date": "2025-11-28",    # ΣΥΜΦ. 303401/28-11-2025 in decision subject
            "end_date": None,
            "guarantee_end": None,
            "reports_count": 2,
            "source_url": "https://diavgeia.gov.gr/decision/view/ΡΠΟ8Ω6Μ-ΟΥΟ",
            "seed": False,
            # Patision Ave (5th Municipal District)
            "coords": [[23.7327, 37.9975], [23.7336, 38.0020], [23.7347, 38.0068]],
        },
        {
            "id": "W-DIAV-006",
            "title": "Ανακατασκευή οδοστρωμάτων με αντιολισθηρό σκυρόδεμα και εγκάρσιων ρείθρων (τμήμα Αθηνάς)",
            "status": "in_progress",
            "contractor": "ΜΑΖΑΡΑΚΗΣ ΗΛΙΑΣ",
            "amount_contract_eur": None,
            "amount_paid_eur": 228763.79,  # Verified Diavgeia Β.2.2 6ΔΩ6Ω6Μ-2ΘΖ (6ος λογαριασμός)
            "ada": "6ΔΩ6Ω6Μ-2ΘΖ",
            "adam": "24SYMV015992336",
            "start_date": "2024-12-12",    # ΑΡ.ΣΥΜΦ. 321214/12-12-2024 in decision subject
            "end_date": None,
            "guarantee_end": None,
            "reports_count": 1,
            "source_url": "https://diavgeia.gov.gr/decision/view/6ΔΩ6Ω6Μ-2ΘΖ",
            "seed": False,
            # Athinas St (Monastiraki – Varvakeios – Omonia)
            "coords": [[23.7261, 37.9770], [23.7269, 37.9798], [23.7276, 37.9826]],
        },
        {
            "id": "W-DIAV-007",
            "title": "Ενεργειακή αναβάθμιση & αυτοματοποίηση του συστήματος οδοφωτισμού του Δ.Α. (τμήμα Λεωφ. Αλεξάνδρας)",
            "status": "in_progress",
            "contractor": "METLEN ENERGY & METALS ΜΟΝΟΠΡΟΣΩΠΗ Α.Ε.",
            "amount_contract_eur": None,
            "amount_paid_eur": 370026.02,  # Verified Diavgeia Β.2.2 Ψ15ΕΩ6Μ-4Γ0 (8ος λογαριασμός)
            "ada": "Ψ15ΕΩ6Μ-4Γ0",
            "adam": "22SYMV010935743",
            "start_date": "2022-07-14",    # ΣΥΜΒΑΣΗ 198220/14-07-22 in decision subject
            "end_date": None,
            "guarantee_end": None,
            "reports_count": 1,
            "source_url": "https://diavgeia.gov.gr/decision/view/Ψ15ΕΩ6Μ-4Γ0",
            "seed": False,
            # Alexandras Ave
            "coords": [[23.7398, 37.9906], [23.7475, 37.9896], [23.7556, 37.9880]],
        },
        {
            "id": "W-DIAV-008",
            "title": "Έργα οδοποιίας και κατασκευή δικτύων ομβρίων και αποχέτευσης στην περιοχή του Ελαιώνα (Υποέργο 1)",
            "status": "in_progress",
            "contractor": "ΖΙΤΑΚΑΤ Α.Τ.Ε.",
            "amount_contract_eur": None,
            "amount_paid_eur": 1769478.05,  # Verified Diavgeia Β.2.2 ΡΔΦΨΩ6Μ-ΥΘ4 (5ος λογαριασμός)
            "ada": "ΡΔΦΨΩ6Μ-ΥΘ4",
            "adam": None,
            "start_date": None,
            "end_date": None,
            "guarantee_end": None,
            "reports_count": 0,
            "source_url": "https://diavgeia.gov.gr/decision/view/ΡΔΦΨΩ6Μ-ΥΘ4",
            "seed": False,
            # Iera Odos / Elaionas (inside LON_MIN 23.68)
            "coords": [[23.6880, 37.9825], [23.6945, 37.9815], [23.7010, 37.9804]],
        },
        {
            "id": "W-DIAV-009",
            "title": "Ενεργειακή αναβάθμιση μέσω της αναβάθμισης βατότητας πεζοδρομίων και οδών (επιστροφή εγγυήσεων)",
            "status": "completed",
            "contractor": None,
            "amount_contract_eur": None,
            "amount_paid_eur": None,
            "ada": "ΨΓΟ3Ω6Μ-ΔΚ6",          # Verified Diavgeia 2.4.7.1 (2026-11-17)
            "adam": None,
            "start_date": None,
            "end_date": "2026-11-17",       # Decision date on Diavgeia
            "guarantee_end": None,
            "reports_count": 0,
            "source_url": "https://diavgeia.gov.gr/decision/view/ΨΓΟ3Ω6Μ-ΔΚ6",
            "seed": False,
            # Filellinon St
            "coords": [[23.7346, 37.9746], [23.7339, 37.9729], [23.7333, 37.9712]],
        },
        {
            "id": "W-DIAV-010",
            "title": "Έγκριση τοπικής διαπλάτυνσης πεζοδρομίων στις διαβάσεις επί της οδού Παπανικολάου (Ο.Τ. 471)",
            "status": "planned",
            "contractor": None,
            "amount_contract_eur": None,
            "amount_paid_eur": None,
            "ada": "ΨΣ9ΧΩ6Μ-6ΚΨ",          # Verified Diavgeia 2.4.7.1 (2026-11-05)
            "adam": None,
            "start_date": None,
            "end_date": None,
            "guarantee_end": None,
            "reports_count": 0,
            "source_url": "https://diavgeia.gov.gr/decision/view/ΨΣ9ΧΩ6Μ-6ΚΨ",
            "seed": False,
            # Ampelokipoi / Goudi area
            "coords": [[23.7640, 37.9890], [23.7656, 37.9896], [23.7672, 37.9901]],
        },
        # --- 2 clearly-flagged SEED works (for progress bar & guarantee countdown demo) ---
        {
            "id": "W-SEED-001",
            "title": "Ανακατασκευή πεζοδρομίων και ραμπών ΑμεΑ οδού Μητροπόλεως (δείγμα SEED)",
            "status": "in_progress",
            "contractor": "Ανάδοχος Δείγματος Α (SEED)",
            "amount_contract_eur": 185000.0,
            "amount_paid_eur": 118400.0,
            "ada": "SEED-ΑΔΑ-001",
            "adam": "SEED-26SYMV-001",
            "start_date": "2026-06-01",
            "end_date": "2026-12-20",
            "guarantee_end": "2028-03-20",  # +15 months general guarantee term (ν. 4412/2016 art. 171)
            "reports_count": 3,
            "source_url": None,
            "seed": True,
            # Mitropoleos St (parallel to Ermou, near Syntagma–Monastiraki)
            "coords": [[23.7336, 37.9752], [23.7312, 37.9753], [23.7289, 37.9755]],
        },
        {
            "id": "W-SEED-002",
            "title": "Ασφαλτόστρωση και αποκατάσταση πεζοδρομίων οδού Υμηττού (δείγμα SEED)",
            "status": "completed",
            "contractor": "Ανάδοχος Δείγματος Β (SEED)",
            "amount_contract_eur": 96000.0,
            "amount_paid_eur": 92400.0,
            "ada": "SEED-ΑΔΑ-002",
            "adam": "SEED-25SYMV-002",
            "start_date": "2025-05-10",
            "end_date": "2026-02-15",
            "guarantee_end": "2027-05-15",  # +15 months (175 days remaining on 2026-11-21)
            "reports_count": 2,
            "source_url": None,
            "seed": True,
            # Ymittou St, Pangrati
            "coords": [[23.7438, 37.9688], [23.7462, 37.9693], [23.7486, 37.9698]],
        },
    ]

    features = []
    for w in works:
        coords = [_clamp_pt(lon, lat) for lon, lat in w["coords"]]
        props = {k: v for k, v in w.items() if k != "coords"}
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": props,
        })

    return {
        "type": "FeatureCollection",
        "snapshot": SNAPSHOT_DATE,
        "note": (
            "10 real Municipality of Athens (org 6013) public-works decisions verified live on diavgeia.gov.gr "
            "on 2026-11-21 (real ADA, source_url, contractor, payment amount, ADAM and contract date where "
            "published; district-wide framework contracts are mapped to representative street segments, and "
            "fields absent from Diavgeia metadata remain null) plus 2 clearly marked SEED works (ada='SEED-*', "
            "seed=true) with complete contract/guarantee figures for UI demo testing."
        ),
        "features": features,
    }


# ---------------------------------------------------------------------------
# 4. transit.geojson
# ---------------------------------------------------------------------------

def build_transit() -> dict:
    """Build web/mock/transit.geojson with {lines, stations, buses} FeatureCollections."""
    st_by_id = {s["id"]: s for s in TRANSIT_STATIONS}

    def _line_coords(ids: list[str]) -> list[list[float]]:
        return [_clamp_pt(*st_by_id[i]["coords"]) for i in ids]

    lines_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": _line_coords(["ST-PET", "ST-THI", "ST-MON", "ST-OMO", "ST-VIC", "ST-ATT"])},
                "properties": {"id": "M1", "name": "Μετρό Γραμμή 1 (Πειραιάς – Κηφισιά)", "mode": "subway", "color": TRANSIT_LINE_COLORS["M1"]},
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": _line_coords(["ST-FIX", "ST-AKR", "ST-SYN", "ST-PAN", "ST-OMO", "ST-MET", "ST-LAR", "ST-ATT"])},
                "properties": {"id": "M2", "name": "Μετρό Γραμμή 2 (Ανθούπολη – Ελληνικό)", "mode": "subway", "color": TRANSIT_LINE_COLORS["M2"]},
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": _line_coords(["ST-KER", "ST-MON", "ST-SYN", "ST-EVA", "ST-MEG", "ST-AMP", "ST-PNO"])},
                "properties": {"id": "M3", "name": "Μετρό Γραμμή 3 (Δημ. Θέατρο – Αεροδρόμιο)", "mode": "subway", "color": TRANSIT_LINE_COLORS["M3"]},
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": _line_coords(["ST-ROU", "ST-LAR"])},
                "properties": {"id": "PROASTIAKOS", "name": "Προαστιακός Αθηνών (Πειραιάς – Αθήνα – Αεροδρόμιο)", "mode": "rail", "color": TRANSIT_LINE_COLORS["PROASTIAKOS"]},
            },
        ],
    }

    stations_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": _clamp_pt(*s["coords"])},
                "properties": {
                    "id": s["id"],
                    "name": s["name"],
                    "lines": s["lines"],
                    "elevator": s["elevator"],
                    "osm_id": s["osm_id"],
                },
            }
            for s in TRANSIT_STATIONS
        ],
    }

    # Simulated OASA telematics bus positions along real central Athens avenues.
    # Source: real OASA bus line numbers (X95, 040, 227, A8, 035, 608, E14); positions/bearings simulated for offline demo.
    # Certainty: verified (line numbers/corridors), mock (live coordinates/ETA).
    buses = [
        {"id": "BUS-X95-1", "line": "X95", "bearing": 70, "route_name": "Σύνταγμα – Αεροδρόμιο (Express)", "next_stop": "Ευαγγελισμός", "eta_min": 3, "coords": [23.7412, 37.9759]},
        {"id": "BUS-040-1", "line": "040", "bearing": 210, "route_name": "Πειραιάς – Σύνταγμα", "next_stop": "Φιλελλήνων", "eta_min": 2, "coords": [23.7342, 37.9736]},
        {"id": "BUS-227-1", "line": "227", "bearing": 275, "route_name": "Άνω Πετράλωνα – Άγ. Αρτέμιος", "next_stop": "Μητρόπολη", "eta_min": 4, "coords": [23.7308, 37.9753]},
        {"id": "BUS-A8-1",  "line": "Α8",  "bearing": 12,  "route_name": "Πολυτεχνείο – Ν. Ιωνία – Μαρούσι", "next_stop": "Μουσείο", "eta_min": 2, "coords": [23.7316, 37.9888]},
        {"id": "BUS-035-1", "line": "035", "bearing": 330, "route_name": "Άνω Κυψέλη – Πετράλωνα – Ταύρος", "next_stop": "Ομόνοια", "eta_min": 5, "coords": [23.7305, 37.9808]},
        {"id": "BUS-608-1", "line": "608", "bearing": 55,  "route_name": "Γαλάτσι – Ακαδημία – Νεκρ. Ζωγράφου", "next_stop": "Μέγαρο Μουσικής", "eta_min": 3, "coords": [23.7508, 37.9781]},
        {"id": "BUS-E14-1", "line": "Ε14", "bearing": 240, "route_name": "Σύνταγμα – ΟΑΚΑ – Υπ. Παιδείας (Express)", "next_stop": "Πλατεία Συντάγματος", "eta_min": 1, "coords": [23.7376, 37.9760]},
    ]
    buses_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": _clamp_pt(*b["coords"])},
                "properties": {k: v for k, v in b.items() if k != "coords"},
            }
            for b in buses
        ],
    }

    return {
        "snapshot": SNAPSHOT_DATE,
        "note": (
            "Station coordinates & OSM IDs are real OpenStreetMap data (ODbL 1.0, verified 2026-11-21); "
            "Metro M1/M2/M3 and Proastiakos line colours follow STASY/OASA official branding; "
            "station lines are simplified station-to-station segments; OASA bus positions, bearings and "
            "ETAs are simulated snapshot fixtures for offline demo."
        ),
        "lines": lines_fc,
        "stations": stations_fc,
        "buses": buses_fc,
    }


# ---------------------------------------------------------------------------
# 5. health.geojson
# ---------------------------------------------------------------------------

def _fetch_osm_way_phone(way_id: int) -> str:
    """Return OSM phone tag for a hospital way if present, else 'άγνωστο'."""
    try:
        r = httpx.get(OSM_API_WAY.format(way_id=way_id), headers=HTTP_HEADERS, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            for tag in root.findall(".//tag"):
                if tag.attrib.get("k") in ("phone", "contact:phone") and tag.attrib.get("v"):
                    return tag.attrib["v"]
    except Exception:
        pass
    return "άγνωστο"


def build_health(fetch_phones: bool = True) -> dict:
    """Build web/mock/health.geojson with real central Athens hospitals and OSM pharmacies."""
    features: list[dict] = []

    for h in HOSPITALS:
        phone = _fetch_osm_way_phone(h["osm_way"]) if fetch_phones else "άγνωστο"
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": _clamp_pt(*h["coords"])},
            "properties": {
                "kind": "νοσοκομείο",
                "name": h["name"],
                "address": h["address"],
                "phone": phone,
                "hours": h["hours"],
                "specialties": h["specialties"],
                "on_duty": h["on_duty"],
                "osm_id": f"way/{h['osm_way']}",
            },
        })

    for p in PHARMACIES:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": _clamp_pt(*p["coords"])},
            "properties": {
                "kind": "φαρμακείο",
                "name": p["name"],
                "address": p["address"],
                "phone": p["phone"],
                "hours": p["hours"],
                "specialties": p["specialties"],
                "on_duty": p["on_duty"],
                "osm_id": p["osm_id"],
            },
        })

    return {
        "type": "FeatureCollection",
        "snapshot": SNAPSHOT_DATE,
        "note": (
            "Real central Athens hospitals and pharmacy locations from OpenStreetMap (ODbL 1.0, verified "
            "2026-11-21; phones from OSM tags or 'άγνωστο' when absent). Pharmacy and hospital on_duty "
            "flags, duty hours and specialties are INVENTED for offline demo (ΦΣΑ / Ministry of Health "
            "daily duty lists are not fetched live in mock mode)."
        ),
        "features": features,
    }


# ---------------------------------------------------------------------------
# 6. reports.geojson
# ---------------------------------------------------------------------------

def build_reports() -> dict:
    """Build web/mock/reports.geojson: anonymized citizen reports rounded to 4 decimals (~10 m)."""
    # All coordinates explicitly rounded to 4 decimal places per SPEC «Privacy (GDPR)».
    # Category ids as in B6 (/api/map/reports): congestion συμφόρηση, incident συμβάν, obstacle εμπόδιο, damage ζημιά,
    # work_progress πρόοδος έργου (Greek labels live in ui/report.js).
    # Source: simulated demo citizen reports. Certainty: mock.
    items = [
        {"id": "R-MOCK-01", "category": "obstacle", "created_at": f"{SNAPSHOT_DATE}T09:15:00Z", "confirmations": 4, "description": "Κώνοι και περίφραξη έργου στενεύουν το πεζοδρόμιο στην Ερμού.", "work_id": "W-DIAV-001", "coords": [23.7322, 37.9758]},
        {"id": "R-MOCK-02", "category": "work_progress", "created_at": f"{SNAPSHOT_DATE}T10:05:00Z", "confirmations": 6, "description": "Τοποθετήθηκαν νέες πλάκες και οδηγός όδευσης τυφλών.", "work_id": "W-DIAV-001", "coords": [23.7302, 37.9760]},
        {"id": "R-MOCK-03", "category": "congestion", "created_at": f"{SNAPSHOT_DATE}T11:20:00Z", "confirmations": 7, "description": "Αυξημένη κίνηση οχημάτων στη Σταδίου προς Ομόνοια.", "work_id": None, "coords": [23.7318, 37.9792]},
        {"id": "R-MOCK-04", "category": "damage", "created_at": f"{SNAPSHOT_DATE}T08:40:00Z", "confirmations": 3, "description": "Σπασμένη πλάκα πεζοδρομίου κοντά στη διάβαση Μητροπόλεως.", "work_id": "W-SEED-001", "coords": [23.7312, 37.9753]},
        {"id": "R-MOCK-05", "category": "incident", "created_at": f"{SNAPSHOT_DATE}T12:10:00Z", "confirmations": 2, "description": "Σταθμευμένο φορτηγό κλείνει τη ράμπα ΑμεΑ στην Αθηνάς.", "work_id": None, "coords": [23.7269, 37.9798]},
        {"id": "R-MOCK-06", "category": "work_progress", "created_at": f"{SNAPSHOT_DATE}T12:45:00Z", "confirmations": 5, "description": "Συνεργείο εργάζεται στα κράσπεδα επί της Πανεπιστημίου.", "work_id": "W-DIAV-003", "coords": [23.7336, 37.9794]},
        {"id": "R-MOCK-07", "category": "damage", "created_at": f"{SNAPSHOT_DATE}T07:55:00Z", "confirmations": 2, "description": "Καμένο φωτιστικό δρόμου στη γωνία με την πλατεία Βαρνάβα.", "work_id": None, "coords": [23.7437, 37.9667]},
        {"id": "R-MOCK-08", "category": "obstacle", "created_at": f"{SNAPSHOT_DATE}T13:15:00Z", "confirmations": 3, "description": "Κλαδιά και κάδος εμποδίζουν διέλευση καροτσιού στη Φιλελλήνων.", "work_id": None, "coords": [23.7341, 37.9735]},
        {"id": "R-MOCK-09", "category": "congestion", "created_at": f"{SNAPSHOT_DATE}T13:40:00Z", "confirmations": 5, "description": "Καθυστέρηση λεωφορείων στη Βασιλίσσης Σοφίας προς Ευαγγελισμό.", "work_id": None, "coords": [23.7448, 37.9762]},
        {"id": "R-MOCK-10", "category": "work_progress", "created_at": f"{SNAPSHOT_DATE}T14:00:00Z", "confirmations": 4, "description": "Η αποκατάσταση οδοστρώματος στην Υμηττού παραδόθηκε καθαρή.", "work_id": "W-SEED-002", "coords": [23.7462, 37.9693]},
    ]

    features = []
    for item in items:
        lon, lat = round(item["coords"][0], 4), round(item["coords"][1], 4)
        props = {
            "id": item["id"],
            "category": item["category"],
            "created_at": item["created_at"],
            "confirmations": item["confirmations"],
            "description": item["description"],
        }
        if item["work_id"] is not None:
            props["work_id"] = item["work_id"]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })

    return {
        "type": "FeatureCollection",
        "snapshot": SNAPSHOT_DATE,
        "note": (
            "Simulated anonymous citizen reports for offline demo (all 5 SPEC categories). "
            "Coordinates are rounded to 4 decimal places (~10 m) per SPEC Privacy (GDPR); "
            "no personal identifiers, tokens, or photos are included."
        ),
        "features": features,
    }


# ---------------------------------------------------------------------------
# 7. points.json
# ---------------------------------------------------------------------------

def build_points() -> dict:
    """Build web/mock/points.json matching SPEC GET /points and Κανόνες πόντων."""
    history = [
        {"ts": "2026-11-18T09:12:00Z", "delta": POINTS_RULES["incident"], "reason": "Αναφορά εμποδίου (οδός Φιλελλήνων)"},
        {"ts": "2026-11-19T14:30:00Z", "delta": POINTS_RULES["confirm"], "reason": "Επιβεβαίωση αναφοράς γείτονα (οδός Σταδίου)"},
        {"ts": "2026-11-20T10:05:00Z", "delta": POINTS_RULES["work_photo"], "reason": "Αναφορά προόδου έργου με φωτογραφία (Ερμού)"},
        {"ts": "2026-11-20T16:40:00Z", "delta": POINTS_RULES["city_verified"], "reason": "Επιβεβαίωση αναφοράς από τον Δήμο Αθηναίων (+20 bonus)"},
        {"ts": "2026-11-21T08:50:00Z", "delta": POINTS_RULES["incident"], "reason": "Αναφορά συμφόρησης (Λεωφ. Βασ. Σοφίας)"},
        {"ts": "2026-11-21T11:15:00Z", "delta": POINTS_RULES["work_photo"], "reason": "Αναφορά προόδου έργου με φωτογραφία (Πανεπιστημίου)"},
    ]
    balance = sum(item["delta"] for item in history)

    # Illustrative municipal rewards per SPEC.md lines 157-158 (open question for the Municipality).
    rewards = [
        {"id": "REW-01", "title": "2 ώρες δωρεάν δημοτική στάθμευση", "cost": 40},
        {"id": "REW-02", "title": "Εισιτήριο δημοτικής εκδήλωσης (Τεχνόπολη / ΟΠΑΝΔΑ)", "cost": 50},
        {"id": "REW-03", "title": "Ημερήσιο πάσο δημοτικού γυμναστηρίου / κολυμβητηρίου", "cost": 60},
        {"id": "REW-04", "title": "Κουπόνι 5€ σε τοπικά καταστήματα γειτονιάς", "cost": 100},
    ]

    return {
        "snapshot": SNAPSHOT_DATE,
        "note": (
            "Simulated anonymous citizen points wallet for offline demo (no user_id). "
            "Point deltas follow SPEC.md «Κανόνες πόντων» (+5/+2/+15/+20); district goal 5000 "
            "matches DECISIONS.md A-9; rewards catalogue is an illustrative proposal pending "
            "Municipality of Athens approval."
        ),
        "balance": balance,
        "district": {
            "name": "1η Δημοτική Κοινότητα (Κέντρο — Σύνταγμα)",
            "progress_pct": 68,
            "goal": DISTRICT_GOAL,
        },
        "history": history,
        "rewards": rewards,
    }


# ---------------------------------------------------------------------------
# 8. stoa.json
# ---------------------------------------------------------------------------

def build_stoa() -> list[dict]:
    """Build web/mock/stoa.json: top-level array of Q&A entries with flyTo citations."""
    # Exact coordinates aligned with health.geojson, works.geojson, transit.geojson.
    p1 = PHARMACIES[0]  # Καραγιώργη Σερβίας 4 (120 m from Syntagma, on_duty=True)
    p2 = PHARMACIES[1]  # Μητροπόλεως 27 (319 m from Syntagma, on_duty=True)
    syn = next(s for s in TRANSIT_STATIONS if s["id"] == "ST-SYN")
    mon = next(s for s in TRANSIT_STATIONS if s["id"] == "ST-MON")

    return [
        {
            "question": "Ποιο φαρμακείο εφημερεύει κοντά μου;",
            "answer_md": (
                "Σύμφωνα με το δοκιμαστικό snapshot εφημεριών (offline λειτουργία), τα πλησιέστερα "
                "εφημερεύοντα φαρμακεία κοντά στο Σύνταγμα είναι:\n"
                "- **Καραγιώργη Σερβίας 4** (Φαρμακείο Καραγιώργη Σερβίας 4, ~120 μ. από Σύνταγμα, 08:00–23:00)\n"
                "- **Μητροπόλεως 27** (Φαρμακείο Πινοτσή, ~319 μ., διανυκτερεύει 08:00–08:00)\n\n"
                "*Σημείωση: οι εφημερίες στο mock αρχείο είναι ενδεικτικές — επιβεβαιώστε στον Φαρμακευτικό Σύλλογο Αττικής.*"
            ),
            "citations": [
                {"label": "Καραγιώργη Σερβίας 4", "lon": p1["coords"][0], "lat": p1["coords"][1], "kind": "pharmacy"},
                {"label": "Μητροπόλεως 27", "lon": p2["coords"][0], "lat": p2["coords"][1], "kind": "pharmacy"},
            ],
        },
        {
            "question": "Ποια έργα γίνονται κοντά στο Σύνταγμα;",
            "answer_md": (
                "Στην 1η Δημοτική Κοινότητα καταγράφονται ενεργά έργα πεζοδρομίων και προσβασιμότητας:\n"
                "- **Οδός Ερμού**: Ενεργειακή αναβάθμιση και βελτίωση προσβασιμότητας πεζοδρομίων 1ης–3ης Δ.Κ. "
                "(ανάδοχος ΩΡΙΩΝ Α.Τ.Ε., πληρωμή 200.023,43 €, `[ΑΔΑ Ψ0ΣΝΩ6Μ-5ΙΖ]`).\n"
                "- **Οδός Πανεπιστημίου**: Άρση επικινδυνότητας σε οδοστρώματα και πεζοδρόμια "
                "(ανάδοχος ΔΟΜΙΚΗ ΑΘΗΝΩΝ Α.Τ.Ε., `[ΑΔΑ 65ΨΟΩ6Μ-675]`)."
            ),
            "citations": [
                {"label": "Οδός Ερμού", "lon": 23.7312, "lat": 37.9759, "kind": "work"},
                {"label": "Οδός Πανεπιστημίου", "lon": 23.7336, "lat": 37.9794, "kind": "work"},
            ],
        },
        {
            "question": "Είναι το έργο στην οδό Υμηττού εντός εγγύησης;",
            "answer_md": (
                "Για το δοκιμαστικό έργο στην **Οδό Υμηττού** (`[ΑΔΑ SEED-ΑΔΑ-002]`, δείγμα SEED), με "
                "ημερομηνία περάτωσης 15/02/2026 και γενικό χρόνο εγγύησης 15 μήνες (άρθρο 171 ν. 4412/2016), "
                "το έργο βρίσκεται **πιθανώς εντός περιόδου εγγύησης** έως 15/05/2027 (175 μέρες ακόμα). "
                "Η τελική αξιολόγηση και τυχόν αξίωση αποκατάστασης γίνεται από μηχανικό του Δήμου."
            ),
            "citations": [
                {"label": "Οδό Υμηττού", "lon": 23.7462, "lat": 37.9693, "kind": "work"},
            ],
        },
        {
            "question": "Ποιος σταθμός μετρό κοντά μου έχει ανελκυστήρα;",
            "answer_md": (
                "Σύμφωνα με τα δεδομένα OpenStreetMap (ODbL 1.0), οι κεντρικοί σταθμοί με σήμανση "
                "προσβασιμότητας / ανελκυστήρα κοντά στο κέντρο είναι ο **Σταθμός Σύνταγμα** (Γραμμές Μ2, Μ3) "
                "και ο **Σταθμός Μοναστηράκι** (Γραμμές Μ1, Μ3)."
            ),
            "citations": [
                {"label": "Σταθμός Σύνταγμα", "lon": round(syn["coords"][0], 6), "lat": round(syn["coords"][1], 6), "kind": "transit"},
                {"label": "Σταθμός Μοναστηράκι", "lon": round(mon["coords"][0], 6), "lat": round(mon["coords"][1], 6), "kind": "transit"},
            ],
        },
        {
            "question": "Πού έχει δροσιά και καλύτερο αέρα στο κέντρο;",
            "answer_md": (
                "Με βάση το snapshot αισθητήρων του Δήμου Αθηναίων (2026-11-21), οι πιο δροσερές περιοχές "
                "με χαμηλότερο PM2.5 είναι γύρω από τους **Αμπελοκήπους** (20,9 °C, AQI 2), ενώ πιο θερμή "
                "και επιβαρυμένη ζώνη καταγράφεται σε **Ψυρρή – Κουμουνδούρου** (25,3 °C, AQI 4, PM2.5 45,8 µg/m³)."
            ),
            "citations": [
                {"label": "Αμπελοκήπους", "lon": 23.76071, "lat": 37.98888, "kind": "env"},
                {"label": "Ψυρρή – Κουμουνδούρου", "lon": 23.72417, "lat": 37.97940, "kind": "env"},
            ],
        },
    ]


# ---------------------------------------------------------------------------
# 9. base.geojson
# ---------------------------------------------------------------------------

def build_base(ckan_dir: Path | None) -> dict:
    """Build web/mock/base.geojson: Municipality of Athens district polygons + main roads."""
    features: list[dict] = []
    boundary_note = ""

    if ckan_dir is not None:
        neigh_p = ckan_dir / "datastore_search___limit___1000___resource_id____0283af02-7783-4688-897b-7153da7ed2fd__.json"
        dist_p = ckan_dir / "datastore_search___limit___1000___resource_id____400da0d1-a213-4236-bfef-bb14e6cefb39__.json"
        if neigh_p.is_file() and dist_p.is_file():
            neigh = json.loads(neigh_p.read_text(encoding="utf-8"))["result"]["records"]
            dists = json.loads(dist_p.read_text(encoding="utf-8"))["result"]["records"]
            dnames = {str(d["id"]): d["name"] for d in dists if d.get("id") and d.get("name")}
            by_dist: dict[str, list[list[list[list[float]]]]] = {}

            for r in neigh:
                g = _parse_wkt(r.get("polygon_geo") or "")
                if not g or g["type"] != "Polygon":
                    continue
                ring = [_clamp_pt(pt[0], pt[1]) for pt in g["coordinates"][0]]
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                simp = _simplify_ring(ring, SIMPLIFY_TOL_DEG)
                did = str(r.get("municipal_district_id") or "0")
                by_dist.setdefault(did, []).append([simp])

            for did, polys in sorted(by_dist.items()):
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "MultiPolygon", "coordinates": polys},
                    "properties": {
                        "kind": "district",
                        "district_id": did,
                        "name": dnames.get(did, f"Δημοτική Κοινότητα {did}"),
                    },
                })
            boundary_note = (
                "7 Municipal District MultiPolygons aggregated from real Municipality of Athens CKAN "
                "neighbourhood polygons (neighbourhoods-athens & municipal-districts-athens, CC BY 4.0), "
                "simplified (~45 m tolerance) and clamped to the Athens bbox [23.68–23.80, 37.95–38.03] "
                "(4 northern/southern edge vertices trimmed by <=0.0027°)."
            )

    if not features:
        # Simplified fallback outer polygon of Municipality of Athens if CKAN cache is absent.
        # Source: derived from Athens municipal extent. Certainty: approximate.
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [23.690, 37.960], [23.720, 37.955], [23.755, 37.960],
                    [23.785, 37.980], [23.775, 38.015], [23.745, 38.028],
                    [23.715, 38.020], [23.695, 37.995], [23.690, 37.960],
                ]],
            },
            "properties": {"kind": "boundary", "name": "Δήμος Αθηναίων"},
        })
        boundary_note = "Simplified fallback Municipality of Athens boundary polygon."

    # Major central Athens arterial roads for offline map orientation (A1 offline style).
    # Coordinates traced from central Athens street network (OSM alignment checked 2026-11-21).
    # Source: OpenStreetMap street corridors (simplified). Certainty: high.
    main_roads = [
        ("Λεωφ. Βασιλίσσης Σοφίας", "primary", [[23.7355, 37.9756], [23.7420, 37.9760], [23.7478, 37.9765], [23.7535, 37.9792], [23.7598, 37.9838], [23.7650, 37.9888]]),
        ("Λεωφ. Βασιλίσσης Αμαλίας", "primary", [[23.7354, 37.9756], [23.7347, 37.9730], [23.7335, 37.9702], [23.7322, 37.9685]]),
        ("Οδός Πανεπιστημίου", "primary", [[23.7352, 37.9760], [23.7330, 37.9804], [23.7305, 37.9830], [23.7282, 37.9841]]),
        ("Οδός Σταδίου", "primary", [[23.7345, 37.9758], [23.7320, 37.9790], [23.7295, 37.9822], [23.7280, 37.9841]]),
        ("Οδός Ερμού", "pedestrian", [[23.7346, 37.9755], [23.7302, 37.9760], [23.7257, 37.9761], [23.7210, 37.9768], [23.7152, 37.9779]]),
        ("Οδός Μητροπόλεως", "secondary", [[23.7346, 37.9751], [23.7312, 37.9753], [23.7278, 37.9757], [23.7258, 37.9761]]),
        ("Οδός Αθηνάς", "secondary", [[23.7257, 37.9762], [23.7269, 37.9798], [23.7280, 37.9840]]),
        ("Οδός Πατησίων (28ης Οκτωβρίου)", "primary", [[23.7281, 37.9842], [23.7303, 37.9890], [23.7319, 37.9945], [23.7336, 38.0020], [23.7362, 38.0125], [23.7386, 38.0220]]),
        ("Λεωφ. Αλεξάνδρας", "primary", [[23.7320, 37.9912], [23.7398, 37.9906], [23.7480, 37.9895], [23.7577, 37.9873], [23.7650, 37.9888]]),
        ("Λεωφ. Ανδρέα Συγγρού", "trunk", [[23.7322, 37.9685], [23.7296, 37.9665], [23.7268, 37.9646], [23.7224, 37.9602], [23.7176, 37.9548]]),
        ("Οδός Πειραιώς", "primary", [[23.7276, 37.9840], [23.7222, 37.9822], [23.7160, 37.9798], [23.7109, 37.9785], [23.7042, 37.9742], [23.6960, 37.9688]]),
    ]
    for name, highway, coords in main_roads:
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [_clamp_pt(x, y) for x, y in coords]},
            "properties": {"kind": "road", "name": name, "highway": highway},
        })

    return {
        "type": "FeatureCollection",
        "snapshot": SNAPSHOT_DATE,
        "note": (
            f"{boundary_note} Main arterial roads are simplified central Athens street corridors "
            "aligned to OpenStreetMap for A1's offline map style."
        ),
        "features": features,
    }


# ---------------------------------------------------------------------------
# 10. README.md
# ---------------------------------------------------------------------------

def build_readme(env_count: int) -> str:
    """Document all mock files, snapshot date (incl. stoa.json), real vs invented fields."""
    return f"""# Offline Mock Datasets (`web/mock/`)

**Snapshot date:** `{SNAPSHOT_DATE}`
**Builder script:** [`scripts/build_mocks.py`](../../scripts/build_mocks.py)
**Contract canon:** [`docs/SPEC.md`](../../docs/SPEC.md) («Backend contracts», «Offline fallback»)

All nine JSON/GeoJSON files match the exact response shapes expected by `web/js/api.js` (task B1) and Dev A's map layers so the full 3-minute demo runs offline without network access. Every GeoJSON file uses WGS84 coordinates inside the Municipality of Athens bounding box (`lon 23.68–23.80`, `lat 37.95–38.03`).

## Provenance summary

| File | Real data | Invented / demo-only | Licence |
|---|---|---|---|
| `env.json` | {env_count} Municipality of Athens CKAN air-quality sensors (`opendata.cityofathens.gr`, `{SNAPSHOT_DATE}T14:00:00Z`) placed at neighbourhood centroids (A-21), covering central Athens (Σύνταγμα, Μοναστηράκι, Ψυρρή, Κολωνάκι) and all 7 districts; faulty PM2.5 spike excluded | None (live snapshot) | CC BY 4.0 |
| `access.geojson` | OpenStreetMap accessibility features (`kerb=lowered`, `ramp=yes`, `tactile_paving=yes`, named `wheelchair=yes/limited` POIs) around Σύνταγμα–Μοναστηράκι–Πλάκα with exact OSM IDs | None | ODbL 1.0 |
| `works.geojson` | 10 real Municipality of Athens (`org 6013`) public-works decisions from `diavgeia.gov.gr` (real ADA, `source_url`, contractor, ADAM, payment amount, contract date; unknown fields kept `null`) | Representative street segments for district-wide framework contracts; 2 clearly marked `SEED-` works (`seed: true`) with contract/guarantee bars for UI testing | Diavgeia Open Data / SEED |
| `transit.geojson` | 18 real OSM station coordinates & IDs (`Σύνταγμα`, `Μοναστηράκι`, etc.); STASY/OASA official line colours | Simplified station-to-station line segments; simulated OASA bus positions, bearings & ETAs | ODbL 1.0 / Mock |
| `health.geojson` | 6 real central Athens public hospitals & 6 real OSM pharmacy locations (phones from OSM tags or `άγνωστο`) | `on_duty` flags, duty hours and demo specialties (ΦΣΑ / Ministry of Health lists not fetched live) | ODbL 1.0 / Mock |
| `reports.geojson` | None (all 10 reports are simulated citizen fixtures across all 5 SPEC categories) | Coordinates rounded to 4 decimals (~10 m, SPEC Privacy); no personal IDs, tokens or photos | Mock |
| `points.json` | Point rules (`+5/+2/+15/+20`) from SPEC.md; district goal `5000` (A-9) | Simulated anonymous wallet history & illustrative municipal rewards (no `user_id`) | Mock |
| `stoa.json` | Snapshot `{SNAPSHOT_DATE}` — top-level JSON array without a wrapper object (so `api.js` matches `POST /stoa_ask` entries directly). Citations align with `health.geojson` (0 m offset for the Syntagma demo pharmacy), `works.geojson`, `transit.geojson`, and `env.json`. | Pre-canned offline Q&A answers for the demo questions, including `«Ποιο φαρμακείο εφημερεύει κοντά μου;»`, using cautious Stoa wording («πιθανώς εντός περιόδου εγγύησης»). | Mock + cited sources |
| `base.geojson` | 7 Municipal District MultiPolygons from CKAN `neighbourhoods-athens` & `municipal-districts-athens` (simplified ~45 m, edge-clamped to bbox) | Simplified arterial road corridors for A1 offline style | CC BY 4.0 / ODbL 1.0 |
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Build offline mock files under web/mock/.")
    ap.add_argument("--out-dir", default=str(APP_ROOT / "web" / "mock"), help="Output directory")
    ap.add_argument("--ckan-dir", default=None, help="Path to local CKAN snapshot directory")
    ap.add_argument("--no-osm-phones", action="store_true", help="Skip OSM hospital phone tag lookups")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ckan_dir = _find_ckan_dir(args.ckan_dir)
    print(f"CKAN dir: {ckan_dir}")

    env_data = build_env(ckan_dir)
    _write_json(out_dir / "env.json", env_data)
    _write_json(out_dir / "access.geojson", build_access())
    _write_json(out_dir / "works.geojson", build_works())
    _write_json(out_dir / "transit.geojson", build_transit())
    _write_json(out_dir / "health.geojson", build_health(fetch_phones=not args.no_osm_phones))
    _write_json(out_dir / "reports.geojson", build_reports())
    _write_json(out_dir / "points.json", build_points())
    _write_json(out_dir / "stoa.json", build_stoa())
    _write_json(out_dir / "base.geojson", build_base(ckan_dir))
    (out_dir / "README.md").write_text(build_readme(len(env_data["features"])), encoding="utf-8")

    print("Wrote 9 JSON/GeoJSON mocks + README.md to", out_dir)


if __name__ == "__main__":
    main()
