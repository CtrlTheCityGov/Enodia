"""Shared test setup.

Tests run on the small fictional SEED environment set (data/env_seed.json), not on the real OpenStreetMap extract in
data/env/features.json that the demo uses: route-ranking tests need fixed data. app/env.py reads ENV_FEATURES_PATH
first (see its loader), so pointing it at the seed file here keeps every test deterministic.
"""
import os
from pathlib import Path

os.environ.setdefault("ENV_FEATURES_PATH", str(Path(__file__).resolve().parent.parent / "data" / "env_seed.json"))
