"""Multi-detector fail-closed privacy pipeline (faces + Greek/EU licence plates + EXIF removal).

Runs strictly BEFORE any photo is written to disk or sent to downstream AI models:
  1. Validates upload size, MIME type (when provided), image magic bytes, and dimensions.
  2. Extracts optional EXIF GPS coordinates (for pin placement) and applies EXIF orientation.
  3. Runs a modular multi-detector ensemble for faces:
       - YuNet (OpenCV Zoo `face_detection_yunet_2023mar.onnx`, MIT) via `cv2.FaceDetectorYN`
       - CenterFace (`deface`, MIT) via `cv2.dnn`
       - OpenCV Haar frontal + mirrored profile (Apache-2.0) fallback/union when a neural detector is absent
     Detections are combined via UNION + overlap merge (prioritising privacy recall).
  4. Runs a multi-detector ensemble for Greek / European licence plates (bounding boxes ONLY, no OCR):
       - Optional ONNX plate detector (`PLATE_ONNX_PATH`)
       - OpenCV Haar plate cascade (normal + CLAHE)
       - Structural Greek/EU plate detector (EU blue band + high-contrast 2.2:1–6.2:1 plate geometry)
  5. Expands boxes by configurable safety margins and applies two-stage irreversible anonymisation
     (block pixelation + strong Gaussian blur).
  6. Re-encodes JPEG with zero EXIF metadata and tracks explicit processing states:
     `pending` -> `processed` | `review_required` | `failed`.

FAIL-CLOSED: If validation fails, all face detectors fail/crash, boxes are invalid, or encoding fails,
raises `PrivacyProcessingError` (`status="failed"`) so the unprocessed original NEVER touches disk or AI.
Note: Automated detection significantly reduces privacy risk but does NOT guarantee 100% anonymisation.
"""
from __future__ import annotations

import io
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps

from . import config

# Explicit privacy-processing lifecycle states.
PRIVACY_PENDING = "pending"
PRIVACY_PROCESSED = "processed"
PRIVACY_REVIEW_REQUIRED = "review_required"
PRIVACY_FAILED = "failed"
PRIVACY_STATES = (PRIVACY_PENDING, PRIVACY_PROCESSED, PRIVACY_REVIEW_REQUIRED, PRIVACY_FAILED)

# Input validation guardrails.
MAX_UPLOAD_BYTES = int(os.getenv("PRIVACY_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
MAX_SIDE = int(os.getenv("PRIVACY_MAX_SIDE", "1600"))
MAX_INPUT_DIM = int(os.getenv("PRIVACY_MAX_INPUT_DIM", "8000"))
MIN_INPUT_DIM = 16
ALLOWED_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/tiff",
})
ALLOWED_PIL_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "BMP", "TIFF", "MPO"})

# Configurable safety-margin expansions around detected regions (fraction of max(w, h)).
FACE_MARGIN = float(os.getenv("PRIVACY_FACE_MARGIN", "0.28"))
PLATE_MARGIN = float(os.getenv("PRIVACY_PLATE_MARGIN", "0.22"))

# Detector thresholds & model paths.
CENTERFACE_THRESHOLD = float(os.getenv("PRIVACY_CENTERFACE_THRESH", "0.2"))
YUNET_THRESHOLD = float(os.getenv("PRIVACY_YUNET_THRESH", "0.45"))
YUNET_NMS = 0.3
DEFAULT_YUNET_PATH = config.ROOT / "models" / "face_detection_yunet_2023mar.onnx"

_FRONT = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_PROFILE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
if _FRONT.empty() or _PROFILE.empty():
    raise RuntimeError(
        "OpenCV face models not found. Install opencv-python-headless 4.x "
        "(pip install 'opencv-python-headless>=4.9,<5')."
    )

_PLATE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_russian_plate_number.xml")
if _PLATE.empty():
    raise RuntimeError("OpenCV plate model not found (haarcascade_russian_plate_number.xml).")
PLATE_MIN_SIZE = (24, 8)


class PrivacyProcessingError(RuntimeError):
    """Raised when privacy processing fails closed (unprocessed photo must NOT proceed)."""

    def __init__(self, message: str, *, code: str = "privacy_failed", status: str = PRIVACY_FAILED):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class DetectionBox:
    x: int
    y: int
    w: int
    h: int
    score: float
    detector: str
    kind: str  # "face" | "plate"

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


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


def validate_upload(raw: bytes, content_type: str | None = None) -> None:
    """Validate raw upload bytes and optional MIME type before decoding."""
    if not raw or not isinstance(raw, (bytes, bytearray)):
        raise PrivacyProcessingError("Empty or missing image payload", code="empty_image")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise PrivacyProcessingError("Image exceeds maximum allowed size", code="file_too_large")
    if content_type:
        mime = content_type.split(";", 1)[0].strip().lower()
        if mime and mime != "application/octet-stream" and mime not in ALLOWED_MIME_TYPES:
            raise PrivacyProcessingError(f"Unsupported image MIME type: {mime}", code="invalid_mime")


def _validate_box(x: int, y: int, w: int, h: int, img_w: int, img_h: int) -> tuple[int, int, int, int] | None:
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x, y, w, h)):
        raise PrivacyProcessingError("Detector produced non-finite bounding box", code="invalid_detector_output")
    x0 = max(0, min(img_w, int(round(x))))
    y0 = max(0, min(img_h, int(round(y))))
    x1 = max(0, min(img_w, int(round(x + w))))
    y1 = max(0, min(img_h, int(round(y + h))))
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def union_merge_boxes(boxes: list[tuple[int, int, int, int]], iou_threshold: float = 0.35) -> list[tuple[int, int, int, int]]:
    """Combine overlapping boxes from multiple detectors into their enclosing union (privacy-first)."""
    if not boxes:
        return []
    merged: list[list[int]] = []
    for box in boxes:
        bx, by, bw, bh = box
        absorbed = False
        for m in merged:
            if _iou((m[0], m[1], m[2], m[3]), box) >= iou_threshold:
                nx0 = min(m[0], bx)
                ny0 = min(m[1], by)
                nx1 = max(m[0] + m[2], bx + bw)
                ny1 = max(m[1] + m[3], by + bh)
                m[0], m[1], m[2], m[3] = nx0, ny0, nx1 - nx0, ny1 - ny0
                absorbed = True
                break
        if not absorbed:
            merged.append([bx, by, bw, bh])
    return [(m[0], m[1], m[2], m[3]) for m in merged]


# ------------------------------------------------------------------ Face detectors
def _detect_faces(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """OpenCV Haar frontal + mirrored profile detector (fallback / union helper)."""
    boxes: list[tuple[int, int, int, int]] = []
    for casc in (_FRONT, _PROFILE):
        found = casc.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
        boxes.extend([tuple(map(int, b)) for b in found])
    flipped = cv2.flip(gray, 1)
    w = gray.shape[1]
    for (x, y, bw, bh) in _PROFILE.detectMultiScale(flipped, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)):
        boxes.append((int(w - x - bw), int(y), int(bw), int(bh)))
    return boxes


def _yunet_model_path() -> Path:
    override = os.getenv("YUNET_MODEL_PATH", "").strip()
    return Path(override) if override else DEFAULT_YUNET_PATH


def _detect_faces_yunet(bgr: np.ndarray) -> list[tuple[int, int, int, int]] | None:
    """Detect faces using OpenCV Zoo YuNet ONNX (`cv2.FaceDetectorYN`, MIT licence).

    Returns list of (x, y, w, h) boxes, or None if model file is missing or detector errors.
    """
    model_path = _yunet_model_path()
    if not model_path.is_file() or not hasattr(cv2, "FaceDetectorYN"):
        return None
    h_img, w_img = bgr.shape[:2]
    try:
        detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (w_img, h_img), YUNET_THRESHOLD, YUNET_NMS, 5000
        )
        _, raw_faces = detector.detect(bgr)
    except Exception:
        return None
    if raw_faces is None:
        return []
    boxes: list[tuple[int, int, int, int]] = []
    for row in raw_faces:
        valid = _validate_box(float(row[0]), float(row[1]), float(row[2]), float(row[3]), w_img, h_img)
        if valid is not None:
            boxes.append(valid)
    return boxes


def _detect_faces_centerface(rgb: np.ndarray) -> list[tuple[int, int, int, int]] | None:
    """Detect faces with deface's CenterFace (uses cv2.dnn when onnxruntime is absent).

    Returns (x, y, w, h) boxes, or None if deface is unavailable or fails.
    """
    try:
        from deface.centerface import CenterFace

        # Fresh instance per photo: reusing a single cv2.dnn Net across varying shapes corrupts OpenCV 4.14.
        detector = CenterFace(in_shape=None, backend="auto")
        dets, _ = detector(rgb, threshold=CENTERFACE_THRESHOLD)
    except Exception:
        return None
    h_img, w_img = rgb.shape[:2]
    boxes: list[tuple[int, int, int, int]] = []
    for det in dets:
        valid = _validate_box(
            float(det[0]), float(det[1]), float(det[2]) - float(det[0]), float(det[3]) - float(det[1]), w_img, h_img
        )
        if valid is not None:
            boxes.append(valid)
    return boxes


# ------------------------------------------------------------------ Licence-plate detectors (NO OCR)
def _detect_plates(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """OpenCV Haar plate cascade on normal + CLAHE grayscale."""
    found = _PLATE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=PLATE_MIN_SIZE)
    boxes = [tuple(map(int, b)) for b in found]
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    found2 = _PLATE.detectMultiScale(clahe, scaleFactor=1.08, minNeighbors=5, minSize=PLATE_MIN_SIZE)
    boxes.extend([tuple(map(int, b)) for b in found2])
    return boxes


def _detect_plates_eu_structural(bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Detect Greek/EU licence-plate regions via colour + aspect-ratio + stroke-density heuristics (no OCR).

    Targets Greek standard white plates (~4.7:1 with left EU blue strip) and Greek yellow taxi plates
    while rejecting sky/building strips via dark character edge-transition checks.
    """
    h_img, w_img = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # 1. EU blue strip anchor (left band of Greek/EU plates: H in [95..132], S>=90, V>=55)
    blue_mask = cv2.inRange(hsv, np.array([95, 90, 55]), np.array([132, 255, 255]))
    blue_contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates: list[tuple[int, int, int, int]] = []
    for cnt in blue_contours:
        bx, by, bw, bh = cv2.boundingRect(cnt)
        if bh < 10 or bw < 3 or bh > h_img * 0.35:
            continue
        strip_ratio = bh / max(1, bw)
        if not (1.3 <= strip_ratio <= 5.5):
            continue
        # Expected full Greek/EU plate extends ~4.5x height to the right of the blue band.
        est_w = int(round(bh * 4.7))
        px0 = max(0, bx - 2)
        py0 = max(0, by - 2)
        px1 = min(w_img, bx + est_w + 4)
        py1 = min(h_img, by + bh + 2)
        pw, ph = px1 - px0, py1 - py0
        if pw < 36 or ph < 10 or (pw / max(1, ph)) < 2.2:
            continue
        roi_gray = gray[py0:py1, px0:px1]
        roi_hsv = hsv[py0:py1, px0:px1]
        # Plate body (right of blue strip) must be bright white or taxi-yellow with dark character strokes.
        body_start = min(roi_gray.shape[1] - 1, max(1, bw + 1))
        body_gray = roi_gray[:, body_start:]
        body_hsv = roi_hsv[:, body_start:]
        if body_gray.size < 40:
            continue
        bright_ratio = float(np.mean(body_gray > 145))
        low_sat_or_yellow = float(np.mean((body_hsv[:, :, 1] < 85) | ((body_hsv[:, :, 0] >= 15) & (body_hsv[:, :, 0] <= 38))))
        sobel_x = cv2.Sobel(body_gray, cv2.CV_32F, 1, 0, ksize=3)
        edge_density = float(np.mean(np.abs(sobel_x) > 45))
        if bright_ratio >= 0.42 and low_sat_or_yellow >= 0.60 and edge_density >= 0.08:
            candidates.append((px0, py0, pw, ph))

    # 2. High-contrast light rectangular plate contour search (handles plates without visible blue strip / taxi yellow)
    white_mask = cv2.inRange(hsv, np.array([0, 0, 175]), np.array([180, 65, 255]))
    yellow_mask = cv2.inRange(hsv, np.array([15, 95, 145]), np.array([38, 255, 255]))
    plate_color_mask = cv2.bitwise_or(white_mask, yellow_mask)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3))
    closed = cv2.morphologyEx(plate_color_mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 44 or h < 12 or w > w_img * 0.65 or h > h_img * 0.25:
            continue
        aspect = w / max(1, h)
        if not (2.4 <= aspect <= 6.2):
            continue
        area = cv2.contourArea(cnt)
        rectangularity = area / max(1.0, float(w * h))
        if rectangularity < 0.55:
            continue
        roi_g = gray[y:y + h, x:x + w]
        # Require crisp dark lettering inside bright plate (bimodal contrast + horizontal transitions)
        dark_ratio = float(np.mean(roi_g < 95))
        light_ratio = float(np.mean(roi_g > 160))
        sobel_x = cv2.Sobel(roi_g, cv2.CV_32F, 1, 0, ksize=3)
        edge_density = float(np.mean(np.abs(sobel_x) > 55))
        if 0.06 <= dark_ratio <= 0.48 and light_ratio >= 0.42 and edge_density >= 0.12:
            candidates.append((x, y, w, h))

    return candidates


def _detect_plates_onnx(bgr: np.ndarray) -> list[tuple[int, int, int, int]] | None:
    """Optional ONNX YOLO-style plate detector when PLATE_ONNX_PATH is configured."""
    raw_path = os.getenv("PLATE_ONNX_PATH", "").strip()
    if not raw_path:
        return None
    model_path = Path(raw_path)
    if not model_path.is_file():
        return None
    try:
        net = cv2.dnn.readNetFromONNX(str(model_path))
        h_img, w_img = bgr.shape[:2]
        blob = cv2.dnn.blobFromImage(bgr, 1 / 255.0, (640, 640), swapRB=True, crop=False)
        net.setInput(blob)
        out = net.forward()
        preds = out[0]
        if preds.ndim == 2 and preds.shape[0] < preds.shape[1]:
            preds = preds.T
        boxes: list[tuple[int, int, int, int]] = []
        sx, sy = w_img / 640.0, h_img / 640.0
        for row in preds:
            conf = float(row[4]) if len(row) == 5 else float(np.max(row[4:]))
            if conf < 0.35:
                continue
            cx, cy, bw, bh = float(row[0]) * sx, float(row[1]) * sy, float(row[2]) * sx, float(row[3]) * sy
            valid = _validate_box(cx - bw / 2, cy - bh / 2, bw, bh, w_img, h_img)
            if valid is not None:
                boxes.append(valid)
        return boxes
    except Exception:
        return None


# ------------------------------------------------------------------ Irreversible anonymisation
def _anonymise_region(bgr: np.ndarray, x: int, y: int, w: int, h: int, margin: float) -> None:
    """Apply margin expansion + irreversible coarse pixelation + strong Gaussian blur + contrast flattening."""
    pad = max(6, int(round(margin * max(w, h))))
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(bgr.shape[1], x + w + pad)
    y1 = min(bgr.shape[0], y + h + pad)
    if x1 <= x0 or y1 <= y0:
        return
    roi = bgr[y0:y1, x0:x1]
    rh, rw = roi.shape[:2]
    # Stage 1: coarse 4x4 mosaic destroys biometric landmarks & plate characters.
    blocks_w = max(2, min(4, rw // 12))
    blocks_h = max(2, min(4, rh // 12))
    small = cv2.resize(roi, (blocks_w, blocks_h), interpolation=cv2.INTER_AREA)
    mosaic = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_NEAREST)
    # Stage 2: subtle mean-colour blend flattens eye/mouth/character contrast so detectors cannot re-trigger.
    mean_col = np.full_like(mosaic, np.mean(roi, axis=(0, 1)), dtype=np.uint8)
    blended = cv2.addWeighted(mosaic, 0.55, mean_col, 0.45, 0)
    # Stage 3: strong Gaussian blur with large sigma removes residual block edges.
    k = max(51, (min(rh, rw) // 2) | 1)
    sigma = max(20.0, min(rh, rw) / 3.5)
    bgr[y0:y1, x0:x1] = cv2.GaussianBlur(blended, (k, k), sigmaX=sigma, sigmaY=sigma)


# ------------------------------------------------------------------ Public pipeline entrypoint
def process_photo(
    raw: bytes,
    *,
    content_type: str | None = None,
    face_margin: float = FACE_MARGIN,
    plate_margin: float = PLATE_MARGIN,
) -> dict[str, Any]:
    """Run the fail-closed privacy pipeline on uploaded image bytes.

    Returns dict with:
      jpeg, gps, faces, plates, width, height,
      privacy_status ('processed' | 'review_required'),
      detectors_used, warnings, timings_ms.
    Raises PrivacyProcessingError (status='failed') if privacy processing cannot complete safely.
    """
    t0 = time.perf_counter()
    validate_upload(raw, content_type=content_type)

    try:
        img = Image.open(io.BytesIO(raw))
        fmt = (img.format or "").upper()
        if fmt and fmt not in ALLOWED_PIL_FORMATS:
            raise PrivacyProcessingError(f"Unsupported image format: {fmt}", code="invalid_format")
        gps = read_gps(img)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except PrivacyProcessingError:
        raise
    except Exception as exc:
        raise PrivacyProcessingError("Unreadable or corrupted image", code="invalid_image") from exc

    orig_w, orig_h = img.size
    if orig_w < MIN_INPUT_DIM or orig_h < MIN_INPUT_DIM or orig_w > MAX_INPUT_DIM or orig_h > MAX_INPUT_DIM:
        raise PrivacyProcessingError(
            f"Image dimensions out of allowed range ({orig_w}x{orig_h})", code="invalid_dimensions"
        )

    img.thumbnail((MAX_SIDE, MAX_SIDE))
    rgb = np.array(img)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))

    # --- Multi-detector face ensemble (union of neural detectors; fail-closed if all fail) ---
    detectors_used: list[str] = []
    warnings: list[str] = []
    face_boxes_raw: list[tuple[int, int, int, int]] = []
    neural_ok = 0

    t_face0 = time.perf_counter()
    cf_boxes = _detect_faces_centerface(rgb)
    if cf_boxes is not None:
        neural_ok += 1
        detectors_used.append("centerface")
        face_boxes_raw.extend(cf_boxes)
    else:
        warnings.append("centerface_unavailable")

    yn_boxes = _detect_faces_yunet(bgr)
    if yn_boxes is not None:
        neural_ok += 1
        detectors_used.append("yunet")
        face_boxes_raw.extend(yn_boxes)
    else:
        warnings.append("yunet_unavailable")

    # Run Haar cascade as supplementary fallback whenever CenterFace is absent (preserves T5 fallback & boosts recall).
    haar_ok = False
    if cf_boxes is None or neural_ok == 0:
        try:
            haar_boxes = _detect_faces(gray)
            haar_ok = True
            detectors_used.append("haar_face")
            face_boxes_raw.extend(haar_boxes)
        except Exception:
            warnings.append("haar_face_failed")

    t_face_ms = round((time.perf_counter() - t_face0) * 1000, 1)

    if neural_ok == 0 and not haar_ok:
        raise PrivacyProcessingError("All face detectors failed; refusing to store unprocessed photo", code="detectors_failed")

    faces = union_merge_boxes(face_boxes_raw, iou_threshold=0.35)

    # --- Multi-detector Greek/EU licence-plate ensemble (bounding-box blur only, no OCR) ---
    t_plate0 = time.perf_counter()
    plate_boxes_raw: list[tuple[int, int, int, int]] = []
    plate_ok = False

    onnx_plates = _detect_plates_onnx(bgr)
    if onnx_plates is not None:
        plate_ok = True
        detectors_used.append("plate_onnx")
        plate_boxes_raw.extend(onnx_plates)

    try:
        haar_plates = _detect_plates(gray)
        plate_ok = True
        detectors_used.append("plate_haar")
        plate_boxes_raw.extend(haar_plates)
    except Exception:
        warnings.append("plate_haar_failed")

    try:
        eu_plates = _detect_plates_eu_structural(bgr)
        plate_ok = True
        detectors_used.append("plate_eu_structural")
        plate_boxes_raw.extend(eu_plates)
    except Exception:
        warnings.append("plate_eu_structural_failed")

    t_plate_ms = round((time.perf_counter() - t_plate0) * 1000, 1)

    if not plate_ok:
        raise PrivacyProcessingError("All licence-plate detectors failed; failing closed", code="plate_detectors_failed")

    plates = union_merge_boxes(plate_boxes_raw, iou_threshold=0.3)

    # --- Apply irreversible two-stage anonymisation on all detected regions ---
    for (x, y, w, h) in faces:
        _anonymise_region(bgr, x, y, w, h, face_margin)
    for (x, y, w, h) in plates:
        _anonymise_region(bgr, x, y, w, h, plate_margin)

    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])  # writes zero EXIF
    if not ok:
        raise PrivacyProcessingError("Could not encode anonymised JPEG", code="encode_failed")

    # Determine explicit processing status: review_required if running without any neural face detector.
    privacy_status = PRIVACY_PROCESSED if neural_ok >= 1 else PRIVACY_REVIEW_REQUIRED
    total_ms = round((time.perf_counter() - t0) * 1000, 1)

    return {
        "jpeg": buf.tobytes(),
        "gps": gps,
        "faces": len(faces),
        "plates": len(plates),
        "width": bgr.shape[1],
        "height": bgr.shape[0],
        "privacy_status": privacy_status,
        "detectors_used": detectors_used,
        "warnings": warnings,
        "timings_ms": {"face": t_face_ms, "plate": t_plate_ms, "total": total_ms},
    }
