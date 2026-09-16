"""Calibration storage: camera source + per-player rects, homography, ROIs.

Everything is normalized 0..1. Files live in config/ and are safe to edit by
hand; missing keys fall back to defaults.
"""
import json
import math
import logging
from pathlib import Path

from app.vision.card_detector import DEFAULT_DETECTION
from app.vision.perspective import clamp01

log = logging.getLogger("app.vision.calibration")

DEFAULT_CAMERAS = {
    "source": {"type": "camera", "index": 0, "path": "", "exposure_mode": "motion"},
    "corrected_size": [800, 600],
    "rotate_source_180": False,
    # Card detection tuning — single source of truth is DEFAULT_DETECTION in
    # app/vision/card_detector.py; never duplicate values here.
    "detection": dict(DEFAULT_DETECTION),
}

_DEFAULT_PLAYER_REGIONS = {
    "card_play_region": {"x": 0.30, "y": 0.30, "width": 0.40, "height": 0.40},
    "fixer_region": {"x": 0.05, "y": 0.70, "width": 0.40, "height": 0.25},
    "eddie_region": {"x": 0.55, "y": 0.70, "width": 0.35, "height": 0.20},
    "gig_region": {"x": 0.55, "y": 0.70, "width": 0.40, "height": 0.25},
    "legend_region": {"x": 0.05, "y": 0.05, "width": 0.35, "height": 0.20},
}

DEFAULT_REGIONS = {
    "player1": {
        "source_rect": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
        "homography_points": None,  # [[x,y] TL, TR, BR, BL] normalized in the crop
        "regions": dict(_DEFAULT_PLAYER_REGIONS),
    },
    "player2": {
        "source_rect": {"x": 0.5, "y": 0.0, "width": 0.5, "height": 1.0},
        "homography_points": None,
        "regions": dict(_DEFAULT_PLAYER_REGIONS),
    },
}


def _sanitize_rect(rect: dict) -> dict:
    return {
        "x": clamp01(rect.get("x", 0)),
        "y": clamp01(rect.get("y", 0)),
        "width": clamp01(rect.get("width", 1)),
        "height": clamp01(rect.get("height", 1)),
    }


def _sanitize_player(player: dict, defaults: dict) -> dict:
    out = {
        "source_rect": _sanitize_rect(player.get("source_rect", defaults["source_rect"])),
        "homography_points": None,
        "regions": {},
    }
    points = player.get("homography_points")
    if isinstance(points, list) and len(points) == 4:
        out["homography_points"] = [[clamp01(p[0]), clamp01(p[1])] for p in points]
    regions = player.get("regions", {})
    for name, rect in {**defaults["regions"], **regions}.items():
        out["regions"][name] = _sanitize_rect(rect)
    return out


class CalibrationStore:
    def __init__(self, cameras_path: Path, regions_path: Path):
        self.cameras_path = cameras_path
        self.regions_path = regions_path
        self.cameras = self._load(cameras_path, DEFAULT_CAMERAS)
        self.regions = self._sanitize_regions(self._load(regions_path, DEFAULT_REGIONS))

    @staticmethod
    def _load(path: Path, defaults: dict) -> dict:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                merged = json.loads(json.dumps(defaults))  # deep copy
                merged.update(data)
                return merged
            except (json.JSONDecodeError, OSError) as exc:
                log.error("CALIBRATION_UNREADABLE path=%s error=%s", path, exc)
        return json.loads(json.dumps(defaults))

    @staticmethod
    def _sanitize_regions(data: dict) -> dict:
        return {
            "player1": _sanitize_player(data.get("player1", {}), DEFAULT_REGIONS["player1"]),
            "player2": _sanitize_player(data.get("player2", {}), DEFAULT_REGIONS["player2"]),
        }

    def save_cameras(self, data: dict) -> dict:
        merged = json.loads(json.dumps(DEFAULT_CAMERAS))
        merged.update(data)
        merged["rotate_source_180"] = merged.get("rotate_source_180") is True
        size = merged.get("corrected_size", [800, 600])
        merged["corrected_size"] = [max(64, int(size[0])), max(64, int(size[1]))]
        adjustments = merged.get("vision_adjustments", {})
        clean = {}
        for key, default, low, high in (("brightness", 0, -100, 100), ("contrast", 1, .5, 2)):
            try:
                value = float(adjustments.get(key, default))
                if not math.isfinite(value):
                    value = default
            except (ValueError, TypeError, AttributeError):
                value = default
            clean[key] = max(low, min(high, value))
        merged["vision_adjustments"] = clean
        self.cameras = merged
        self.cameras_path.parent.mkdir(parents=True, exist_ok=True)
        self.cameras_path.write_text(json.dumps(merged, indent=2))
        log.info("CAMERAS_SAVED path=%s", self.cameras_path)
        return merged

    def save_regions(self, data: dict) -> dict:
        self.regions = self._sanitize_regions(data)
        self.regions_path.parent.mkdir(parents=True, exist_ok=True)
        self.regions_path.write_text(json.dumps(self.regions, indent=2))
        log.info("REGIONS_SAVED path=%s", self.regions_path)
        return self.regions

    def player(self, number: int) -> dict:
        return self.regions[f"player{number}"]

    @property
    def corrected_size(self) -> tuple[int, int]:
        size = self.cameras.get("corrected_size", [800, 600])
        return int(size[0]), int(size[1])
