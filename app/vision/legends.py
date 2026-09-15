"""Legend slots: where they are, whether each holds a face-up card, and the
crops recognition should look at.

A player's legend region holds three cards in a row. They are stacked along
the region's LONG axis (a vertical column at the side of the mat on a
top-down camera, a horizontal row on a facing camera), so the region is split
into three equal slots along whichever side is longer.
"""
import logging
from typing import Optional

import cv2
import numpy as np

from app.vision.card_detector import CardDetector, rectify_quad
from app.vision.perspective import crop_rect, rect_to_pixels

log = logging.getLogger("app.vision.legends")

# Yellow card-back heuristic (HSV). The physical backs are bold yellow + black.
YELLOW_HUE = (15, 40)
YELLOW_SAT_MIN = 80
YELLOW_VAL_MIN = 80
BACK_YELLOW_FRAC = 0.22   # >= this fraction of yellow pixels -> face-down back
PRESENT_BRIGHT_FRAC = 0.20  # fraction of bright pixels -> a card is there
BRIGHT_VAL_MIN = 90
LEGEND_SLOTS = 3

# Detector overrides for finding the card outline inside a slot: the card
# fills most of the slot and may touch its edges.
LEGEND_DETECTION = {"max_area_frac": 0.98, "min_area_frac": 0.15}


def classify_legend_slot(view: np.ndarray, rect: dict) -> dict:
    """Is there a card in this legend slot, and is it face-up?"""
    crop = crop_rect(view, rect)
    if crop.size == 0:
        return {"present": False, "face_up": False, "yellow_frac": 0.0, "bright_frac": 0.0}
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    yellow = (
        (hue >= YELLOW_HUE[0]) & (hue <= YELLOW_HUE[1])
        & (sat >= YELLOW_SAT_MIN) & (val >= YELLOW_VAL_MIN)
    )
    bright = val >= BRIGHT_VAL_MIN
    yellow_frac = float(yellow.mean())
    bright_frac = float(bright.mean())
    present = bright_frac >= PRESENT_BRIGHT_FRAC or yellow_frac >= BACK_YELLOW_FRAC
    face_up = present and yellow_frac < BACK_YELLOW_FRAC
    return {
        "back_visible": yellow_frac >= BACK_YELLOW_FRAC,
        "present": present,
        "face_up": face_up,
        "yellow_frac": round(yellow_frac, 3),
        "bright_frac": round(bright_frac, 3),
    }


def legend_slot_rects(legend_region: dict) -> list[dict]:
    """Split the legend region into three equal slots along its longer side."""
    if legend_region["height"] > legend_region["width"]:
        height = legend_region["height"] / LEGEND_SLOTS
        return [
            {"x": legend_region["x"], "y": legend_region["y"] + i * height,
             "width": legend_region["width"], "height": height}
            for i in range(LEGEND_SLOTS)
        ]
    width = legend_region["width"] / LEGEND_SLOTS
    return [
        {"x": legend_region["x"] + i * width, "y": legend_region["y"],
         "width": width, "height": legend_region["height"]}
        for i in range(LEGEND_SLOTS)
    ]


def _rect_quad(rect: dict, vw: int, vh: int) -> np.ndarray:
    x, y, w, h = rect_to_pixels(rect, vw, vh)
    return np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])


def legend_slot_crops(service, frame: Optional[np.ndarray], view: np.ndarray, rect: dict,
                      detector: CardDetector, player: int) -> list:
    """(label, crop) candidates for a face-up legend slot: the card outline
    found inside the slot (tight, native resolution) first, then the whole
    slot as a fallback."""
    vh, vw = view.shape[:2]
    crops: list = []
    detections, _ = detector.detect_all(view, rect, max_candidates=3, allow_border=True)
    for i, detection in enumerate(detections):
        crop = service.native_crop(frame, player, detection.quad)
        crops.append((f"slot-quad{i}", crop if crop is not None else detection.crop))
    whole = service.native_crop(frame, player, _rect_quad(rect, vw, vh))
    if whole is None:
        whole = rectify_quad(view, _rect_quad(rect, vw, vh))
    crops.append(("slot", whole))
    return crops
