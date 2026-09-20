from app.vision.showcase_regions import detection_regions
"""One-shot table scan, run at stream start (and on demand).

Pure vision: reports what the table looks like right now — which legend slots
hold a card and whether each is face-up (yellow card back = face-down), and
whether a card sits in the card-play region (returning its normalized crop).
The API layer maps these findings onto game state; this module never touches
state itself.
"""
import logging
from typing import Optional

import cv2
import numpy as np

from app.vision.card_detector import CardDetector, split_quad
from app.vision.legends import (LEGEND_DETECTION, LEGEND_SLOTS, classify_legend_slot,
                                legend_slot_crops, legend_slot_rects)

log = logging.getLogger("app.vision.scan")

# Re-exported for callers/tests; the implementations live in app.vision.legends.
__all__ = ["classify_legend_slot", "legend_slot_rects", "legend_slot_crops", "scan_player", "LEGEND_SLOTS"]


def scan_player(service, player: int) -> dict:
    """Scan one player's corrected view. Returns findings + card crops (np)."""
    frame, view = service.frame_and_view(player)
    if view is None:
        return {"ok": False, "error": "no frame"}
    regions = detection_regions(service.store, player)
    detector = CardDetector({**(service.store.cameras.get("detection") or {})})
    rcfg = service.recognition_config()

    legends = []
    legend_crops: list[list] = []
    legend_region = regions.get("legend_region")
    if legend_region:
        slot_detector = CardDetector({**(service.store.cameras.get("detection") or {}), **LEGEND_DETECTION})
        for rect in legend_slot_rects(legend_region):
            finding = classify_legend_slot(view, rect)
            legends.append(finding)
            # Every slot gets recognition; brightness is only a diagnostic hint.
            legend_crops.append(
                legend_slot_crops(service, frame, view, rect, slot_detector, player))

    card_crop: Optional[np.ndarray] = None
    card_crops: list = []
    card_bbox = None
    play_region = regions.get("card_play_region")
    if play_region:
        detections, _ = detector.detect_all(
            view, play_region, max_candidates=max(1, int(rcfg.get("candidates", 1))))
        if detections:
            card_bbox = list(detections[0].bbox)
            for i, det in enumerate(detections):
                crop = service.native_crop(frame, player, det.quad)
                card_crops.append((f"quad{i}", crop if crop is not None else det.crop))
            if rcfg.get("try_splits", True):
                for label, half in split_quad(detections[0].quad):
                    crop = service.native_crop(frame, player, half)
                    if crop is not None:
                        card_crops.append((label, crop))
            card_crop = card_crops[0][1]

    log.info(
        "SCAN player=%s legends=%s card=%s",
        player,
        [(l["present"], l["face_up"]) for l in legends],
        card_bbox is not None,
    )
    return {"ok": True, "legends": legends, "legend_crops": legend_crops,
            "card_bbox": card_bbox, "card_crop": card_crop, "card_crops": card_crops}
