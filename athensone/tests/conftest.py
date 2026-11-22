"""Shared test setup.

Tests run on the small fictional SEED environment set (data/env_seed.json), not on the real OpenStreetMap extract in
data/env/features.json that the demo uses: route-ranking tests need fixed data. app/env.py reads ENV_FEATURES_PATH
first (see its loader), so pointing it at the seed file here keeps every test deterministic.
"""
import os
import tempfile
from pathlib import Path

# Tests get their own database and photo folder, never the demo ones (data/athensone.db, data/photos/).
_TMP = Path(tempfile.mkdtemp(prefix="athensone-tests-"))
os.environ.setdefault("ATHENSONE_DB", str(_TMP / "test.db"))
os.environ.setdefault("ATHENSONE_PHOTO_DIR", str(_TMP / "photos"))

os.environ.setdefault("ENV_FEATURES_PATH", str(Path(__file__).resolve().parent.parent / "data" / "env_seed.json"))
os.environ.setdefault("STOA_WORKS_PATH", str(Path(__file__).resolve().parent.parent / "data" / "works_seed.json"))
