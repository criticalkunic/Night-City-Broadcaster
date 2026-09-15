"""Rect cropping, homography warping, and ROI drawing.

All configuration coordinates are normalized 0..1 so resolution changes never
invalidate saved calibration.
"""
import cv2
import numpy as np


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def rect_to_pixels(rect: dict, width: int, height: int) -> tuple[int, int, int, int]:
    """Normalized {x, y, width, height} -> pixel (x, y, w, h), clamped in-frame."""
    x = int(clamp01(rect["x"]) * width)
    y = int(clamp01(rect["y"]) * height)
    w = int(clamp01(rect["width"]) * width)
    h = int(clamp01(rect["height"]) * height)
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))
    return x, y, w, h


def crop_rect(frame: np.ndarray, rect: dict) -> np.ndarray:
    height, width = frame.shape[:2]
    x, y, w, h = rect_to_pixels(rect, width, height)
    return frame[y:y + h, x:x + w]


def warp_quad(image: np.ndarray, points_norm: list, out_size: tuple[int, int]) -> np.ndarray:
    """Perspective-correct a quad (normalized TL, TR, BR, BL) to a top-down view."""
    height, width = image.shape[:2]
    out_w, out_h = out_size
    src = np.float32([[clamp01(px) * width, clamp01(py) * height] for px, py in points_norm])
    dst = np.float32([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image, matrix, (out_w, out_h))


ROI_COLORS = {
    "card_play_region": (63, 210, 255),   # BGR yellow-ish
    "fixer_region": (195, 210, 35),       # cyan-ish
    "gig_region": (94, 77, 255),          # red-ish
    "legend_region": (160, 100, 255),     # magenta-ish
}
_DEFAULT_COLOR = (200, 200, 200)


def draw_regions(image: np.ndarray, regions: dict, highlight: str | None = None) -> np.ndarray:
    """Return a copy of image with named normalized rects outlined and labeled."""
    out = image.copy()
    height, width = out.shape[:2]
    for name, rect in regions.items():
        color = ROI_COLORS.get(name, _DEFAULT_COLOR)
        thickness = 3 if name == highlight else 1
        x, y, w, h = rect_to_pixels(rect, width, height)
        cv2.rectangle(out, (x, y), (x + w, y + h), color, thickness)
        cv2.putText(out, name.replace("_region", ""), (x + 4, y + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return out


def draw_rect(image: np.ndarray, rect: dict, color: tuple, label: str = "") -> np.ndarray:
    out = image.copy()
    height, width = out.shape[:2]
    x, y, w, h = rect_to_pixels(rect, width, height)
    cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
    if label:
        cv2.putText(out, label, (x + 4, y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    return out
