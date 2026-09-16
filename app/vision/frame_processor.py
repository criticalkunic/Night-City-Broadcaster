"""VisionService: turns the raw capture into named views for setup/debug.

Views (each available as JPEG snapshot or MJPEG stream):
  raw           combined camera frame
  p1_crop       player 1 source rectangle
  p2_crop       player 2 source rectangle
  p1_corrected  player 1 perspective-corrected (homography if calibrated)
  p2_corrected  player 2 perspective-corrected

Processing happens on demand per request (crop + warp are cheap); capture runs
on its own thread and never blocks FastAPI. Card detection plugs in at
Milestone 3 without changing this interface.
"""
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from app.vision.background import MatBackground
from app.vision.calibration import CalibrationStore
from app.vision.capture import CaptureThread
from app.vision.card_detector import CROP_SIZE, DetectionWorker, rectify_quad
from app.vision.perspective import crop_rect, draw_rect, draw_regions, rect_to_pixels, warp_quad
from app.vision.recognizer import DEFAULT_RECOGNITION, Match

log = logging.getLogger("app.vision.service")

VIEWS = ("raw", "p1_crop", "p2_crop", "p1_corrected", "p2_corrected")

_P1_COLOR = (195, 210, 35)  # BGR cyan-ish
_P2_COLOR = (94, 77, 255)   # BGR red-ish


class VisionService:
    def __init__(self, store: CalibrationStore, captures_dir: Path, recognizer=None):
        self.store = store
        self.captures_dir = captures_dir
        self.mat_background = MatBackground(captures_dir / "empty-mat.npz")
        # Milestone 4: card recognizer (index over the local card DB). Optional
        # so vision runs detection-only without a card DB.
        self.recognizer = recognizer
        # Called from the detection thread with (player, Match) when a stable
        # card is recognized above min_confidence and auto_apply is on. The
        # app layer maps it onto game state + WebSocket broadcast.
        self.on_recognized: Optional[Callable[[int, Match], None]] = None
        self.on_play_region_empty = None
        self.on_card_removed: Optional[Callable[[int], None]] = None
        # Called from the detection thread with (player, slot, face_up, Match|None)
        # when a legend slot has settled face-up (recognized) or face-down.
        self.on_legend: Optional[Callable[[int, int, bool, Optional[Match]], None]] = None
        self.capture: Optional[CaptureThread] = None
        self.detection: Optional[DetectionWorker] = None
        self.paused = False
        self._frozen: Optional[np.ndarray] = None  # raw frame held while paused
        self._lock = threading.Lock()
        self.validate_source = None

    def mat_signature(self):
        source = self.capture.source if self.capture is not None else self.store.cameras.get("source")
        player = self.store.player(1)
        player = {**player, "regions": {k: v for k, v in player["regions"].items() if k != "eddie_region"}}
        return json.dumps({"source": source, "player": player,
                           "adjustments": self.store.cameras.get("vision_adjustments", {}),
                           "size": self.store.corrected_size}, sort_keys=True)

    def capture_empty_mat(self):
        if not self.running or self.paused:
            raise ValueError("Start live vision and resume it before capturing the empty mat")
        _, view = self.frame_and_view(1)
        if view is None:
            raise ValueError("No camera frame available")
        self.mat_background.capture(view, self.mat_signature())
        return self.mat_background.status(self.mat_signature())

    def play_foreground(self, view):
        return self.mat_background.foreground(view, self.mat_signature())

    # ------------------------------------------------------------- control

    @property
    def running(self) -> bool:
        return self.capture is not None and self.capture.is_alive()

    def start(self, source: Optional[dict] = None) -> dict:
        src = source or self.store.cameras.get("source", {})
        if self.validate_source:
            self.validate_source(src)
        with self._lock:
            self._stop_locked()
            self.capture = CaptureThread(dict(src))
            self.capture.start()
            self.detection = DetectionWorker(self, self.store.cameras.get("detection"))
            self.detection.start()
            self.paused = False
            self._frozen = None
        # Give the source a moment so the first status reflects reality.
        time.sleep(0.3)
        log.info("VISION_START source=%s", src)
        return self.status()

    def stop(self) -> dict:
        with self._lock:
            self._stop_locked()
        log.info("VISION_STOP")
        return self.status()

    def _stop_locked(self) -> None:
        if self.detection is not None:
            self.detection.stop()
            self.detection = None
        if self.capture is not None:
            self.capture.stop()
            self.capture = None
        self.paused = False
        self._frozen = None

    def pause(self) -> dict:
        frame = self._capture_frame()
        with self._lock:
            self.paused = True
            self._frozen = frame
        log.info("VISION_PAUSED")
        return self.status()

    def resume(self) -> dict:
        with self._lock:
            self.paused = False
            self._frozen = None
        log.info("VISION_RESUMED")
        return self.status()

    def status(self) -> dict:
        cap = self.capture
        return {
            "running": self.running,
            "paused": self.paused,
            "source": cap.source if cap else self.store.cameras.get("source"),
            "fps": round(cap.fps, 1) if cap else 0.0,
            "native_fps": getattr(cap, "native_fps", 30.0) if cap else 30.0,
            "pixel_format": getattr(cap, "pixel_format", "unknown"),
            "backend": getattr(cap, "backend_name", "unknown"),
            "exposure": getattr(cap, "exposure", None),
            "auto_exposure": getattr(cap, "auto_exposure", None),
            "exposure_units": getattr(cap, "exposure_units", None),
            "capture_warning": getattr(cap, "capture_warning", None),
            "resolution": list(cap.resolution) if cap and cap.resolution else None,
            "error": cap.error if cap else None,
            "views": list(VIEWS),
        }

    # ------------------------------------------------------------ rendering

    def _capture_frame(self) -> Optional[np.ndarray]:
        if self.paused and self._frozen is not None:
            return self._frozen
        if self.capture is None:
            return None
        frame, _ = self.capture.latest()
        return frame

    def _raw_frame(self) -> Optional[np.ndarray]:
        """Orient the shared source before calibration, vision and broadcast crops."""
        frame = self._capture_frame()
        if frame is not None and self.store.cameras.get("rotate_source_180") is True:
            return cv2.rotate(frame, cv2.ROTATE_180)
        return frame

    def _corrected(self, frame: np.ndarray, player: int) -> np.ndarray:
        conf = self.store.player(player)
        crop = crop_rect(frame, conf["source_rect"])
        points = conf.get("homography_points")
        size = self.store.corrected_size
        if points:
            return warp_quad(crop, points, size)
        # No calibration yet: letterbox instead of stretching — a plain resize
        # distorts aspect ratios and breaks card-shape detection.
        return self._fit_resize(crop, size)

    def adjust_vision_frame(self, frame):
        settings = self.store.cameras.get("vision_adjustments", {})
        brightness = float(settings.get("brightness", 0))
        contrast = float(settings.get("contrast", 1))
        if brightness == 0 and contrast == 1:
            return frame
        # LUT clips negative values rather than reflecting them as convertScaleAbs does.
        lut = np.clip((np.arange(256, dtype=np.float32) - 127.5) * contrast
                      + 127.5 + brightness, 0, 255).astype(np.uint8)
        return cv2.LUT(frame, lut)

    def frame_and_view(self, player: int) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Vision-adjusted native frame and corrected view from the same capture."""
        frame = self._raw_frame()
        if frame is None:
            return None, None
        frame = self.adjust_vision_frame(frame)
        return frame, self._corrected(frame, player)

    def corrected_to_raw(self, frame_shape: tuple, player: int, points: np.ndarray) -> np.ndarray:
        """Map pixel points in the corrected view back to raw-frame pixels."""
        conf = self.store.player(player)
        fh, fw = frame_shape[:2]
        sx, sy, sw, sh = rect_to_pixels(conf["source_rect"], fw, fh)
        out_w, out_h = self.store.corrected_size
        pts = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
        homography = conf.get("homography_points")
        if homography:
            src = np.float32([[max(0.0, min(1.0, px)) * sw, max(0.0, min(1.0, py)) * sh]
                              for px, py in homography])
            dst = np.float32([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]])
            inverse = cv2.getPerspectiveTransform(dst, src)
            mapped = cv2.perspectiveTransform(pts, inverse).reshape(-1, 2)
        else:
            scale = min(out_w / sw, out_h / sh)
            new_w, new_h = max(1, int(sw * scale)), max(1, int(sh * scale))
            off_x, off_y = (out_w - new_w) // 2, (out_h - new_h) // 2
            mapped = (pts.reshape(-1, 2) - np.float32([off_x, off_y])) / scale
        return mapped + np.float32([sx, sy])

    def native_crop(self, frame: Optional[np.ndarray], player: int, quad_corrected,
                    size: tuple = CROP_SIZE) -> Optional[np.ndarray]:
        """Rectify a corrected-view quad straight from the raw frame, so the
        crop keeps the camera's native resolution instead of the corrected
        view's downscale."""
        if frame is None:
            return None
        try:
            raw_quad = self.corrected_to_raw(frame.shape, player, quad_corrected)
            return rectify_quad(frame, raw_quad, size)
        except cv2.error as exc:
            log.warning("NATIVE_CROP_FAILED player=%s error=%s", player, exc)
            return None

    @staticmethod
    def _fit_resize(image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
        target_w, target_h = size
        height, width = image.shape[:2]
        scale = min(target_w / width, target_h / height)
        new_w, new_h = max(1, int(width * scale)), max(1, int(height * scale))
        resized = cv2.resize(image, (new_w, new_h))
        canvas = np.zeros((target_h, target_w, 3), dtype=image.dtype)
        x = (target_w - new_w) // 2
        y = (target_h - new_h) // 2
        canvas[y:y + new_h, x:x + new_w] = resized
        return canvas

    def render_view(self, view: str, rois: bool = False) -> Optional[np.ndarray]:
        frame = self._raw_frame()
        if frame is None:
            return None
        if view == "raw":
            if rois:
                out = draw_rect(frame, self.store.player(1)["source_rect"], _P1_COLOR, "P1")
                return out
            return frame
        if view in ("p1_crop", "p2_crop"):
            return crop_rect(frame, self.store.player(int(view[1]))["source_rect"])
        if view in ("p1_corrected", "p2_corrected"):
            player = int(view[1])
            out = self._corrected(self.adjust_vision_frame(frame), player)
            if rois:
                out = draw_regions(out, self.store.player(player)["regions"])
                out = self._draw_detection(out, player)
            return out
        raise ValueError(f"Unknown view: {view}")

    def _draw_detection(self, view: np.ndarray, player: int) -> np.ndarray:
        if self.detection is None:
            return view
        bbox = self.detection.bbox_quad(player)
        if not bbox:
            return view
        height, width = view.shape[:2]
        x, y = int(bbox[0] * width), int(bbox[1] * height)
        w, h = int(bbox[2] * width), int(bbox[3] * height)
        result = self.detection.results()["players"][str(player)]
        color = (80, 220, 80) if result["stable"] else (200, 200, 200)
        cv2.rectangle(view, (x, y), (x + w, y + h), color, 2)
        cv2.putText(view, f"card {result['stable_frames']}f", (x, max(14, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        return view

    def jpeg(self, view: str, rois: bool = False) -> bytes:
        image = self.render_view(view, rois=rois)
        if image is None:
            image = self._placeholder(view)
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buffer.tobytes()

    @staticmethod
    def _placeholder(view: str) -> np.ndarray:
        image = np.full((270, 480, 3), 22, dtype=np.uint8)
        cv2.putText(image, "NO SIGNAL", (150, 125), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (63, 210, 255), 2, cv2.LINE_AA)
        cv2.putText(image, f"view: {view}", (150, 165), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (160, 160, 160), 1, cv2.LINE_AA)
        return image

    # --------------------------------------------------------- recognition

    def recognition_config(self) -> dict:
        """Live-merged recognition config (saved calibration wins)."""
        saved = self.store.cameras.get("recognition") or {}
        return {**DEFAULT_RECOGNITION, "auto_apply": True, **saved}

    def recognize_crop(self, crop: Optional[np.ndarray],
                       card_type: Optional[str] = None) -> Optional[Match]:
        """Identify a normalized crop against the card DB (None if no index)."""
        if crop is None or self.recognizer is None or not self.recognizer.ready:
            return None
        return self.recognizer.recognize(crop, card_type=card_type, config=self.recognition_config())

    def recognize_crops(self, crops: list, card_type: Optional[str] = None) -> Optional[Match]:
        """Identify the best of several (label, crop) candidates."""
        if not crops or self.recognizer is None or not self.recognizer.ready:
            return None
        cfg = self.recognition_config()
        # Fallback crops (other quads, halves) only run when the best quad is
        # not already a clear match: keeps the common case to one recognition.
        stop_at = min(1.0, float(cfg["min_confidence"]) + 0.15)
        return self.recognizer.recognize_many(crops, card_type=card_type, config=cfg, stop_at=stop_at)

    def recognize_player(self, player: int) -> Optional[Match]:
        """Identify the current detection candidates for a player (on demand)."""
        if self.detection is None:
            return None
        return self.detection.recognize_now(player)

    # ----------------------------------------------------------- detection

    def detection_results(self) -> dict:
        if self.detection is None or not self.running:
            return {"fps": 0.0, "config": self.store.cameras.get("detection", {}),
                    "recognition": self.recognition_config(),
                    "recognizer_ready": bool(self.recognizer and self.recognizer.ready),
                    "players": {"1": None, "2": None},
                    "legends": {"1": [None] * 3, "2": [None] * 3}}
        return self.detection.results()

    def legend_debug_jpeg(self, player: int, slot: Optional[int] = None) -> bytes:
        """Current slot crop or full board with the exact three legend boxes."""
        from app.vision.legends import legend_slot_rects
        _, view = self.frame_and_view(player)
        if view is None:
            image = self._placeholder("No webcam frame")
        else:
            region = self.store.player(player)["regions"]["legend_region"]
            slots = legend_slot_rects(region)
            if slot is not None:
                image = crop_rect(view, slots[slot])
            else:
                image = view.copy()
                for index, rect in enumerate(slots):
                    image = draw_rect(image, rect, (80, 220, 220), f"Legend {index + 1}")
        if image.size == 0:
            image = self._placeholder("Legend region is empty")
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buffer.tobytes()

    def crop_jpeg(self, player: int) -> bytes:
        crop = self.detection.crop(player) if self.detection else None
        if crop is None:
            crop = self._placeholder(f"p{player} card crop")
        ok, buffer = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buffer.tobytes()

    def detection_debug_jpeg(self, player: int) -> bytes:
        """Card-play ROI with candidate outlines: grey = rejected, green = winner."""
        img = self.detection.debug_image(player) if self.detection else None
        if img is None:
            img = self._placeholder(f"p{player} detection")
        ok, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buffer.tobytes()

    def save_crop(self, player: int) -> Path:
        crop = self.detection.crop(player) if self.detection else None
        if crop is None:
            raise ValueError(f"No card crop available for player {player}")
        crops_dir = self.captures_dir / "crops"
        crops_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = crops_dir / f"p{player}-{stamp}.png"
        cv2.imwrite(str(path), crop)
        log.info("CROP_SAVED player=%s path=%s", player, path)
        return path

    # -------------------------------------------------------------- saving

    def save_frame(self, view: str) -> Path:
        image = self.render_view(view, rois=False)
        if image is None:
            raise ValueError("No frame available to save")
        self.captures_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = self.captures_dir / f"{view}-{stamp}.png"
        cv2.imwrite(str(path), image)
        log.info("FRAME_SAVED view=%s path=%s", view, path)
        return path
