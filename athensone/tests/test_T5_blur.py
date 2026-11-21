"""Tests for T5: Better face blur (CenterFace via deface with OpenCV Haar fallback)."""
import importlib
import io
import os
import sys

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("VALHALLA_URL", "http://127.0.0.1:9")
os.environ.setdefault("WEATHER", "off")
os.environ.setdefault("CKAN_MODE", "off")

import numpy as np  # noqa: E402
import skimage.data as skdata  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import config, privacy  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)


def _face_jpeg(angle: float = 0.0, with_gps: bool = False) -> bytes:
    """Build a JPEG containing a real face image (bundled astronaut), optionally tilted and with EXIF GPS."""
    img = Image.fromarray(skdata.astronaut())
    if angle:
        img = img.rotate(angle)
    buf = io.BytesIO()
    if with_gps:
        exif = Image.Exif()
        exif[0x8825] = {1: "N", 2: (37, 58, 4.08), 3: "E", 4: (23, 44, 44.52)}
        img.save(buf, "JPEG", exif=exif)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def test_face_image_faces_ge_1():
    # Check that process_photo detects and counts at least one face on a tilted face photo (where Haar alone fails).
    out = privacy.process_photo(_face_jpeg(angle=25.0))
    assert out["faces"] >= 1


def test_deface_missing_falls_back(monkeypatch):
    # Check that when importing deface fails, process_photo falls back to the Haar _detect_faces path without error.
    calls = []
    try:
        with monkeypatch.context() as mp:
            mp.setitem(sys.modules, "deface", None)
            mp.setitem(sys.modules, "deface.centerface", None)
            importlib.reload(privacy)
            orig_detect = privacy._detect_faces

            def spy_detect(gray):
                res = orig_detect(gray)
                calls.append(len(res))
                return res

            mp.setattr(privacy, "_detect_faces", spy_detect)
            out = privacy.process_photo(_face_jpeg(angle=0.0))
    finally:
        importlib.reload(privacy)

    assert len(calls) >= 1
    assert out["faces"] >= 1


def test_original_never_on_disk():
    # Check that submitting a report with a face photo writes only a blurred, EXIF-free copy to data/photos/.
    from deface.centerface import CenterFace

    c.post("/api/admin/reset")
    before = set(config.PHOTO_DIR.iterdir())
    raw = _face_jpeg(angle=25.0, with_gps=True)
    new_files = []
    try:
        resp = c.post(
            "/api/report",
            files={"photo": ("face.jpg", raw, "image/jpeg")},
            data={"note": "σπασμένο πεζοδρόμιο"},
        )
        assert resp.status_code == 200
        assert resp.json()["faces_blurred"] >= 1
        new_files = [p for p in config.PHOTO_DIR.iterdir() if p not in before]
        assert len(new_files) == 1
        stored_bytes = new_files[0].read_bytes()
        assert stored_bytes != raw
        stored_img = Image.open(io.BytesIO(stored_bytes))
        assert 0x8825 not in stored_img.getexif()
        dets, _ = CenterFace()(np.array(stored_img.convert("RGB")))
        assert len(dets) == 0
    finally:
        for p in new_files:
            p.unlink(missing_ok=True)
