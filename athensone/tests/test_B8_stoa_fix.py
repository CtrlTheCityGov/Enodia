"""Fix-round tests for B8: SandboxError in city_ask returns 200 refusal instead of 502."""
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.main import app  # noqa: E402
from app.sandbox import SandboxError  # noqa: E402

c = TestClient(app)
SYNTAGMA = [23.7348, 37.9755]
REFUSAL_PREFIX = "Δεν βρήκα τεκμηριωμένα στοιχεία"


def test_sandbox_error_returns_refusal_200(monkeypatch):
    # Verify that when the City sandbox raises SandboxError, /api/map/stoa_ask returns HTTP 200 refusal, not 502.
    def boom(*args, **kwargs):
        raise SandboxError("sandbox unreachable")

    monkeypatch.setattr(main.sb, "search", boom)

    r = c.post(
        "/api/map/stoa_ask",
        json={"question": "Πώς βγάζω βεβαίωση μόνιμης κατοικίας;", "center": SYNTAGMA, "history": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert REFUSAL_PREFIX in body["answer_md"]
    assert body["citations"] == []
