"""B4 adapter: on-duty pharmacies (ΦΣΑ) and hospitals (Υπουργείο Υγείας).

External calls (verified live 2026-11-21):
  - Pharmacies: POST https://fsa-efimeries.gr/Home/FilteredHomeResults (Date=YYYY-MM-DD, IsOpen=false)
  - Hospitals:  GET https://www.moh.gov.gr/articles/citizen/efhmeries-nosokomeiwn/68-efhmeries-nosokomeiwn-attikhs
                -> follow ?fdl=<id> for that date's .doc announcement and extract table text (pure-Python OLE2)
  - Geocode:    GET https://nominatim.openstreetmap.org/search (fallback when a pharmacy has no coordinates)

Caches:
  - In-memory TTL cache (config.ONDUTY_TTL_S, default 24 h)
  - Disk cache under CACHE_DIR: pharmacies-<date>.json, hospitals-<date>.json, geocode.json, last.json
  - Curated central-Athens hospital locations live in HOSPITALS_PATH (data/onduty/hospitals.json)

Trust rule: if an upstream source cannot be fetched or parsed, its rows are returned from cache/curated
data with on_duty=None (unknown) — never a guess — and the failed source is named in failed_sources.
"""
from __future__ import annotations

import html
import json
import os
import re
import struct
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from . import config

# Curated central-Athens hospitals file (stays fixed even when tests redirect CACHE_DIR).
# Source: TASKS_B.md B4 card. Certainty: sure.
HOSPITALS_PATH: Path = config.DATA_DIR / "onduty" / "hospitals.json"

# Runtime cache directory (pharmacies-<date>.json, hospitals-<date>.json, geocode.json, last.json).
# Kept separate from HOSPITALS_PATH so tests can monkeypatch CACHE_DIR to a tmp_path.
# Source: TASKS_B.md B4 card & tests/test_B4_onduty.py. Certainty: sure.
CACHE_DIR: Path = config.DATA_DIR / "onduty"

# Source identifiers reported in failed_sources when an upstream fetch/parse fails.
# Source: TASKS_B.md B4 card & tests/test_B4_onduty.py. Certainty: sure.
SOURCE_PHARMACIES = "fsa_pharmacies"
SOURCE_HOSPITALS = "moh_hospitals"

# Human-readable source labels attached to features and the response sources[] list.
# Source: SPEC.md «Εξωτερικές πηγές». Certainty: sure.
LABEL_PHARMACIES = "Φαρμακευτικός Σύλλογος Αττικής (fsa-efimeries.gr)"
LABEL_HOSPITALS = "Υπουργείο Υγείας (moh.gov.gr)"

# Hospital duty hours are left unknown (None). The MOH table has two columns ("08:00 – 08:00 επομένης" and
# "08:00 – 23:00") and the plain-text extraction does not keep which column a hospital sits in, so any fixed
# value could be wrong for some hospitals. Source: live efimeria doc for 2026-11-21 (fdl=32105). Certainty: sure
# that both windows exist; open question for the owner whether to parse columns.
DEFAULT_HOSPITAL_HOURS: str | None = None

# Greek genitive month names as used in MOH Attica announcement link titles (e.g. "21 ΝΟΕΜΒΡΙΟΥ 2026").
# Source: Verified on live moh.gov.gr index page 2026-11-21. Certainty: sure.
GREEK_MONTHS_GEN: dict[int, str] = {
    1: "ΙΑΝΟΥΑΡΙΟΥ",
    2: "ΦΕΒΡΟΥΑΡΙΟΥ",
    3: "ΜΑΡΤΙΟΥ",
    4: "ΑΠΡΙΛΙΟΥ",
    5: "ΜΑΙΟΥ",
    6: "ΙΟΥΝΙΟΥ",
    7: "ΙΟΥΛΙΟΥ",
    8: "ΑΥΓΟΥΣΤΟΥ",
    9: "ΣΕΠΤΕΜΒΡΙΟΥ",
    10: "ΟΚΤΩΒΡΙΟΥ",
    11: "ΝΟΕΜΒΡΙΟΥ",
    12: "ΔΕΚΕΜΒΡΙΟΥ",
}

# OLE2 Compound File Binary Format magic header (MS-CFB specification, section 2.2).
# Source: Microsoft [MS-CFB] spec, verified against live moh.gov.gr .doc attachments. Certainty: sure.
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# Regex for extracting individual hospital mentions from MOH duty table cells.
# Covers prefixed guillemet names (Γ.Ν.Α. «...», Π.Γ.Ν. «...», ΑΟΝΑ «...», etc.),
# bare guillemet names («ΔΡΟΜΟΚΑΪΤΕΙΟ»), and unquoted official names (ΟΦΘΑΛΜΙΑΤΡΕΙΟ ΑΘΗΝΩΝ, Π.Γ.Ν. ΑΤΤΙΚΟΝ).
# Source: Verified against live moh.gov.gr efimeria_20261121.doc & efimeria_20261122.doc. Certainty: sure.
_HOSPITAL_MENTION_RE = re.compile(
    r"(?:"
    r"(?:(?:Γ\.?\s*Ν\.?\s*(?:Α\.?\s*(?:Μ\.?)?|Π\.?\s*Α\.?|Π\.?|Μ\.?|Ν\.?\s*ΙΩΝΙΑΣ|Ν\.?\s*Θ\.?\s*Α\.?|Θ\.?)?"
    r"|Π\.?\s*Γ\.?\s*Ν\.?"
    r"|Ν\.?\s*Δ\.?\s*Ν\.?\s*Α\.?"
    r"|Γ\.?\s*Α\.?\s*Ο\.?\s*Ν\.?\s*Α\.?"
    r"|Α\.?\s*Ο\.?\s*Ν\.?\s*Α\.?"
    r"|Ε\.?\s*Α\.?\s*Ν\.?\s*Π\.?"
    r"|Γ\.?\s*Ο\.?\s*Ν\.?\s*Κ\.?"
    r"|Ν\.?\s*Α\.?)\s*)?"
    r"«[^»]+»(?:\s+ΒΟΥΛΑΣ)?"
    r"|"
    r"Ν\.?\s*Α\.?\s+ΟΦΘΑΛΜΙΑΤΡΕΙΟ(?:\s+ΑΘΗΝΩΝ)?"
    r"|"
    r"Π\.?\s*Γ\.?\s*Ν\.?\s+ΑΤΤΙΚΟΝ"
    r")"
)

# In-memory caches (cleared by clear_cache() between tests).
_mem_cache: dict[tuple[str, str], tuple[float, Any]] = {}
_geocode_mem: dict[str, tuple[float, float]] = {}


def clear_cache() -> None:
    """Clear all in-memory caches (used by tests for isolation)."""
    _mem_cache.clear()
    _geocode_mem.clear()


def _today_str() -> str:
    t = os.getenv("STOA_TODAY")
    return t if t else date.today().isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm_greek(text: str) -> str:
    """Uppercase, strip Greek accents/diacritics, and collapse whitespace."""
    nfd = unicodedata.normalize("NFD", text.upper())
    no_marks = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", no_marks).strip()


def _in_bbox(lon: float, lat: float) -> bool:
    min_lon, min_lat, max_lon, max_lat = config.ONDUTY_BBOX
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def _http_headers() -> dict[str, str]:
    return {"User-Agent": config.ONDUTY_USER_AGENT}


# ------------------------------------------------------------------ OLE2 .doc extraction
def _extract_doc_text(buf: bytes) -> str:
    """Extract table-structured text from a Microsoft Word 97-2003 OLE2 .doc binary (zero dependencies).

    Implements the minimal [MS-CFB] FAT/directory reader and [MS-DOC] FIB/CLX piece-table reader
    used by Ministry of Health Attica duty announcements (efimeria_YYYYMMDD.doc).
    Returns rows separated by newlines and cells separated by tabs.
    """
    if len(buf) < 512 or buf[:8] != _OLE2_MAGIC:
        raise ValueError("Unsupported hospital announcement binary (expected OLE2 .doc)")

    sector_size = 1 << struct.unpack_from("<H", buf, 30)[0]
    first_dir_sec = struct.unpack_from("<I", buf, 48)[0]
    mini_cutoff = struct.unpack_from("<I", buf, 56)[0]
    difat = list(struct.unpack_from("<109I", buf, 76))

    fat: list[int] = []
    for sec in difat:
        if sec >= 0xFFFFFFFA:
            break
        off = 512 + sec * sector_size
        fat.extend(struct.unpack_from(f"<{sector_size // 4}I", buf, off))

    def read_chain(start_sec: int, size: int | None = None) -> bytes:
        out = bytearray()
        sec = start_sec
        seen: set[int] = set()
        while sec < 0xFFFFFFFA and sec not in seen:
            seen.add(sec)
            off = 512 + sec * sector_size
            out.extend(buf[off : off + sector_size])
            sec = fat[sec] if sec < len(fat) else 0xFFFFFFFE
        return bytes(out[:size]) if size is not None else bytes(out)

    dir_bytes = read_chain(first_dir_sec)
    streams: dict[str, bytes] = {}
    for i in range(0, len(dir_bytes), 128):
        entry = dir_bytes[i : i + 128]
        if len(entry) < 128:
            break
        name_len = struct.unpack_from("<H", entry, 64)[0]
        obj_type = entry[66]
        if obj_type == 2 and name_len >= 2:
            name = entry[: name_len - 2].decode("utf-16-le", errors="ignore")
            start_sec = struct.unpack_from("<I", entry, 116)[0]
            size = struct.unpack_from("<I", entry, 120)[0]
            if size >= mini_cutoff:
                streams[name] = read_chain(start_sec, size)

    wd = streams.get("WordDocument")
    if not wd:
        raise ValueError("OLE2 file missing WordDocument stream")

    flags = struct.unpack_from("<H", wd, 10)[0]
    tbl_name = "1Table" if (flags & 0x0200) else "0Table"
    tbl = streams.get(tbl_name)
    if not tbl:
        raise ValueError(f"OLE2 file missing {tbl_name} stream")

    fc_clx = struct.unpack_from("<I", wd, 0x01A2)[0]
    lcb_clx = struct.unpack_from("<I", wd, 0x01A6)[0]
    clx = tbl[fc_clx : fc_clx + lcb_clx]

    pos = 0
    while pos < len(clx) and clx[pos] == 1:
        pos += 3 + struct.unpack_from("<H", clx, pos + 1)[0]
    if pos >= len(clx) or clx[pos] != 2:
        raise ValueError("Word piece table (PlcPcd) not found")

    lcb = struct.unpack_from("<I", clx, pos + 1)[0]
    plc = clx[pos + 5 : pos + 5 + lcb]
    n = (lcb - 4) // 12
    cps = struct.unpack_from(f"<{n + 1}I", plc, 0)

    parts: list[str] = []
    for i in range(n):
        pcd_off = (n + 1) * 4 + i * 8
        fc = struct.unpack_from("<I", plc, pcd_off + 2)[0]
        char_count = cps[i + 1] - cps[i]
        if fc & 0x40000000:
            byte_off = (fc & 0x3FFFFFFF) // 2
            parts.append(wd[byte_off : byte_off + char_count].decode("cp1253", errors="replace"))
        else:
            parts.append(wd[fc : fc + char_count * 2].decode("utf-16-le", errors="replace"))

    raw = "".join(parts)
    lines: list[str] = []
    for row in raw.split("\x07\x07"):
        cells = [re.sub(r"[\r\n\t\uf020\x00-\x06\x08-\x1f]+", " ", c).strip() for c in row.split("\x07")]
        if any(cells):
            lines.append("\t".join(cells))
    return "\n".join(lines)


def _find_moh_doc_link(index_html: str, date_str: str) -> str | None:
    """Find the ?fdl=<id> attachment link for date_str on the MOH Attica index page.

    Prefers the .doc version over .pdf and prefers revised ("ΟΡΘΗ ΕΠΑΝΑΚΟΙΝΟΠΟΙΗΣΗ") notices.
    """
    d = date.fromisoformat(date_str)
    target = f"{d.day} {GREEK_MONTHS_GEN[d.month]} {d.year}"
    candidates: list[tuple[int, str]] = []
    for href, label_html in re.findall(r'<a[^>]+href=["\'](\?fdl=\d+)["\'][^>]*>(.*?)</a>', index_html, re.S | re.I):
        text = _norm_greek(html.unescape(re.sub(r"<[^>]+>", " ", label_html)))
        if target not in text:
            continue
        is_pdf = ".PDF" in text
        if is_pdf:
            continue
        score = 2 if "ΟΡΘΗ" in text else 1
        candidates.append((score, href))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


# ------------------------------------------------------------------ HTTP fetchers (1 function per upstream)
def fetch_pharmacies_page(date_str: str) -> str:
    """Fetch the ΦΣΑ on-duty pharmacy HTML cards for date_str (YYYY-MM-DD)."""
    with httpx.Client(timeout=config.ONDUTY_TIMEOUT_S, follow_redirects=True, headers=_http_headers()) as client:
        r = client.post(
            config.ONDUTY_PHARMACIES_URL,
            data={"Date": date_str, "IsOpen": "false"},
        )
        r.raise_for_status()
        return r.text


def fetch_hospitals_announcement(date_str: str) -> str:
    """Fetch the Ministry of Health Attica hospital duty announcement for date_str and return plain text."""
    with httpx.Client(timeout=config.ONDUTY_TIMEOUT_S, follow_redirects=True, headers=_http_headers()) as client:
        idx = client.get(config.ONDUTY_HOSPITALS_URL)
        idx.raise_for_status()
        rel = _find_moh_doc_link(idx.text, date_str)
        if not rel:
            raise ValueError(f"No MOH Attica hospital duty .doc link found for {date_str}")
        doc_url = urljoin(str(idx.url), rel)
        doc_res = client.get(doc_url)
        doc_res.raise_for_status()
        if doc_res.content[:8] == _OLE2_MAGIC:
            return _extract_doc_text(doc_res.content)
        return doc_res.text


def fetch_geocode(address: str) -> tuple[float, float] | None:
    """Geocode one street address via OpenStreetMap Nominatim. Returns (lat, lon) or None."""
    query = address if "greece" in address.lower() or "ελλαδ" in _norm_greek(address).lower() else f"{address}, Greece"
    with httpx.Client(timeout=config.ONDUTY_TIMEOUT_S, follow_redirects=True, headers=_http_headers()) as client:
        r = client.get(
            config.ONDUTY_GEOCODE_URL,
            params={"q": query, "format": "json", "limit": 1},
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return None
        return (float(rows[0]["lat"]), float(rows[0]["lon"]))


# ------------------------------------------------------------------ Geocode cache
def _geocode_cache_path() -> Path:
    return CACHE_DIR / "geocode.json"


def _load_geocode_disk() -> dict[str, list[float]]:
    p = _geocode_cache_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_geocode_disk(data: dict[str, list[float]]) -> None:
    p = _geocode_cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def geocode(address: str) -> tuple[float, float] | None:
    """Return cached (lat, lon) for address, calling fetch_geocode() at most once per unique address."""
    key = re.sub(r"\s+", " ", address).strip()
    if not key:
        return None
    if key in _geocode_mem:
        return _geocode_mem[key]

    disk = _load_geocode_disk()
    if key in disk and isinstance(disk[key], list) and len(disk[key]) == 2:
        coords = (float(disk[key][0]), float(disk[key][1]))
        _geocode_mem[key] = coords
        return coords

    try:
        coords = fetch_geocode(key)
    except Exception:
        return None

    if coords is not None:
        _geocode_mem[key] = coords
        disk[key] = [coords[0], coords[1]]
        _save_geocode_disk(disk)
    return coords


# ------------------------------------------------------------------ Parsers (pure functions)
def _clean_html_text(snippet: str) -> str:
    text = re.sub(r"<[^>]+>", " ", snippet)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_pharmacies(raw: str) -> list[dict[str, Any]]:
    """Parse FSA HTML card output into rows with name, address, phone, hours, and optional lat/lon."""
    blocks = re.split(r'<div\s+class="card-frame\b', raw)[1:]
    items: list[dict[str, Any]] = []
    for block in blocks:
        m_street = re.search(r'<div\s+class="card-title[^>]*>.*?<h6[^>]*>(.*?)</h6>', block, re.S | re.I)
        m_area = re.search(r'<div\s+class="card-subtitle[^>]*>(.*?)</div>', block, re.S | re.I)
        spans = re.findall(r"<span[^>]*>(.*?)</span>", block, re.S | re.I)
        m_phone = re.search(r'href="tel:([^"]+)"', block, re.I)
        m_coord = re.search(r"query=([0-9.\-]+)%2C([0-9.\-]+)", block, re.I)

        street = _clean_html_text(m_street.group(1)) if m_street else ""
        area = _clean_html_text(m_area.group(1)) if m_area else ""
        if street and area and _norm_greek(area) not in _norm_greek(street):
            address = f"{street}, {area}"
        else:
            address = street or area

        name = _clean_html_text(spans[0]) if len(spans) > 0 else ""
        hours = _clean_html_text(spans[1]) if len(spans) > 1 else ""
        phone = _clean_html_text(m_phone.group(1)) if m_phone else None
        lat = float(m_coord.group(1)) if m_coord else None
        lon = float(m_coord.group(2)) if m_coord else None

        if name and address and hours:
            items.append(
                {
                    "name": name,
                    "address": address,
                    "phone": phone or None,
                    "hours": hours,
                    "lat": lat,
                    "lon": lon,
                }
            )
    return items


def _looks_like_specialty(cell: str) -> bool:
    """Return True if a first table cell names a medical specialty rather than a hospital or note."""
    if not cell:
        return False
    norm = _norm_greek(cell)
    if norm in ("ΚΛΙΝΙΚΕΣ", "ΠΕΙΡΑΙΑΣ", "ΠΑΡΑΤΗΡΗΣΕΙΣ"):
        return False
    if "«" in cell or "»" in cell or "ΕΦΗΜΕΡ" in norm or "ΕΩΣ " in norm:
        return False
    if norm.startswith(("ΓΙΑ ", "ΤΑ ", "Κ.Υ.", "08:", "ΣΑΒΒΑΤΟ", "ΚΥΡΙΑΚΗ", "ΔΕΥΤΕΡΑ", "ΤΡΙΤΗ", "ΤΕΤΑΡΤΗ", "ΠΕΜΠΤΗ", "ΠΑΡΑΣΚΕΥΗ")):
        return False
    if _HOSPITAL_MENTION_RE.search(cell):
        return False
    # Specialties are short Greek clinic labels (e.g., "Παθολογική", "Ω.Ρ.Λ.", "Κλινική Χεριού-...").
    return len(cell) <= 60


def parse_hospital_announcement(raw: str) -> list[dict[str, Any]]:
    """Parse extracted MOH Attica hospital duty text into [{'name': ..., 'specialties': [...]}]."""
    by_hospital: dict[str, list[str]] = {}
    display_name: dict[str, str] = {}
    in_table = False
    current_specialty: str | None = None

    for line in raw.splitlines():
        if not line.strip():
            continue
        cells = [c.strip() for c in line.split("\t")]
        non_empty = [c for c in cells if c]
        if not non_empty:
            continue

        joined_norm = _norm_greek(" ".join(non_empty))
        if "ΚΛΙΝΙΚΕΣ" in joined_norm and "08:00" in joined_norm:
            in_table = True
            current_specialty = None
            continue
        if not in_table:
            continue

        first = non_empty[0]
        rest = non_empty[1:]
        if _looks_like_specialty(first):
            current_specialty = re.sub(r"\s+", " ", first).strip()
            hospital_cells = rest
        else:
            hospital_cells = non_empty

        if not current_specialty:
            continue

        for cell in hospital_cells:
            for match in _HOSPITAL_MENTION_RE.finditer(cell):
                hosp = re.sub(r"\s+", " ", match.group(0)).strip()
                hosp = re.sub(r"«\s+", "«", hosp)
                hosp = re.sub(r"\s+»", "»", hosp)
                key = _norm_greek(hosp)
                if key not in display_name:
                    display_name[key] = hosp
                    by_hospital[key] = []
                if current_specialty not in by_hospital[key]:
                    by_hospital[key].append(current_specialty)

    return [{"name": display_name[k], "specialties": specs} for k, specs in by_hospital.items() if specs]


# ------------------------------------------------------------------ Curated hospitals & matching
def load_curated_hospitals() -> list[dict[str, Any]]:
    """Load curated central-Athens hospital coordinates, addresses, and phones."""
    data = json.loads(HOSPITALS_PATH.read_text(encoding="utf-8"))
    return list(data.get("hospitals") or [])


def _match_hospital_specialties(curated: dict[str, Any], parsed_entries: list[dict[str, Any]]) -> list[str]:
    """Return merged specialties for one curated hospital from parsed MOH announcement rows."""
    aliases = [_norm_greek(a) for a in (curated.get("aliases") or []) if a]
    aliases.append(_norm_greek(curated["name"]))
    matched: list[str] = []
    for entry in parsed_entries:
        entry_norm = _norm_greek(entry.get("name", ""))
        if any(alias and alias in entry_norm for alias in aliases):
            for spec in entry.get("specialties") or []:
                if spec not in matched:
                    matched.append(spec)
    return matched


# ------------------------------------------------------------------ Disk cache helpers
def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_latest_cached_pharmacies() -> list[dict[str, Any]]:
    """Return pharmacies from the latest disk snapshot (last.json or newest pharmacies-*.json)."""
    last = _read_json_if_exists(CACHE_DIR / "last.json")
    if last and isinstance(last.get("pharmacies"), list) and last["pharmacies"]:
        return list(last["pharmacies"])
    if CACHE_DIR.exists():
        files = sorted(CACHE_DIR.glob("pharmacies-*.json"), reverse=True)
        for p in files:
            cached = _read_json_if_exists(p)
            if cached and isinstance(cached.get("items"), list) and cached["items"]:
                return list(cached["items"])
    return []


# ------------------------------------------------------------------ Public service entry point
def _get_pharmacies_for_date(date_str: str) -> tuple[list[dict[str, Any]], str, bool]:
    """Fetch or load pharmacies for date_str. Returns (rows, source_state, failed)."""
    now = time.time()
    mem = _mem_cache.get(("pharmacies", date_str))
    if mem and (now - mem[0]) < config.ONDUTY_TTL_S:
        return list(mem[1]), "cache", False

    disk_path = CACHE_DIR / f"pharmacies-{date_str}.json"
    disk = _read_json_if_exists(disk_path)
    if disk and isinstance(disk.get("items"), list) and (now - float(disk.get("fetched_at", 0))) < config.ONDUTY_TTL_S:
        _mem_cache[("pharmacies", date_str)] = (float(disk["fetched_at"]), disk["items"])
        return list(disk["items"]), "cache", False

    try:
        raw = fetch_pharmacies_page(date_str)
        parsed = parse_pharmacies(raw)
        if not parsed:
            raise ValueError("No pharmacies parsed from upstream response")
        resolved: list[dict[str, Any]] = []
        for row in parsed:
            lat, lon = row.get("lat"), row.get("lon")
            if lat is None or lon is None:
                coords = geocode(row["address"])
                if coords is None:
                    continue
                lat, lon = coords
            if not _in_bbox(lon, lat):
                continue
            resolved.append(
                {
                    "name": row["name"],
                    "address": row["address"],
                    "phone": row.get("phone"),
                    "hours": row.get("hours"),
                    "lat": round(float(lat), 6),
                    "lon": round(float(lon), 6),
                    "on_duty": True,
                }
            )
        if not resolved:
            raise ValueError("No pharmacies located inside Athens bbox")
        _write_json(disk_path, {"date": date_str, "fetched_at": now, "items": resolved})
        _mem_cache[("pharmacies", date_str)] = (now, resolved)
        return resolved, "live", False
    except Exception:
        fallback = _load_latest_cached_pharmacies()
        if fallback:
            # Never guess today's duty status from a stale snapshot: force on_duty=None.
            unknown_rows = [{**row, "on_duty": None} for row in fallback]
            return unknown_rows, "snapshot", True
        return [], "unavailable", True


def _get_hospitals_for_date(date_str: str) -> tuple[list[dict[str, Any]], str, bool]:
    """Fetch or load MOH hospital duty entries for date_str. Returns (parsed_entries, source_state, failed)."""
    now = time.time()
    mem = _mem_cache.get(("hospitals", date_str))
    if mem and (now - mem[0]) < config.ONDUTY_TTL_S:
        return list(mem[1]), "cache", False

    disk_path = CACHE_DIR / f"hospitals-{date_str}.json"
    disk = _read_json_if_exists(disk_path)
    if disk and isinstance(disk.get("items"), list) and (now - float(disk.get("fetched_at", 0))) < config.ONDUTY_TTL_S:
        _mem_cache[("hospitals", date_str)] = (float(disk["fetched_at"]), disk["items"])
        return list(disk["items"]), "cache", False

    try:
        raw = fetch_hospitals_announcement(date_str)
        parsed = parse_hospital_announcement(raw)
        if not parsed:
            raise ValueError("No hospitals parsed from MOH announcement")
        _write_json(disk_path, {"date": date_str, "fetched_at": now, "items": parsed})
        _mem_cache[("hospitals", date_str)] = (now, parsed)
        return parsed, "live", False
    except Exception:
        return [], "snapshot", True


def _pharmacy_feature(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
        "properties": {
            "kind": "φαρμακείο",
            "name": row["name"],
            "address": row["address"],
            "phone": row.get("phone"),
            "hours": row.get("hours"),
            "specialties": [],
            "on_duty": row.get("on_duty"),
            "source": LABEL_PHARMACIES,
        },
    }


def _hospital_feature(curated: dict[str, Any], specialties: list[str], failed: bool) -> dict[str, Any]:
    if failed:
        on_duty: bool | None = None
        hours: str | None = None
        specs: list[str] = []
    elif specialties:
        on_duty = True
        hours = DEFAULT_HOSPITAL_HOURS
        specs = specialties
    else:
        on_duty = False
        hours = None
        specs = []

    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [curated["lon"], curated["lat"]]},
        "properties": {
            "kind": "νοσοκομείο",
            "name": curated["name"],
            "address": curated["address"],
            "phone": curated.get("phone"),
            "hours": hours,
            "specialties": specs,
            "on_duty": on_duty,
            "source": f"{LABEL_HOSPITALS}; {curated.get('source', '')}".strip("; "),
        },
    }


def get_onduty(date_str: str | None = None) -> dict[str, Any]:
    """Build the SPEC GET /api/map/health GeoJSON FeatureCollection for date_str (default today)."""
    target_date = date_str or _today_str()
    # Validate ISO date format (raises ValueError on invalid input).
    date.fromisoformat(target_date)

    pharm_rows, pharm_src, pharm_failed = _get_pharmacies_for_date(target_date)
    hosp_parsed, hosp_src, hosp_failed = _get_hospitals_for_date(target_date)
    curated_hospitals = load_curated_hospitals()

    failed_sources: list[str] = []
    if pharm_failed:
        failed_sources.append(SOURCE_PHARMACIES)
    if hosp_failed:
        failed_sources.append(SOURCE_HOSPITALS)

    features: list[dict[str, Any]] = [_pharmacy_feature(r) for r in pharm_rows]
    for h in curated_hospitals:
        specs = [] if hosp_failed else _match_hospital_specialties(h, hosp_parsed)
        features.append(_hospital_feature(h, specs, failed=hosp_failed))

    # Persist last good snapshot whenever at least one upstream succeeded live.
    if pharm_src == "live" or hosp_src == "live":
        last = _read_json_if_exists(CACHE_DIR / "last.json") or {}
        if not pharm_failed and pharm_rows:
            last["pharmacies"] = pharm_rows
            last["pharmacies_date"] = target_date
        if not hosp_failed and hosp_parsed:
            last["hospitals"] = hosp_parsed
            last["hospitals_date"] = target_date
        last["updated_at"] = _now_iso()
        _write_json(CACHE_DIR / "last.json", last)

    if failed_sources:
        overall_source = "snapshot" if features else "unavailable"
    elif pharm_src == "live" and hosp_src == "live":
        overall_source = "live"
    elif "live" in (pharm_src, hosp_src) and "cache" in (pharm_src, hosp_src):
        overall_source = "live"
    else:
        overall_source = "cache"

    return {
        "type": "FeatureCollection",
        "date": target_date,
        "source": overall_source,
        "updated_at": _now_iso(),
        "failed_sources": failed_sources,
        "sources": [
            {"id": SOURCE_PHARMACIES, "name": LABEL_PHARMACIES, "url": config.ONDUTY_PHARMACIES_URL},
            {"id": SOURCE_HOSPITALS, "name": LABEL_HOSPITALS, "url": config.ONDUTY_HOSPITALS_URL},
        ],
        "features": features,
    }
