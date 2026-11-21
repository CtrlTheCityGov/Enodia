"""Tests for B7: Points pill + panel, redeem."""
import json
import os
import sqlite3

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

from fastapi.testclient import TestClient  # noqa: E402

from app import config, points  # noqa: E402
from app.main import app  # noqa: E402


def _load_rewards_file() -> list[dict]:
    rewards_path = config.ROOT / "data" / "rewards.json"
    assert rewards_path.exists(), f"Missing {rewards_path}"
    raw = json.loads(rewards_path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    for key in ("rewards", "items"):
        if isinstance(raw.get(key), list):
            return raw[key]
    raise AssertionError("data/rewards.json must contain a rewards list")


def _new_account_client() -> tuple[TestClient, str]:
    client = TestClient(app)
    res = client.get("/api/points/me")
    assert res.status_code == 200
    token = res.cookies.get("ao_token")
    assert token
    return client, token


def test_points_contract():
    # GET /api/map/points returns all SPEC keys and loads rewards from data/rewards.json.
    TestClient(app).post("/api/admin/reset")
    client, token = _new_account_client()
    assert points.grant(token, "report_approved", "b7-c-1", "operator", district="1η Δημοτική Κοινότητα", points=10)
    assert points.grant(token, "guarantee_claim", "b7-c-2", "engineer", district="1η Δημοτική Κοινότητα", points=30)

    res = client.get("/api/map/points")
    assert res.status_code == 200
    body = res.json()

    assert {"balance", "district", "history", "rewards"} <= body.keys()
    assert body["balance"] == 40
    assert {"name", "progress_pct", "goal"} <= body["district"].keys()
    assert body["district"]["name"] == "1η Δημοτική Κοινότητα"
    assert 0 <= body["district"]["progress_pct"] <= 100
    assert isinstance(body["district"]["goal"], int) and body["district"]["goal"] > 0

    assert isinstance(body["history"], list) and len(body["history"]) == 2
    for entry in body["history"]:
        assert {"ts", "delta", "reason"} <= entry.keys()
        assert isinstance(entry["ts"], str) and entry["ts"]
        assert isinstance(entry["delta"], int)
        assert isinstance(entry["reason"], str) and entry["reason"]
    assert sum(entry["delta"] for entry in body["history"]) == 40

    file_rewards = _load_rewards_file()
    assert len(file_rewards) >= 1
    assert [(r["id"], r["title"], r["cost"]) for r in body["rewards"]] == [
        (r["id"], r["title"], r["cost"]) for r in file_rewards
    ]


def test_balance_minus_redeemed():
    # Earning 50 points and redeeming a 30-point reward leaves balance 20 in both redeem and points responses.
    TestClient(app).post("/api/admin/reset")
    client, token = _new_account_client()
    assert points.grant(token, "guarantee_claim", "b7-bal-1", "test", district="1η Δημοτική Κοινότητα", points=50)

    pts_before = client.get("/api/map/points")
    assert pts_before.status_code == 200
    reward_30 = next((r for r in pts_before.json()["rewards"] if r["cost"] == 30), None)
    assert reward_30 is not None, "Expected a 30-point reward in /api/map/points"

    redeem = client.post("/api/map/points/redeem", json={"reward_id": reward_30["id"]})
    assert redeem.status_code == 200
    rbody = redeem.json()
    assert rbody["ok"] is True
    assert rbody["balance"] == 20
    assert rbody.get("voucher_code")

    pts_after = client.get("/api/map/points")
    assert pts_after.status_code == 200
    assert pts_after.json()["balance"] == 20


def test_redeem_not_enough():
    # Redeeming a 30-point reward with 10 points returns ok=false, leaves balance unchanged, and writes no redemption row.
    TestClient(app).post("/api/admin/reset")
    client, token = _new_account_client()
    assert points.grant(token, "report_approved", "b7-low-1", "test", district="1η Δημοτική Κοινότητα", points=10)

    pts_before = client.get("/api/map/points")
    assert pts_before.status_code == 200
    reward_30 = next((r for r in pts_before.json()["rewards"] if r["cost"] == 30), None)
    assert reward_30 is not None, "Expected a 30-point reward in /api/map/points"

    with sqlite3.connect(config.DB_PATH) as conn:
        rows_before = conn.execute("SELECT COUNT(*) FROM redemptions").fetchone()[0]

    redeem = client.post("/api/map/points/redeem", json={"reward_id": reward_30["id"]})
    assert redeem.status_code == 200
    rbody = redeem.json()
    assert rbody["ok"] is False
    assert rbody["balance"] == 10
    assert not rbody.get("voucher_code")

    assert client.get("/api/map/points").json()["balance"] == 10
    with sqlite3.connect(config.DB_PATH) as conn:
        rows_after = conn.execute("SELECT COUNT(*) FROM redemptions").fetchone()[0]
    assert rows_after == rows_before


def test_redeem_unknown_reward_404():
    # Redeeming an unknown reward_id returns HTTP 404.
    TestClient(app).post("/api/admin/reset")
    client, _ = _new_account_client()

    res = client.post("/api/map/points/redeem", json={"reward_id": "UNKNOWN-REWARD-999"})
    assert res.status_code == 404


def test_voucher_not_token():
    # Redeeming generates a voucher_code distinct from the ao_token cookie and containing no substring of it.
    TestClient(app).post("/api/admin/reset")
    client, token = _new_account_client()

    pts = client.get("/api/map/points")
    assert pts.status_code == 200
    reward = pts.json()["rewards"][0]
    assert points.grant(token, "guarantee_claim", "b7-v-1", "test", district="1η Δημοτική Κοινότητα", points=reward["cost"])

    redeem = client.post("/api/map/points/redeem", json={"reward_id": reward["id"]})
    assert redeem.status_code == 200
    rbody = redeem.json()
    assert rbody["ok"] is True
    voucher = rbody["voucher_code"]
    assert isinstance(voucher, str) and len(voucher) >= 4
    assert voucher != token
    assert all(token[i:i + 6].lower() not in voucher.lower() for i in range(len(token) - 5))


def test_no_cookie_new_account_zero():
    # Calling GET /api/map/points without an ao_token cookie mints an HttpOnly cookie and returns balance 0.
    TestClient(app).post("/api/admin/reset")
    fresh = TestClient(app)

    res = fresh.get("/api/map/points")
    assert res.status_code == 200
    token = res.cookies.get("ao_token")
    assert token and points.is_valid_token(token)
    assert "httponly" in res.headers.get("set-cookie", "").lower()
    assert res.json()["balance"] == 0


def test_district_progress_pct_bounds(monkeypatch):
    # District progress_pct caps at 100 even when total district points exceed the goal.
    monkeypatch.setenv("DISTRICT_TARGET", "100")
    TestClient(app).post("/api/admin/reset")
    client, token = _new_account_client()
    assert points.grant(token, "guarantee_claim", "b7-pct-1", "test", district="1η Δημοτική Κοινότητα", points=150)

    res = client.get("/api/map/points")
    assert res.status_code == 200
    district = res.json()["district"]
    assert district["goal"] == 100
    assert district["progress_pct"] == 100


def test_existing_points_routes_unchanged():
    # Existing /api/points/me and /api/points/districts endpoints keep their exact response keys.
    TestClient(app).post("/api/admin/reset")
    client, token = _new_account_client()
    assert points.grant(token, "report_approved", "b7-ext-1", "operator", district="1η Δημοτική Κοινότητα")

    me = client.get("/api/points/me")
    assert me.status_code == 200
    me_body = me.json()
    assert set(me_body.keys()) == {"balance", "tier", "entries"}
    assert set(me_body["entries"][0].keys()) == {
        "id", "district", "action", "ref_id", "points", "verified_by", "created_at",
    }

    dist = client.get("/api/points/districts")
    assert dist.status_code == 200
    dist_body = dist.json()
    assert set(dist_body.keys()) == {"items", "target"}
    assert set(dist_body["items"][0].keys()) == {"district", "points"}
