"""Comprehensive regression tests for Priorities 1–6:
- Multi-detector fail-closed face & Greek/EU licence-plate privacy pipeline (YuNet + CenterFace + EU plate)
- Greek & English neural TTS normalisation, voice routing, and English-on-Greek safety guard
- Greek, informal Greek, Greeklish, typo-tolerant & English NLU (vision.py + stoa_map.py + language.py)
- Operator authorisation (OPERATOR_KEY) & blurred map-report evidence linkage
"""
from __future__ import annotations

import io
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")
os.environ.setdefault("STOA_TODAY", "2026-11-21")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import skimage.data as skdata  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageEnhance  # noqa: E402

from app import config, language, privacy, stoa_map, tts, vision  # noqa: E402
from app.main import app  # noqa: E402


def _encode_bgr(bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", bgr)
    assert ok
    return buf.tobytes()


def _face_bytes(angle: float = 0.0, brightness: float = 1.0) -> bytes:
    img = Image.fromarray(skdata.astronaut())
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if angle:
        img = img.rotate(angle)
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _greek_plate_bytes(taxi: bool = False) -> bytes:
    canvas = np.full((420, 680, 3), (70, 78, 86), dtype=np.uint8)
    cv2.rectangle(canvas, (90, 110), (590, 330), (45, 50, 55), -1)
    x, y, w, h = 215, 210, 240, 52
    bg = (0, 215, 250) if taxi else (245, 245, 245)
    cv2.rectangle(canvas, (x, y), (x + w, y + h), bg, -1)
    cv2.rectangle(canvas, (x, y), (x + w, y + h), (20, 20, 20), 2)
    cv2.rectangle(canvas, (x + 1, y + 1), (x + 26, y + h - 1), (185, 65, 15), -1)
    cv2.putText(canvas, "GR", (x + 3, y + h - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (245, 245, 245), 1)
    cv2.putText(canvas, "IKB-4821", (x + 34, y + 39), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (15, 15, 15), 3)
    return _encode_bgr(canvas)


# ------------------------------------------------------------------ PRIORITY 1: Privacy Pipeline
def test_privacy_detects_tilted_lowlight_and_multiface_and_defeats_redetection():
    # Tilted -35 deg and low-light faces must both be detected and irreversibly anonymised.
    for raw in (_face_bytes(angle=-35.0), _face_bytes(brightness=0.35)):
        out = privacy.process_photo(raw)
        assert out["privacy_status"] == privacy.PRIVACY_PROCESSED
        assert out["faces"] >= 1
        assert "yunet" in out["detectors_used"]
        # Re-running YuNet on the anonymised output must detect 0 faces.
        arr = np.frombuffer(out["jpeg"], dtype=np.uint8)
        decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        assert len(privacy._detect_faces_yunet(decoded) or []) == 0


def test_privacy_detects_greek_white_and_taxi_yellow_plates():
    for taxi in (False, True):
        out = privacy.process_photo(_greek_plate_bytes(taxi=taxi))
        assert out["privacy_status"] == privacy.PRIVACY_PROCESSED
        assert out["plates"] >= 1
        assert "plate_eu_structural" in out["detectors_used"]


def test_privacy_marks_review_required_when_neural_detectors_unavailable(monkeypatch):
    monkeypatch.setattr(privacy, "_detect_faces_centerface", lambda _rgb: None)
    monkeypatch.setattr(privacy, "_detect_faces_yunet", lambda _bgr: None)
    out = privacy.process_photo(_face_bytes(angle=0.0))
    assert out["privacy_status"] == privacy.PRIVACY_REVIEW_REQUIRED
    assert "haar_face" in out["detectors_used"]
    assert out["faces"] >= 1


def test_privacy_fails_closed_when_all_detectors_crash(monkeypatch):
    monkeypatch.setattr(privacy, "_detect_faces_centerface", lambda _rgb: None)
    monkeypatch.setattr(privacy, "_detect_faces_yunet", lambda _bgr: None)

    def _boom(_gray):
        raise RuntimeError("detector crash")

    monkeypatch.setattr(privacy, "_detect_faces", _boom)

    with pytest.raises(privacy.PrivacyProcessingError) as exc:
        privacy.process_photo(_face_bytes())
    assert exc.value.status == privacy.PRIVACY_FAILED

    # Endpoint must fail closed (HTTP 503), write ZERO files to PHOTO_DIR, and never invoke vision AI.
    client = TestClient(app)
    client.post("/api/admin/reset")
    before = set(config.PHOTO_DIR.iterdir())
    vision_called = []
    monkeypatch.setattr(vision, "classify", lambda *a, **kw: vision_called.append(True))

    res = client.post(
        "/api/report",
        files={"photo": ("street.jpg", _face_bytes(), "image/jpeg")},
        data={"lat": 37.9755, "lng": 23.7348, "note": "δοκιμή"},
    )
    assert res.status_code == 503
    assert set(config.PHOTO_DIR.iterdir()) == before
    assert vision_called == []

    res_map = client.post(
        "/api/map/reports",
        files={"photo": ("street.jpg", _face_bytes(), "image/jpeg")},
        data={"category": "obstacle", "lon": 23.7348, "lat": 37.9755, "note": "δοκιμή"},
    )
    assert res_map.status_code == 503
    assert set(config.PHOTO_DIR.iterdir()) == before


def test_privacy_rejects_invalid_mime_type():
    with pytest.raises(privacy.PrivacyProcessingError) as exc:
        privacy.process_photo(b"<svg>bad</svg>", content_type="image/svg+xml")
    assert exc.value.code == "invalid_mime"


# ------------------------------------------------------------------ PRIORITY 2: Greek Neural TTS
def test_tts_language_detection_voice_routing_and_greek_normalisation():
    # Greek sentences, questions, dates, abbreviations, mixed Greek-English all route to el-GR-AthinaNeural.
    samples = [
        "Ποιο φαρμακείο εφημερεύει στην Πλ. Συντάγματος;",
        "Το έργο στη Λεωφ. Βασ. Σοφίας ολοκληρώθηκε στις 2026-11-21 με κόστος €15.000 (ΑΔΑ Ψ123-ΑΒΓ).",
        "Η διαδρομή Valhalla wheelchair έχει 62% σκιά, 21,5°C και AQI 28 (1,5 km).",
        "Αγ. Κωνσταντίνου, Δ.Κ. 1, π.χ. τηλ. 2105551234, σελ. 3, 21/11/2026.",
    ]
    for s in samples:
        loc, voice = tts.resolve_voice(s)
        assert loc == "el-GR"
        assert voice.startswith("el-GR-")

    # Safety guard: even if caller mistakenly passes lang="en" for Greek text, Greek voice is enforced!
    loc_guard, voice_guard = tts.resolve_voice("Καλημέρα Αθήνα, η ράμπα είναι κλειστή.", lang="en", voice="en-US-GuyNeural")
    assert loc_guard == "el-GR"
    assert voice_guard.startswith("el-GR-")

    # English-only text routes to English voice.
    loc_en, voice_en = tts.resolve_voice("The wheelchair route avoids active roadworks on Ermou Street.")
    assert loc_en == "en-US"
    assert voice_en.startswith("en-")

    # Speech normalisation preserves Greek Unicode + tonos and expands abbreviations/dates/units naturally.
    spoken = tts.normalize_for_speech(
        "Έργο στη Λεωφ. Βασ. Σοφίας (2026-11-21): €15.000, 62% σκιά, 21,5°C, 1,5 χλμ., ΑΔΑ Ψ123. [Πηγή](https://example.com)"
    )
    assert "Λεωφόρος" in spoken
    assert "Βασιλίσσης" in spoken
    assert "21 Νοεμβρίου 2026" in spoken
    assert "ευρώ" in spoken
    assert "τοις εκατό" in spoken
    assert "βαθμοί Κελσίου" in spoken
    assert "χιλιόμετρα" in spoken
    assert "Α Δ Α" in spoken
    assert "https://" not in spoken
    assert "ό" in spoken or "ά" in spoken  # tonos preserved, never transliterated to Latin!


def test_tts_endpoint_returns_audio_and_headers(monkeypatch):
    async def _fake_synth(text, lang=None, voice=None):
        loc, v = tts.resolve_voice(text, lang=lang, voice=voice)
        return tts.TTSResult(
            audio=b"ID3-FAKE-MP3-BYTES",
            media_type="audio/mpeg",
            provider="edge-tts",
            voice=v,
            locale=loc,
            normalized_text=tts.normalize_for_speech(text, loc),
        )

    monkeypatch.setattr(tts, "synthesize_speech", _fake_synth)
    client = TestClient(app)
    res = client.post("/api/tts", json={"text": "Καλημέρα Αθήνα, πού είναι το πλησιέστερο φαρμακείο;"})
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/mpeg"
    assert res.headers["x-tts-lang"] == "el-GR"
    assert res.headers["x-tts-voice"].startswith("el-GR-")
    assert res.content == b"ID3-FAKE-MP3-BYTES"


# ------------------------------------------------------------------ PRIORITY 3: Greek / Greeklish / English NLU
def test_nlu_understands_greek_greeklish_typos_and_english_reports():
    # Greeklish pothole report
    r_gl = vision.classify(b"fake", "Megali lakouva stin Ermou, poly epikindino")
    assert r_gl["category"] == "pothole"
    assert r_gl["interpretation"]["original_note"] == "Megali lakouva stin Ermou, poly epikindino"
    assert r_gl["interpretation"]["provenance"] == "AI-GENERATED"
    assert r_gl["interpretation"]["verified"] is False
    assert r_gl["interpretation"]["location_hint"] == "ερμου"

    # Greek spelling mistake ("πεζωδρομιο" instead of "πεζοδρόμιο")
    r_typo = vision.classify(b"fake", "Σπασμένο πεζωδρομιο με εμποδιο")
    assert r_typo["category"] == "sidewalk"
    assert r_typo["accessibility_blocker"] is True

    # English water leak report -> English polite draft reply, never claiming dispatch
    r_en = vision.classify(b"fake", "Huge water leak near Syntagma square")
    assert r_en["category"] == "water_leak"
    assert r_en["detected_language"] == "en"
    assert "awaiting" in r_en["draft_reply_el"].lower()
    assert "dispatched" not in r_en["draft_reply_el"].lower()

    # Stoa understands both Greeklish and English on-duty pharmacy queries
    fake_onduty = [
        {"kind": "φαρμακείο", "name": "Φαρμακείο Συντάγματος", "address": "Ερμού 10", "on_duty": True, "lon": 23.734, "lat": 37.975}
    ]
    orig = stoa_map.onduty_provider
    stoa_map.onduty_provider = lambda: fake_onduty
    try:
        res_gl = stoa_map.answer("poio farmakeio efimerevei?", [23.7348, 37.9755])
        assert "Φαρμακείο Συντάγματος" in res_gl["answer_md"]
        assert res_gl["language"] == "el"

        res_en = stoa_map.answer("Which pharmacy is on duty near me?", [23.7348, 37.9755])
        assert "On-duty nearby:" in res_en["answer_md"]
        assert "Φαρμακείο Συντάγματος" in res_en["answer_md"]
        assert res_en["language"] == "en"
    finally:
        stoa_map.onduty_provider = orig


# ------------------------------------------------------------------ PRIORITY 4–6: Security & Evidence Linkage
def test_operator_key_guard_and_map_report_photo_linkage(monkeypatch):
    client = TestClient(app)
    client.post("/api/admin/reset")
    before = set(config.PHOTO_DIR.iterdir())
    try:
        sub = client.post(
            "/api/map/reports",
            data={"category": "obstacle", "lon": 23.7348, "lat": 37.9755, "note": "Κάδος στη ράμπα"},
            files={"photo": ("obs.jpg", _face_bytes(), "image/jpeg")},
        )
        assert sub.status_code == 200
        body = sub.json()
        cid = body["city_request_id"]
        assert cid
        assert body["privacy_status"] == privacy.PRIVACY_PROCESSED

        # Operator queue receives the linked map_report blurred photo and privacy_status.
        ops = client.get("/api/reports").json()["items"]
        ticket = next(x for x in ops if x["id"] == cid)
        assert ticket["photo_url"] == body["photo_url_blurred"]
        assert ticket["map_report"]["privacy_status"] == privacy.PRIVACY_PROCESSED

        # When OPERATOR_KEY is configured, operator endpoints reject unauthorised callers with 403.
        monkeypatch.setenv("OPERATOR_KEY", "municipality-secret-key")
        assert client.post(f"/api/reports/{cid}/approve").status_code == 403
        assert client.post(f"/api/reports/{cid}/approve", headers={"X-Operator-Key": "wrong"}).status_code == 403
        assert client.post(f"/api/reports/{cid}/approve", headers={"X-Operator-Key": "municipality-secret-key"}).status_code == 200
    finally:
        for p in set(config.PHOTO_DIR.iterdir()) - before:
            p.unlink(missing_ok=True)
