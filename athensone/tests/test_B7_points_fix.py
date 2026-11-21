"""Fix-round tests for B7: /api/admin/reset clears redemptions so balance never turns negative."""
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

from fastapi.testclient import TestClient  # noqa: E402

from app import points  # noqa: E402
from app.main import app  # noqa: E402


def test_reset_clears_redemptions():
    # Earn 50, redeem a 30 reward, then reset: the same cookie must have balance 0 (not -30).
    TestClient(app).post("/api/admin/reset")
    client = TestClient(app)
    res = client.get("/api/points/me")
    token = res.cookies.get("ao_token")
    assert token

    assert points.grant(token, "guarantee_claim", "b7-fix-1", "test", district="1η Δημοτική Κοινότητα", points=50)
    rewards_list = client.get("/api/map/points").json()["rewards"]
    reward_30 = next(r for r in rewards_list if r["cost"] == 30)

    red = client.post("/api/map/points/redeem", json={"reward_id": reward_30["id"]})
    assert red.status_code == 200 and red.json()["ok"] is True
    assert client.get("/api/map/points").json()["balance"] == 20

    client.post("/api/admin/reset")
    after = client.get("/api/map/points")
    assert after.status_code == 200
    assert after.json()["balance"] == 0
    assert after.json()["history"] == []
