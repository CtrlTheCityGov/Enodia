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

# --- B2 ---
# Works from Διαύγεια + ΚΗΜΔΗΣ. URLs checked online on Sat 21 Nov 2026 (both answered 200 with JSON). Certainty: sure.
DIAVGEIA_URL = os.getenv("DIAVGEIA_URL", "https://diavgeia.gov.gr/opendata").rstrip("/")
KHMDHS_URL = os.getenv("KHMDHS_URL", "https://cerpp.eprocurement.gov.gr/khmdhs-opendata").rstrip("/")
# Δήμος Αθηναίων: organisation uid 6013 in Διαύγεια (organizations.json) and key 6013 in ΚΗΜΔΗΣ (contract
# 26SYMV019034442). Checked Sat 21 Nov 2026. Certainty: sure.
WORKS_ORG = os.getenv("WORKS_ORG", "6013")
# Upstream timeout, seconds (TASKS_B «Common to B2–B5»: 10 s). Certainty: sure.
WORKS_HTTP_TIMEOUT_S = float(os.getenv("WORKS_HTTP_TIMEOUT_S", "10"))
# reports_count counts open reports within this many metres of a works line (B2 card). Certainty: sure.
WORKS_REPORT_RADIUS_M = float(os.getenv("WORKS_REPORT_RADIUS_M", "30"))
# --- /B2 ---
