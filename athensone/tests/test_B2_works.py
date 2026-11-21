"""Tests for task B2: Works from Diavgeia + KHMDHS and GET /api/map/works."""
import io
import json
import os
from pathlib import Path

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import config, works  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)

SEED_PATH = config.DATA_DIR / "works_seed.json"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "B2"

SPEC_FIELDS = {
    "id",
    "title",
    "status",
    "contractor",
    "amount_contract_eur",
    "amount_paid_eur",
    "ada",
    "adam",
    "start_date",
    "end_date",
    "guarantee_end",
    "reports_count",
}


@pytest.fixture(autouse=True)
def _reset_works_cache():
    works._cache.clear()
    yield
    works._cache.clear()


def _use_seed(monkeypatch):
    monkeypatch.setenv("STOA_WORKS_PATH", str(SEED_PATH))
    works._cache.clear()


def _write_works_file(tmp_path: Path, monkeypatch, items: list[dict]) -> Path:
    path = tmp_path / "works.json"
    payload = {
        "source": "SEED",
        "snapshot": "2026-11-21",
        "organisation": "Δήμος Αθηναίων (test)",
        "note": "Synthetic test dataset",
        "works": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("STOA_WORKS_PATH", str(path))
    works._cache.clear()
    return path


def _make_work(
    wid: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    completion_date: str | None = None,
    amount_paid_eur: float | None = 25000.0,
    amount_contract_eur: float | None = 50000.0,
) -> dict:
    def ev(val, ada="TEST-ΑΔΑ-001"):
        if val is None:
            return {"value": None, "label": "UNKNOWN"}
        return {"value": val, "label": "CITED", "source": {"ada": ada, "page": 1}}

    return {
        "id": wid,
        "works_type": "sidewalk",
        "resolution": "street",
        "title": ev(f"Έργο {wid}"),
        "street": ev("Οδός Δοκιμής"),
        "contractor": ev("Ανάδοχος Δοκιμής"),
        "amount_contract_eur": ev(amount_contract_eur),
        "amount_paid_eur": ev(amount_paid_eur),
        "start_date": ev(start_date),
        "end_date": ev(end_date),
        "completion_date": ev(completion_date),
        "guarantee_months": ev(15),
        "final_acceptance": False,
        "geometry": {
            "type": "LineString",
            "coordinates": [[23.7410, 37.9656], [23.7420, 37.9660], [23.7430, 37.9664]],
        },
    }


def _dummy_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (320, 240), (120, 120, 120)).save(buf, "JPEG")
    return buf.getvalue()


def test_map_works_contract_fields(monkeypatch):
    # Checks that GET /api/map/works on the SEED dataset returns a FeatureCollection with all 12 SPEC fields on every feature.
    _use_seed(monkeypatch)
    r = c.get("/api/map/works")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert "source" in body and "updated_at" in body
    assert len(body["features"]) == 5
    for feat in body["features"]:
        assert feat["type"] == "Feature"
        assert feat["geometry"]["type"] in ("LineString", "MultiLineString", "Point")
        props = feat["properties"]
        assert SPEC_FIELDS.issubset(props.keys())
        assert props["id"]
        assert isinstance(props["reports_count"], int)


def test_map_works_bbox_filter(monkeypatch):
    # Checks that ?bbox= around W-SEED-001 only returns W-SEED-001.
    _use_seed(monkeypatch)
    r = c.get("/api/map/works", params={"bbox": "23.7408,37.9654,23.7431,37.9666"})
    assert r.status_code == 200
    ids = [f["properties"]["id"] for f in r.json()["features"]]
    assert ids == ["W-SEED-001"]


def test_map_works_status_filter(monkeypatch, tmp_path):
    # Checks that ?status=in_progress returns only in-progress works.
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")
    _write_works_file(
        tmp_path,
        monkeypatch,
        [
            _make_work("W-PLANNED", start_date="2026-12-01", end_date="2027-03-01"),
            _make_work("W-ACTIVE", start_date="2026-10-01", end_date="2026-12-15"),
            _make_work("W-DONE", start_date="2026-01-10", end_date="2026-06-30", completion_date="2026-06-30"),
        ],
    )
    r = c.get("/api/map/works", params={"status": "in_progress"})
    assert r.status_code == 200
    feats = r.json()["features"]
    assert [f["properties"]["id"] for f in feats] == ["W-ACTIVE"]
    assert all(f["properties"]["status"] == "in_progress" for f in feats)


def test_status_from_dates(monkeypatch, tmp_path):
    # Checks that status is derived as planned before start_date, in_progress between start_date and end_date, and completed after end_date.
    _write_works_file(
        tmp_path,
        monkeypatch,
        [_make_work("W-DATES", start_date="2026-03-01", end_date="2026-09-01", completion_date="2026-09-01")],
    )
    for today, expected in (
        ("2026-02-01", "planned"),
        ("2026-06-01", "in_progress"),
        ("2026-10-01", "completed"),
    ):
        monkeypatch.setenv("STOA_TODAY", today)
        r = c.get("/api/map/works")
        assert r.status_code == 200
        assert r.json()["features"][0]["properties"]["status"] == expected


def test_unknown_amount_is_null(monkeypatch, tmp_path):
    # Checks that an UNKNOWN amount_paid_eur is returned as null (None), never 0.
    _write_works_file(
        tmp_path,
        monkeypatch,
        [_make_work("W-UNK", start_date="2026-03-01", end_date="2026-12-31", amount_paid_eur=None, amount_contract_eur=50000.0)],
    )
    r = c.get("/api/map/works")
    assert r.status_code == 200
    props = r.json()["features"][0]["properties"]
    assert props["amount_paid_eur"] is None
    assert props["amount_contract_eur"] == 50000.0


def test_reports_count_near_line(monkeypatch):
    # Checks that reports_count counts only open reports within 30 m of the work line (2 inside 30 m, 1 at ~100 m -> 2).
    _use_seed(monkeypatch)
    c.post("/api/admin/reset")
    jpg = _dummy_jpeg()
    # W-SEED-001 runs from [23.7410, 37.9656] to [23.7430, 37.9664] (~197 m long).
    # Two points on the line (>50 m apart to avoid duplicate merging) and one ~100 m away.
    for lat, lng in ((37.9656, 23.7410), (37.9664, 23.7430), (37.96685, 23.74160)):
        rep = c.post(
            "/api/report",
            files={"photo": ("r.jpg", jpg, "image/jpeg")},
            data={"lat": lat, "lng": lng, "note": "σπασμένες πλάκες πεζοδρομίου"},
        )
        assert rep.status_code == 200
        assert rep.json()["duplicate_of"] is None

    r = c.get("/api/map/works")
    assert r.status_code == 200
    by_id = {f["properties"]["id"]: f["properties"] for f in r.json()["features"]}
    assert by_id["W-SEED-001"]["reports_count"] == 2


def test_diavgeia_parser_fixture():
    # Checks that works_src.parse_diavgeia parses a saved Diavgeia search fixture into decisions with ada, subject, date, amount.
    from app import works_src

    raw = json.loads((FIXTURES / "diavgeia.json").read_text(encoding="utf-8"))
    decisions = works_src.parse_diavgeia(raw)
    assert isinstance(decisions, list) and len(decisions) >= 1
    for d in decisions:
        assert d.get("ada") and isinstance(d["ada"], str)
        assert d.get("subject") and isinstance(d["subject"], str)
        assert d.get("date")
        assert "amount" in d
        if d["amount"] is not None:
            assert isinstance(d["amount"], (int, float))
    assert any(d["amount"] is not None for d in decisions)


def test_khmdhs_join_on_ada():
    # Checks that works_src.join_on_ada joins contractor and contract amount from saved KHMDHS fixture onto matching Diavgeia ADAs.
    from app import works_src

    diavgeia_raw = json.loads((FIXTURES / "diavgeia.json").read_text(encoding="utf-8"))
    khmdhs_raw = json.loads((FIXTURES / "khmdhs.json").read_text(encoding="utf-8"))
    decisions = works_src.parse_diavgeia(diavgeia_raw)
    contracts = works_src.parse_khmdhs(khmdhs_raw)
    joined = works_src.join_on_ada(decisions, contracts)

    assert isinstance(joined, list) and len(joined) >= 1
    dec_adas = {d["ada"] for d in decisions if d.get("ada")}
    con_by_ada = {k["ada"]: k for k in contracts if k.get("ada")}
    matched_adas = dec_adas & set(con_by_ada)
    assert matched_adas

    joined_by_ada = {row["ada"]: row for row in joined if row.get("ada") in matched_adas}
    assert matched_adas.issubset(joined_by_ada.keys())
    for ada in matched_adas:
        assert joined_by_ada[ada]["contractor"] == con_by_ada[ada]["contractor"]
        assert joined_by_ada[ada]["amount_contract_eur"] == con_by_ada[ada]["amount_contract_eur"]


def test_existing_works_routes_unchanged(monkeypatch):
    # Checks that /api/works/geojson and /api/works/radar keep their exact pre-B2 response keys.
    _use_seed(monkeypatch)
    monkeypatch.setenv("STOA_TODAY", "2026-11-21")

    gj_res = c.get("/api/works/geojson")
    assert gj_res.status_code == 200
    gj = gj_res.json()
    assert set(gj.keys()) == {"type", "features", "meta"}
    assert set(gj["meta"].keys()) == {"source", "snapshot", "organisation", "count", "note"}
    assert len(gj["features"]) == 5
    assert set(gj["features"][0].keys()) == {"type", "geometry", "properties"}
    assert set(gj["features"][0]["properties"].keys()) == {
        "id",
        "works_type",
        "works_type_el",
        "headline_el",
        "street",
        "contractor",
        "amount_paid_eur",
        "year",
        "ada",
        "status",
        "tier",
        "until",
    }

    rad_res = c.get("/api/works/radar", params={"days": 90})
    assert rad_res.status_code == 200
    rad = rad_res.json()
    assert set(rad.keys()) == {
        "window_days",
        "items",
        "total_eur",
        "coverage",
        "source",
        "snapshot",
        "organisation",
        "count",
        "note",
    }
    assert set(rad["coverage"].keys()) == {"usable", "total"}
    assert len(rad["items"]) == 2
    assert set(rad["items"][0]["clock"].keys()) == {
        "until",
        "status",
        "tier",
        "formula",
        "days_left",
        "term_label",
        "anchor_label",
    }
