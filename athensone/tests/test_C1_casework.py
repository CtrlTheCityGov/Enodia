"""C1: category normalisation, guarantee engine, Stoa matching, duplicate linking, case workflow, dossier, tracker.

Fully offline (mock sandbox, CKAN off). Uses the real Stoa dataset data/stoa/works.json (10 real Diavgeia decisions
+ 2 SEED records) where the canonical demo depends on it, and synthetic records for the pure-engine edge cases.
"""
import os
from datetime import date
from pathlib import Path

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import categories, guarantee, stoa_match  # noqa: E402
from app.main import app  # noqa: E402

REAL_WORKS = str(Path(__file__).resolve().parent.parent / "data" / "stoa" / "works.json")
TODAY = date(2026, 11, 22)
ERMOU = (37.97570, 23.73300)      # on the representative segment of real W-DIAV-001
YMITTOU = (37.96925, 23.74620)    # on SEED W-SEED-002 (complete synthetic contract)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("STOA_WORKS_PATH", REAL_WORKS)
    monkeypatch.setenv("STOA_TODAY", TODAY.isoformat())
    monkeypatch.delenv("OPERATOR_KEY", raising=False)
    c = TestClient(app)
    c.post("/api/admin/reset")
    return c


def _map_report(c, lat, lng, category="damage", subtype="sidewalk", note="σπασμένες πλάκες"):
    data = {"category": category, "lon": lng, "lat": lat, "note": note}
    if subtype:
        data["subtype"] = subtype
    r = c.post("/api/map/reports", data=data)
    assert r.status_code == 200, r.text
    return r.json()


def _act(c, rid, **body):
    body.setdefault("actor", "Μηχ. Δοκιμή")
    return c.post(f"/api/cases/{rid}/actions", json=body)


# ------------------------------------------------------------------ categories
def test_damage_sidewalk_reaches_stoa():
    n = categories.normalise("damage", "sidewalk", "")
    assert n["city_category"] == "sidewalk" and n["stoa_eligible"] and not n["needs_review"]


def test_damage_without_subtype_is_not_invented():
    n = categories.normalise("damage", None, "κάτι χάλασε")
    assert n["city_category"] == "other" and not n["stoa_eligible"] and n["needs_review"]


def test_keywords_suggest_but_flag_review():
    n = categories.normalise("damage", None, "Μεγάλη λακκούβα στο οδόστρωμα")
    assert n["city_category"] == "pothole" and n["method"] == "keywords" and n["needs_review"]


def test_obstacle_never_triggers_stoa():
    n = categories.normalise("obstacle", None, "μηχανάκι πάνω στη ράμπα")
    assert n["city_category"] == "sidewalk" and not n["stoa_eligible"]


def test_original_choice_is_kept():
    n = categories.normalise("damage", "pothole", "x")
    assert n["original_category"] == "damage" and n["original_subtype"] == "pothole"


# ------------------------------------------------------------------ guarantee engine
def _w(**f):
    base = {"id": "W-T", "ada": {"value": "ΑΔΑ-Τ", "label": "CITED"}}
    base.update(f)
    return base


def test_missing_completion_gives_unknown_and_no_date():
    g = guarantee.evaluate(_w(completion_date={"value": None, "label": "UNKNOWN"}), TODAY)
    assert g["state"] == "UNKNOWN" and g["expiry"] is None and g["days_remaining"] is None


def test_contract_term_and_certificate_give_active_clock():
    g = guarantee.evaluate(_w(completion_date={"value": "2026-02-15", "label": "CITED", "source": {"ada": "X"}},
                              guarantee_months={"value": 24, "label": "CITED", "source": {"ada": "X"}}), TODAY)
    assert g["state"] == "ACTIVE" and g["expiry"] == "2028-02-15"
    assert g["start"]["date"] == "2026-02-16"  # day after the certificate (art. 171 as replaced by ν. 4782/2021)
    assert g["period"]["basis"] == "CONTRACTUALLY_VERIFIED" and g["start"]["basis"] == "OFFICIALLY_DOCUMENTED"


def test_legal_default_is_labelled_and_warns_below_250k():
    g = guarantee.evaluate(_w(completion_date={"value": "2026-02-15", "label": "CITED"},
                              amount_contract_eur={"value": 90000.0, "label": "CITED"}), TODAY)
    assert g["period"]["basis"] == "LEGAL_DEFAULT" and g["period"]["months"] == 15
    assert any("250.000" in x for x in g["limitations"]) and g["requires_review"]


def test_expired_period():
    g = guarantee.evaluate(_w(completion_date={"value": "2020-01-10", "label": "CITED"},
                              guarantee_months={"value": 15, "label": "CITED"}), TODAY)
    assert g["state"] == "EXPIRED" and g["days_remaining"] < 0


def test_conflicting_sources_require_review():
    g = guarantee.evaluate(_w(completion_date={"value": "2026-02-15", "label": "CITED",
                                               "conflicts": [{"value": "2026-05-01", "source": {"ada": "Y"}}]},
                              guarantee_months={"value": 15, "label": "CITED"}), TODAY)
    assert g["state"] == "REQUIRES_HUMAN_REVIEW" and g["conflicts"]


def test_guarantee_return_without_date_requires_review_not_a_date():
    g = guarantee.evaluate(_w(completion_date={"value": None, "label": "UNKNOWN"},
                              final_acceptance_evidence={"value": True, "label": "INFERRED"}), TODAY)
    assert g["state"] == "REQUIRES_HUMAN_REVIEW" and g["expiry"] is None


# ------------------------------------------------------------------ matching
LINE = {"type": "LineString", "coordinates": [[23.7300, 37.9760], [23.7320, 37.9760]]}


def test_district_contract_is_neighbourhood_not_exact():
    w = _w(works_type="sidewalk", title={"value": "Πεζοδρόμια στην 1η, 2η & 3η Δ.Κ. (τμήμα Ερμού)"}, geometry=LINE)
    r = stoa_match.match(37.9760, 23.7310, {"sidewalk"}, [w], TODAY, district="1η Δημοτική Κοινότητα")
    c = r["candidates"][0]
    assert c["match_type"] == "NEIGHBOURHOOD" and c["confidence"] < 0.5
    assert any("ενδεικτική χάραξη" in u for u in c["uncertainty"])


def test_municipality_contract_is_weak():
    w = _w(works_type="sidewalk", title={"value": "Πεζοδρόμια σε όλες τις Δ.Κ. του Δ.Α."}, geometry=LINE)
    c = stoa_match.match(37.9760, 23.7310, {"sidewalk"}, [w], TODAY)["candidates"][0]
    assert c["match_type"] == "MUNICIPALITY" and c["confidence"] <= 0.2


def test_street_contract_on_street_matches():
    w = _w(works_type="sidewalk", title={"value": "Ανακατασκευή πεζοδρομίων οδού Τεστ"}, geometry=LINE,
           geometry_basis="documented")
    c = stoa_match.match(37.97601, 23.7310, {"sidewalk"}, [w], TODAY)["candidates"][0]
    assert c["match_type"] == "EXACT" and c["confidence"] >= 0.8


def test_wrong_works_type_is_ignored():
    w = _w(works_type="lighting", title={"value": "Φωτισμός οδού Τεστ"}, geometry=LINE)
    assert stoa_match.match(37.9760, 23.7310, {"sidewalk"}, [w], TODAY)["candidates"] == []


def test_no_types_means_no_match():
    assert stoa_match.match(37.9760, 23.7310, set(), [], TODAY)["match_type"] == "NONE"


def test_rejected_match_is_never_best():
    w = _w(works_type="sidewalk", title={"value": "Πεζοδρόμια οδού Τεστ"}, geometry=LINE)
    r = stoa_match.match(37.9760, 23.7310, {"sidewalk"}, [w], TODAY, reviews={"W-T": {"verdict": "reject"}})
    assert r["best"] is None and r["candidates"][0]["rejected"]


# ------------------------------------------------------------------ integration: report → case → Stoa
def test_map_damage_sidewalk_creates_case_with_real_stoa_candidate(client):
    out = _map_report(client, *ERMOU)
    rid = out["city_request_id"]
    assert rid and out["classification"]["stoa_eligible"]
    v = client.get(f"/api/cases/{rid}").json()
    assert v["stage"] == "NEW" and v["report"]["category"] == "sidewalk"
    best = v["stoa"]["best"]
    assert best["work_id"] == "W-DIAV-001" and best["work"]["source_url"].startswith("https://diavgeia.gov.gr/")
    assert best["guarantee"]["state"] == "UNKNOWN" and best["guarantee"]["expiry"] is None  # no fabricated date


def test_duplicate_is_linked_not_dropped_and_reversible(client):
    first = _map_report(client, *ERMOU)
    second = _map_report(client, ERMOU[0] + 0.0001, ERMOU[1], note="και εδώ σπασμένη πλάκα")
    rid = first["city_request_id"]
    assert second["linked_to_existing"] and second["city_request_id"] == rid
    v = client.get(f"/api/cases/{rid}").json()
    assert v["support_count"] == 2 and v["supporting"][0]["child_id"] == second["tracking_id"]
    t = client.get(f"/api/track/{second['tracking_id']}").json()
    assert t["linked_to_existing"] and t["city_case"] == rid and t["support_count"] == 2
    # reverse the merge: needs a reason, then the submission gets its own City request
    assert client.post(f"/api/cases/{rid}/links/{second['tracking_id']}/unlink", json={"actor": "Α", "reason": ""}).status_code == 422
    u = client.post(f"/api/cases/{rid}/links/{second['tracking_id']}/unlink",
                    json={"actor": "Α", "reason": "Διαφορετική βλάβη, απέναντι πεζοδρόμιο"}).json()
    assert u["own_request_id"] != rid
    assert client.get(f"/api/cases/{rid}").json()["support_count"] == 1
    assert client.get(f"/api/track/{second['tracking_id']}").json()["city_case"] == u["own_request_id"]


def test_legacy_photo_duplicate_keeps_the_submission(client):
    import io

    from PIL import Image

    def jpeg():
        b = io.BytesIO()
        Image.new("RGB", (64, 64), (120, 120, 120)).save(b, "JPEG")
        return b.getvalue()

    a = client.post("/api/report", files={"photo": ("a.jpg", jpeg(), "image/jpeg")},
                    data={"lat": "37.9682", "lng": "23.7457", "note": "ράμπα"}).json()
    b = client.post("/api/report", files={"photo": ("b.jpg", jpeg(), "image/jpeg")},
                    data={"lat": "37.96822", "lng": "23.7457", "note": "ράμπα"}).json()
    assert b["duplicate_of"] == a["request"]["id"]
    v = client.get(f"/api/cases/{a['request']['id']}").json()
    assert v["support_count"] == 2 and v["supporting"][0]["photo_url"]


# ------------------------------------------------------------------ workflow
def test_actor_reason_and_role_are_enforced(client):
    rid = _map_report(client, *YMITTOU)["city_request_id"]
    assert _act(client, rid, action="start_investigation", actor="").status_code == 422
    assert _act(client, rid, action="start_investigation").status_code == 200
    assert _act(client, rid, action="accept_match", work_id="W-SEED-002", role="operator").status_code == 403
    assert _act(client, rid, action="accept_match", work_id="NOPE", role="engineer").status_code == 422
    assert _act(client, rid, action="reject_match", work_id="W-SEED-002", role="engineer").status_code == 422  # no reason
    assert _act(client, rid, action="resolve").status_code == 409  # not allowed at this stage


def test_contractor_referral_blocked_without_claim_supporting_dossier(client):
    rid = _map_report(client, *ERMOU)["city_request_id"]
    _act(client, rid, action="start_investigation")
    _act(client, rid, action="accept_match", work_id="W-DIAV-001", role="engineer")
    d = _act(client, rid, action="generate_dossier", role="engineer").json()
    assert d["can_draft_claim"] is False  # completion date unknown → evidence summary only
    r = _act(client, rid, action="decide_refer_contractor", role="engineer", reason="θέλω")
    assert r.status_code == 409
    html = client.get(d["url"]).text
    assert "ΔΕΝ ΕΧΕΙ ΑΠΟΣΤΑΛΕΙ" in html and "Δεν συντάχθηκε" in html and "Ψ0ΣΝΩ6Μ-5ΙΖ" in html


def test_full_seed_workflow_is_audited_and_citizen_sees_only_public_info(client):
    rep = _map_report(client, *YMITTOU)
    rid = rep["city_request_id"]
    steps = [dict(action="start_investigation"),
             dict(action="accept_match", role="engineer", work_id="W-SEED-002"),
             dict(action="generate_dossier", role="engineer"),
             dict(action="decide_refer_contractor", role="engineer", reason="Φθορά του έργου μετά από αυτοψία"),
             dict(action="legal_approve", role="engineer", reason="x")]  # wrong role
    for s in steps[:-1]:
        assert _act(client, rid, **s).status_code == 200, s
    assert _act(client, rid, **steps[-1]).status_code == 403
    assert _act(client, rid, action="legal_approve", role="legal", reason="Σύμφωνη γνώμη").status_code == 200
    assert _act(client, rid, action="resolve").status_code == 200
    assert _act(client, rid, action="notify_citizen", reason="ok", message="Αποκαταστάθηκε.").json()["stage"] == "CITIZEN_NOTIFIED"
    v = client.get(f"/api/cases/{rid}").json()
    actions = [e["action"] for e in v["events"]]
    assert actions[0] == "created" and "legal_approve" in actions and all(e["actor"] for e in v["events"])
    dos = client.get(f"/api/cases/{rid}/dossiers/{v['dossiers'][0]['id']}").text
    assert "SEED" in dos and "ΣΧΕΔΙΟ" in dos and "2027-05-15" in dos  # 15/02/2026 + 15 contract months
    t = client.get(f"/api/track/{rep['tracking_id']}").json()
    blob = str(t)
    assert t["stage_el"] == "Αποκαταστάθηκε" and "Αποκαταστάθηκε." in blob
    assert "Ανάδοχος" not in blob and "SEED" not in blob and "Μηχ." not in blob


def test_operator_key_protects_case_endpoints(client, monkeypatch):
    rid = _map_report(client, *ERMOU)["city_request_id"]
    monkeypatch.setenv("OPERATOR_KEY", "s3cret")
    assert client.get(f"/api/cases/{rid}").status_code == 403
    assert client.post("/api/admin/reset").status_code == 403
    assert client.get(f"/api/cases/{rid}", headers={"X-Operator-Key": "s3cret"}).status_code == 200
    assert client.get(f"/api/track/{rid}").status_code == 200  # citizen tracker stays public


def test_demo_seed_is_deterministic(client):
    a = client.post("/api/admin/demo-seed").json()
    b = client.post("/api/admin/demo-seed").json()
    assert set(a["created"]) == set(b["created"]) == {"ermou", "ymittou"}
    items = client.get("/api/reports").json()["items"]
    assert len(items) == 2
    bests = sorted(i["case"]["stoa"]["best"]["work_id"] for i in items)
    assert bests == ["W-DIAV-001", "W-SEED-002"]


# ------------------------------------------------------------------ ingestion merge
def test_merge_never_downgrades_and_records_conflicts():
    from app import stoa_ingest

    old = [{"id": "W-1", "ada": {"value": "A1", "label": "CITED"},
            "completion_date": {"value": "2026-01-10", "label": "CITED", "source": {"ada": "A1"}},
            "contractor": {"value": "Χ Α.Ε.", "label": "CITED"}, "amount_paid_eur": {"value": None, "label": "UNKNOWN"}}]
    new = [{"id": "W-1", "ada": {"value": "A1", "label": "CITED"},
            "completion_date": {"value": None, "label": "UNKNOWN"},
            "contractor": {"value": "Ψ Α.Ε.", "label": "CITED", "source": {"ada": "A9"}},
            "amount_paid_eur": {"value": 1000.0, "label": "CITED"}},
           {"id": "W-2", "ada": {"value": "A2", "label": "CITED"}}]
    merged, rep = stoa_ingest.merge_datasets(old, new, "2026-11-22")
    w1 = next(w for w in merged if w["id"] == "W-1")
    assert w1["completion_date"]["value"] == "2026-01-10"            # unknown never overwrites known
    assert w1["contractor"]["value"] == "Χ Α.Ε." and w1["contractor"]["conflicts"][0]["value"] == "Ψ Α.Ε."
    assert w1["amount_paid_eur"]["value"] == 1000.0                   # gaps are filled
    assert rep["added"] == ["W-2"] and rep["conflicts"] == {"W-1": ["contractor"]}
    assert guarantee.evaluate(w1, TODAY)["state"] == "REQUIRES_HUMAN_REVIEW"  # conflict blocks an ACTIVE verdict
