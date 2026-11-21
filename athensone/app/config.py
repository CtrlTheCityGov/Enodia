"""All settings come from environment variables (see .env.example)."""
import os
from pathlib import Path

try:  # optional: load .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PHOTO_DIR = DATA_DIR / "photos"
DB_PATH = DATA_DIR / "athensone.db"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

SANDBOX_URL = os.getenv("SANDBOX_URL", "https://athensgov.cityofathens.gr/sandbox").rstrip("/")
SANDBOX_KEY = os.getenv("SANDBOX_KEY", "")
PERSONA = os.getenv("PERSONA", "p2")  # p2 = retiree in Pangrati ("Maria")
# No key -> mock mode, so the team can build before the key arrives.
MOCK = os.getenv("MOCK", "").lower() in ("1", "true", "yes") or not SANDBOX_KEY

VALHALLA_URL = os.getenv("VALHALLA_URL", "https://valhalla1.openstreetmap.de").rstrip("/")

# Vision / LLM provider: "anthropic", "openai" (any OpenAI-compatible server: vLLM, Ollama, ...) or "mock"
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "mock")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "llava")

# Reports within this distance and same category count as duplicates
DUPLICATE_RADIUS_KM = float(os.getenv("DUPLICATE_RADIUS_KM", "0.05"))
# Below this AI confidence the operator screen flags "check category"
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.85"))

# Demo start point: Plateia Varnava, Pangrati
DEMO_START = {"lat": 37.9667, "lng": 23.7437}

# Weather for heat-aware routing (Open-Meteo, no key). "off" in tests / offline demos.
WEATHER = os.getenv("WEATHER", "on").lower()
HEAT_C = float(os.getenv("HEAT_C", "33"))  # at or above this, shade weight goes up automatically

# AthensGov open data (CKAN). live = call the portal (snapshots saved to data/ckan/),
# snapshot = only use saved snapshots (offline demo), off = never (tests).
CKAN_URL = os.getenv("CKAN_URL", "https://opendata.cityofathens.gr/api/3/action").rstrip("/")
CKAN_MODE = os.getenv("CKAN_MODE", "live").lower()

# --- T3: Heat alert banner ---
# Winter demo switch: forces hot=True on /api/heat with forced=True so the UI labels it "δοκιμαστικό".
# Source: TASKS.md T3 card (approved A-1); parsing matches MOCK above (line 22). Certainty: sure.
HEAT_FORCE = os.getenv("HEAT_FORCE", "").lower() in ("1", "true", "yes")
# --- /T3 ---

# --- B3: Transit (metro, suburban, OASA buses) ---
# OASA Telematics public API base URL.
# Source: verified live Sat 21 Nov 2026 (GET ?act=webGetLines, getBusLocation, getStopArrivals -> HTTP 200 JSON). Certainty: sure.
OASA_TELEMATICS_URL = os.getenv("OASA_TELEMATICS_URL", "https://telematics.oasa.gr/api/").rstrip("/") + "/"
# Upstream HTTP timeout in seconds. Source: TASKS_B.md "Common to B2-B5" (10 s). Certainty: sure.
TRANSIT_HTTP_TIMEOUT = float(os.getenv("TRANSIT_HTTP_TIMEOUT", "10"))
# In-memory TTL cache for live bus positions and stop arrivals (seconds).
# Source: SPEC.md "Εξωτερικές πηγές" Τηλεματική (20 s polling) & TASKS_B.md B3. Certainty: sure.
TRANSIT_BUS_TTL_S = int(os.getenv("TRANSIT_BUS_TTL_S", "20"))
TRANSIT_ARRIVALS_TTL_S = int(os.getenv("TRANSIT_ARRIVALS_TTL_S", "20"))

# Overpass endpoints for one-off scripts/fetch_transit.py static rail build (OSM ODbL).
# Source: overpass-api.de (same as scripts/fetch_env.py) + overpass.private.coffee mirror verified Sat 21 Nov 2026. Certainty: sure.
TRANSIT_OVERPASS_URLS = [
    u.strip()
    for u in os.getenv(
        "TRANSIT_OVERPASS_URLS",
        "https://overpass-api.de/api/interpreter,https://overpass.private.coffee/api/interpreter",
    ).split(",")
    if u.strip()
]

# Default central-Athens OASA bus/trolleybus routes polled by /api/map/transit.
# Source: verified live Sat 21 Nov 2026 via telematics.oasa.gr/api/ (webGetLines, webGetRoutes, webGetStops);
# bboxes computed from each route's real stop coordinates. Certainty: sure (route codes can change on OASA schedule updates).
_DEFAULT_TRANSIT_ROUTES: list[dict] = [
    {"route_code": "3922", "line": "040", "name": "ΠΕΙΡΑΙΑΣ - ΣΥΝΤΑΓΜΑ", "bbox": (23.6319, 37.9353, 23.7340, 37.9745)},
    {"route_code": "3923", "line": "040", "name": "ΣΥΝΤΑΓΜΑ - ΠΕΙΡΑΙΑΣ", "bbox": (23.6302, 37.9353, 23.7340, 37.9745)},
    {"route_code": "2051", "line": "Χ95", "name": "ΣΥΝΤΑΓΜΑ - ΑΕΡΟΛ. ΑΘΗΝΩΝ", "bbox": (23.7349, 37.9212, 23.9465, 38.0134)},
    {"route_code": "2052", "line": "Χ95", "name": "ΑΕΡ/ΝΑΣ ΑΘΗΝΩΝ - ΣΥΝΤΑΓΜΑ", "bbox": (23.7349, 37.9217, 23.9465, 38.0134)},
    {"route_code": "4914", "line": "2", "name": "ΚΑΙΣΑΡΙΑΝΗ - ΠΑΓΚΡΑΤΙ - ΑΝΩ ΚΥΨΕΛΗ", "bbox": (23.7308, 37.9672, 23.7557, 38.0062)},
    {"route_code": "5196", "line": "2", "name": "ΑΝΩ ΚΥΨΕΛΗ - ΠΑΓΚΡΑΤΙ - ΚΑΙΣΑΡΙΑΝΗ", "bbox": (23.7298, 37.9653, 23.7557, 38.0062)},
    {"route_code": "4906", "line": "608", "name": "ΓΑΛΑΤΣΙ - ΑΚΑΔΗΜΙΑ - ΝΕΚΡ. ΖΩΓΡΑΦΟΥ", "bbox": (23.7303, 37.9711, 23.7815, 38.0266)},
    {"route_code": "5346", "line": "608", "name": "ΝΕΚΡ. ΖΩΓΡΑΦΟΥ - ΑΚΑΔΗΜΙΑ - ΓΑΛΑΤΣΙ", "bbox": (23.7286, 37.9711, 23.7815, 38.0342)},
]


def _load_transit_routes() -> list[dict]:
    """Parse optional TRANSIT_ROUTES env var ('code:line,code:line') or fall back to defaults."""
    raw = os.getenv("TRANSIT_ROUTES", "").strip()
    if not raw:
        return list(_DEFAULT_TRANSIT_ROUTES)
    by_code = {r["route_code"]: r for r in _DEFAULT_TRANSIT_ROUTES}
    out: list[dict] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            rc, line = item.split(":", 1)
            rc, line = rc.strip(), line.strip()
        else:
            rc = item
            line = by_code.get(rc, {}).get("line", rc)
        base = by_code.get(rc, {})
        out.append({"route_code": rc, "line": line, "name": base.get("name", ""), "bbox": base.get("bbox")})
    return out


TRANSIT_ROUTES: list[dict] = _load_transit_routes()
# --- /B3 ---
