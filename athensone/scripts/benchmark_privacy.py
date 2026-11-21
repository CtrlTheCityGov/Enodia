"""Benchmark face & Greek/EU licence-plate detectors across realistic street-photo conditions.

Usage:
    .venv/Scripts/python.exe scripts/benchmark_privacy.py
"""
from __future__ import annotations

import io
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
import skimage.data as skdata
from PIL import Image, ImageEnhance

from app import privacy


def _to_bgr(pil_img: Image.Image) -> np.ndarray:
    rgb = np.array(pil_img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _draw_greek_plate(canvas: np.ndarray, x: int, y: int, w: int, h: int, text: str = "IKB-4821", taxi: bool = False) -> tuple[int, int, int, int]:
    """Draw a synthetic Greek/EU plate (white standard or yellow taxi with EU blue left strip)."""
    bg = (0, 215, 250) if taxi else (245, 245, 245)
    cv2.rectangle(canvas, (x, y), (x + w, y + h), bg, -1)
    cv2.rectangle(canvas, (x, y), (x + w, y + h), (25, 25, 25), 2)
    blue_w = max(8, int(w * 0.11))
    cv2.rectangle(canvas, (x + 1, y + 1), (x + blue_w, y + h - 1), (185, 65, 15), -1)
    cv2.putText(canvas, "GR", (x + 2, y + h - 4), cv2.FONT_HERSHEY_SIMPLEX, max(0.25, h / 60), (245, 245, 245), 1)
    font_scale = max(0.45, h / 32.0)
    cv2.putText(
        canvas,
        text,
        (x + blue_w + max(4, w // 24), y + int(h * 0.76)),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (15, 15, 15),
        max(2, int(h / 16)),
    )
    return (x, y, w, h)


def _make_face_suite() -> list[tuple[str, np.ndarray, int]]:
    """Build reproducible test scenes using skimage.data.astronaut (CC0/NASA public domain)."""
    base = Image.fromarray(skdata.astronaut())
    scenes: list[tuple[str, np.ndarray, int]] = []

    # 1. Frontal face
    scenes.append(("frontal_512", _to_bgr(base), 1))
    # 2. Tilted 25 deg
    scenes.append(("tilted_25deg", _to_bgr(base.rotate(25)), 1))
    # 3. Tilted -35 deg
    scenes.append(("tilted_neg35deg", _to_bgr(base.rotate(-35)), 1))
    # 4. Small / distant face pasted into 1024x768 street canvas
    street = np.full((768, 1024, 3), (110, 118, 125), dtype=np.uint8)
    small = _to_bgr(base.resize((120, 120)))
    street[180:300, 420:540] = small
    scenes.append(("small_distant_1024", street, 1))
    # 5. Multi-person (3 faces at different scales & angles)
    crowd = np.full((720, 1280, 3), (95, 102, 110), dtype=np.uint8)
    crowd[80:380, 60:360] = _to_bgr(base.resize((300, 300)))
    crowd[140:380, 480:720] = _to_bgr(base.rotate(20).resize((240, 240)))
    crowd[200:380, 880:1060] = _to_bgr(base.rotate(-20).resize((180, 180)))
    scenes.append(("multi_person_3", crowd, 3))
    # 6. Low-light condition (brightness 0.35)
    dark = ImageEnhance.Brightness(base).enhance(0.35)
    scenes.append(("low_light_0.35", _to_bgr(dark), 1))
    # 7. High-resolution 1600px scene
    hi = _to_bgr(base.resize((1200, 1200)))
    scenes.append(("high_res_1200", hi, 1))
    # 8. Partially occluded lower face (surgical mask / scarf bar)
    occ = _to_bgr(base).copy()
    cv2.rectangle(occ, (150, 125), (275, 185), (210, 225, 235), -1)
    scenes.append(("partially_obscured", occ, 1))
    # 9. Sunglasses occlusion over eyes
    glasses = _to_bgr(base).copy()
    cv2.rectangle(glasses, (175, 72), (255, 98), (20, 20, 25), -1)
    scenes.append(("dark_glasses", glasses, 1))
    # 10. Negative (no face, plain street background)
    neg = np.full((480, 640, 3), (125, 130, 135), dtype=np.uint8)
    cv2.rectangle(neg, (40, 260), (600, 440), (90, 95, 100), -1)
    scenes.append(("negative_no_face", neg, 0))
    return scenes


def _make_plate_suite() -> list[tuple[str, np.ndarray, int]]:
    scenes: list[tuple[str, np.ndarray, int]] = []
    # 1. Standard Greek EU white plate on bumper
    s1 = np.full((420, 680, 3), (75, 82, 90), dtype=np.uint8)
    cv2.rectangle(s1, (90, 110), (590, 330), (45, 50, 55), -1)
    _draw_greek_plate(s1, 220, 210, 235, 50, "IKB-4821", taxi=False)
    scenes.append(("greek_white_eu_plate", s1, 1))

    # 2. Athens yellow taxi plate with EU strip
    s2 = np.full((420, 680, 3), (85, 90, 95), dtype=np.uint8)
    cv2.rectangle(s2, (90, 110), (590, 330), (20, 175, 220), -1)
    _draw_greek_plate(s2, 215, 215, 240, 52, "TAA-7319", taxi=True)
    scenes.append(("greek_taxi_yellow_plate", s2, 1))

    # 3. Combined person + car with Greek plate
    s3 = np.full((600, 900, 3), (100, 108, 115), dtype=np.uint8)
    s3[60:360, 40:340] = _to_bgr(Image.fromarray(skdata.astronaut()).resize((300, 300)))
    cv2.rectangle(s3, (400, 220), (850, 490), (55, 58, 62), -1)
    _draw_greek_plate(s3, 510, 360, 220, 48, "YHN-2094", taxi=False)
    scenes.append(("person_plus_greek_plate", s3, 1))

    # 4. Negative (no plate)
    s4 = np.full((420, 680, 3), (120, 125, 130), dtype=np.uint8)
    scenes.append(("negative_no_plate", s4, 0))
    return scenes


def run_benchmark() -> None:
    face_scenes = _make_face_suite()
    methods = {
        "haar_only": lambda bgr: privacy._detect_faces(cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))),
        "centerface": lambda bgr: privacy._detect_faces_centerface(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)) or [],
        "yunet": lambda bgr: privacy._detect_faces_yunet(bgr) or [],
        "union_cf_yunet": lambda bgr: privacy.union_merge_boxes(
            (privacy._detect_faces_centerface(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)) or [])
            + (privacy._detect_faces_yunet(bgr) or [])
        ),
    }

    print("=== FACE DETECTION BENCHMARK ===")
    for name, fn in methods.items():
        tp = fn_cnt = fp = 0
        latencies = []
        details = []
        for sname, bgr, expected in face_scenes:
            t0 = time.perf_counter()
            boxes = privacy.union_merge_boxes(fn(bgr))
            dt = (time.perf_counter() - t0) * 1000
            latencies.append(dt)
            det_n = len(boxes)
            if expected == 0:
                fp += det_n
            else:
                matched = min(expected, det_n)
                tp += matched
                fn_cnt += max(0, expected - det_n)
                fp += max(0, det_n - expected)
            details.append(f"{sname}:{det_n}/{expected}")
        recall = tp / max(1, tp + fn_cnt)
        prec = tp / max(1, tp + fp)
        avg_ms = sum(latencies) / len(latencies)
        print(f"{name:15s} | recall={recall:.1%} prec={prec:.1%} TP={tp} FN={fn_cnt} FP={fp} | avg={avg_ms:.1f}ms")
        print("   " + ", ".join(details))

    print("\n=== GREEK / EU LICENCE-PLATE BENCHMARK ===")
    plate_scenes = _make_plate_suite()
    plate_methods = {
        "haar_plate_only": lambda bgr: privacy._detect_plates(cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))),
        "eu_structural": lambda bgr: privacy._detect_plates_eu_structural(bgr),
        "union_plates": lambda bgr: privacy.union_merge_boxes(
            privacy._detect_plates(cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)))
            + privacy._detect_plates_eu_structural(bgr),
            iou_threshold=0.3,
        ),
    }
    for name, fn in plate_methods.items():
        tp = fn_cnt = fp = 0
        latencies = []
        details = []
        for sname, bgr, expected in plate_scenes:
            t0 = time.perf_counter()
            boxes = privacy.union_merge_boxes(fn(bgr), iou_threshold=0.3)
            dt = (time.perf_counter() - t0) * 1000
            latencies.append(dt)
            det_n = len(boxes)
            if expected == 0:
                fp += det_n
            else:
                matched = min(expected, det_n)
                tp += matched
                fn_cnt += max(0, expected - det_n)
                fp += max(0, det_n - expected)
            details.append(f"{sname}:{det_n}/{expected}")
        recall = tp / max(1, tp + fn_cnt)
        prec = tp / max(1, tp + fp)
        avg_ms = sum(latencies) / len(latencies)
        print(f"{name:15s} | recall={recall:.1%} prec={prec:.1%} TP={tp} FN={fn_cnt} FP={fp} | avg={avg_ms:.1f}ms")
        print("   " + ", ".join(details))


if __name__ == "__main__":
    run_benchmark()
