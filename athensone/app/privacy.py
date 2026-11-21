"""Privacy proxy: runs BEFORE a photo is stored or sent to any AI model.

1. Reads GPS from EXIF (to drop the map pin automatically, FixMyStreet-style).
2. Blurs faces: CenterFace through 'deface' (MIT) first, OpenCV Haar cascades (frontal + profile)
   as the fallback when deface is missing or fails (T5).
3. Re-encodes the image as JPEG WITHOUT any EXIF (location, phone model, time are gone).

Licence plates: not detected in this prototype (deface does faces only). Production path:
an open plate detector at the same step.
"""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageOps

_FRONT = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_PROFILE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
if _FRONT.empty() or _PROFILE.empty():
    # Privacy is a hard requirement: refuse to start rather than store unblurred faces.
    raise RuntimeError("OpenCV face models not found. Install opencv-python-headless 4.x "
                       "(pip install 'opencv-python-headless>=4.9,<5').")
MAX_SIDE = 1600


def _dms_to_deg(dms, ref):
    d, m, s = (float(x) for x in dms)
    deg = d + m / 60 + s / 3600
    return -deg if ref in ("S", "W") else deg


def read_gps(img: Image.Image):
    """Return (lat, lng) from EXIF, or None."""
    try:
        gps = img.getexif().get_ifd(0x8825)
        if not gps or 2 not in gps or 4 not in gps:
            return None
        return round(_dms_to_deg(gps[2], gps.get(1, "N")), 6), round(_dms_to_deg(gps[4], gps.get(3, "E")), 6)
    except Exception:
        return None


def _detect_faces(gray):
    boxes = []
    for casc in (_FRONT, _PROFILE):
        found = casc.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
        boxes.extend([tuple(map(int, b)) for b in found])
    # profile faces looking the other way: run on the mirrored image
    flipped = cv2.flip(gray, 1)
    w = gray.shape[1]
    for (x, y, bw, bh) in _PROFILE.detectMultiScale(flipped, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)):
        boxes.append((int(w - x - bw), int(y), int(bw), int(bh)))
    return boxes


# --- T5: Better face blur ---
# CenterFace detection threshold: 0.2 matches deface 1.5.0 CLI `--thresh` default
# (deface/deface.py); verified locally in the installed deface 1.5.0 package.
CENTERFACE_THRESHOLD = 0.2


def _detect_faces_centerface(rgb: np.ndarray) -> list[tuple[int, int, int, int]] | None:
    """Detect faces with deface's CenterFace (uses cv2.dnn when onnxruntime is absent).

    Returns (x, y, w, h) boxes, or None if deface is unavailable or fails so the caller
    falls back to the OpenCV Haar cascade.
    """
    try:
        from deface.centerface import CenterFace

        # Fresh instance per photo (same as deface.image_detect): reusing a single
        # cv2.dnn Net across varying image shapes corrupts detections on OpenCV 4.14.
        detector = CenterFace(in_shape=None, backend="auto")
        dets, _ = detector(rgb, threshold=CENTERFACE_THRESHOLD)
    except Exception:
        return None
    h_img, w_img = rgb.shape[:2]
    boxes: list[tuple[int, int, int, int]] = []
    for det in dets:
        x0 = max(0, min(w_img, int(round(float(det[0])))))
        y0 = max(0, min(h_img, int(round(float(det[1])))))
        x1 = max(0, min(w_img, int(round(float(det[2])))))
        y1 = max(0, min(h_img, int(round(float(det[3])))))
        if x1 > x0 and y1 > y0:
            boxes.append((x0, y0, x1 - x0, y1 - y0))
    return boxes
# --- end T5 ---


def process_photo(raw: bytes):
    """Return dict(jpeg=bytes, gps=(lat,lng)|None, faces=int, width, height)."""
    img = Image.open(io.BytesIO(raw))
    gps = read_gps(img)
    img = ImageOps.exif_transpose(img).convert("RGB")  # apply rotation, then drop EXIF
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    # --- T5: Better face blur ---
    rgb = np.array(img)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    faces = _detect_faces_centerface(rgb)
    if faces is None:
        gray = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
        faces = _detect_faces(gray)
    # --- end T5 ---
    for (x, y, w, h) in faces:
        pad = int(0.25 * max(w, h))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(bgr.shape[1], x + w + pad), min(bgr.shape[0], y + h + pad)
        roi = bgr[y0:y1, x0:x1]
        k = max(31, (min(roi.shape[:2]) // 2) | 1)
        bgr[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (k, k), 0)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])  # cv2 writes no EXIF
    if not ok:
        raise ValueError("could not encode image")
    return {"jpeg": buf.tobytes(), "gps": gps, "faces": len(faces), "width": bgr.shape[1], "height": bgr.shape[0]}
