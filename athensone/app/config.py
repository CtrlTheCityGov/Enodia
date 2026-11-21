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

# --- B4: On-duty pharmacies and hospitals ---
# Source: Verified live 2026-11-21 — POST Date=YYYY-MM-DD&IsOpen=false returns HTML cards for Attica.
# Certainty: sure (HTTP 200 verified).
ONDUTY_PHARMACIES_URL = os.getenv(
    "ONDUTY_PHARMACIES_URL",
    "https://fsa-efimeries.gr/Home/FilteredHomeResults",
)
# Source: Verified live 2026-11-21 — Ministry of Health Attica daily hospital duty index (?fdl=<id> .doc).
# Certainty: sure (HTTP 200 verified).
ONDUTY_HOSPITALS_URL = os.getenv(
    "ONDUTY_HOSPITALS_URL",
    "https://www.moh.gov.gr/articles/citizen/efhmeries-nosokomeiwn/68-efhmeries-nosokomeiwn-attikhs",
)
# Source: OpenStreetMap Nominatim search API (verified live HTTP 200 on 2026-11-21; ODbL 1.0).
# Certainty: sure.
ONDUTY_GEOCODE_URL = os.getenv(
    "ONDUTY_GEOCODE_URL",
    "https://nominatim.openstreetmap.org/search",
)
# Source: TASKS_B.md B4 card ("once a day, cached") -> 86400 s = 24 hours. Certainty: sure.
ONDUTY_TTL_S = int(os.getenv("ONDUTY_TTL_S", "86400"))
# Source: TASKS_B.md Common to B2-B5 ("httpx with a 10 s timeout"). Certainty: sure.
ONDUTY_TIMEOUT_S = float(os.getenv("ONDUTY_TIMEOUT_S", "10"))
# Source: OpenStreetMap Nominatim Usage Policy requires an identifying User-Agent header. Certainty: sure.
ONDUTY_USER_AGENT = os.getenv(
    "ONDUTY_USER_AGENT",
    "AthensOne/0.1 (Apps4Athens 3.0 hackathon)",
)
# Greater Athens WGS84 bounding box (min_lon, min_lat, max_lon, max_lat) used to keep Attica-wide
# FSA pharmacy results scoped to metropolitan Athens.
# Source: TASKS_B.md B0/B4 bounds (lon 23.60-23.90, lat 37.85-38.15). Certainty: sure.
ONDUTY_BBOX = (23.60, 37.85, 23.90, 38.15)
# --- /B4 ---
