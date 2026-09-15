"""Camera/video capture on a dedicated thread.

Only the most recent frame is kept (latest-frame slot, not a growing queue):
consumers always get the freshest frame and the pipeline can never fall behind.
Supports V4L2 devices (OBS Virtual Camera), camera indexes, and prerecorded
video files (looped, paced to their native FPS) for camera-free development.
"""
import logging
import sys
from pathlib import Path
import threading
import time
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger("app.vision.capture")


class CaptureThread(threading.Thread):
    RETRY_SECONDS = 2.0

    def __init__(self, source: dict):
        """source: {"type": "camera"|"video", "index": int, "path": str}"""
        super().__init__(daemon=True, name="vision-capture")
        self.source = source
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._seq = 0
        self._stop_event = threading.Event()
        self.error: Optional[str] = None
        self.fps = 0.0
        self.native_fps = 30.0
        self.pixel_format = "unknown"
        self.capture_warning = None
        self.resolution: Optional[tuple[int, int]] = None
        self._pace = 0.0

    @property
    def is_video_file(self) -> bool:
        return self.source.get("type") == "video"

    def _open(self) -> Optional[cv2.VideoCapture]:
        if self.is_video_file:
            target = str(self.source.get("path", ""))
        else:
            target = self.source.get("path") or ""
            if not target:
                target = int(self.source.get("index", 0))
        local_camera = self.source.get("type", "camera") == "camera" and (isinstance(target, int) or str(target).startswith("/dev/video"))
        backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(target, backend) if local_camera else cv2.VideoCapture(target)
        if not cap.isOpened():
            self.error = f"Cannot open source: {target!r}"
            log.error("CAPTURE_OPEN_FAILED source=%r", target)
            cap.release()
            return None
        self.capture_warning = None
        mode = self.source.get("capture_mode", "auto")
        device_name = 'video'+str(target) if isinstance(target, int) else Path(str(target)).resolve().name
        virtual = (Path('/sys/devices/virtual/video4linux')/device_name).exists()
        request_mjpeg = local_camera and (mode in ('mjpeg1080', 'mjpeg720') or (mode == 'auto' and not virtual))
        if request_mjpeg:
            width, height = (1280, 720) if mode == 'mjpeg720' else (1920, 1080)
            # Negotiate compression BEFORE resolution/FPS; uncompressed 1080p
            # can otherwise constrain USB cameras to single-digit frame rates.
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, 30)
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
        self.pixel_format = ''.join(chr((fourcc >> (8*i)) & 255) for i in range(4)).strip('\x00') or 'unknown'
        reported = cap.get(cv2.CAP_PROP_FPS)
        if request_mjpeg and (self.pixel_format not in ('MJPG', 'JPEG') or reported < 29):
            self.capture_warning = f"Camera negotiated {self.pixel_format} at {reported:g} FPS instead of MJPEG / 30 FPS. Try MJPEG 720p or check camera/USB settings."

        self.native_fps = reported if 1 <= reported <= 120 else 30.0
        self.error = None
        log.info("CAPTURE_STARTED source=%r video_file=%s", target, self.is_video_file)
        return cap

    def run(self) -> None:
        cap = None
        frame_times: list[float] = []
        deadline = time.monotonic()
        while not self._stop_event.is_set():
            if cap is None:
                cap = self._open()
                if cap is None:
                    if self.is_video_file:
                        return  # a missing file will not appear by retrying
                    self._stop_event.wait(self.RETRY_SECONDS)
                    continue
                deadline = time.monotonic()
                video_fps = cap.get(cv2.CAP_PROP_FPS) or 0
                self._pace = 1.0 / video_fps if self.is_video_file and video_fps > 0 else 0

            ok, frame = cap.read()
            if not ok:
                if self.is_video_file:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop the clip
                    continue
                log.warning("CAPTURE_READ_FAILED reconnecting")
                cap.release()
                cap = None
                self._stop_event.wait(self.RETRY_SECONDS)
                continue

            now = time.monotonic()
            with self._lock:
                self._frame = frame
                self._seq += 1
                self.resolution = (frame.shape[1], frame.shape[0])
            frame_times.append(now)
            while frame_times and now - frame_times[0] > 2.0:
                frame_times.pop(0)
            self.fps = len(frame_times) / 2.0
            if self._pace:
                deadline += self._pace
                now = time.monotonic()
                if deadline < now - self._pace:
                    deadline = now
                self._stop_event.wait(max(0, deadline - now))

        if cap is not None:
            cap.release()
        log.info("CAPTURE_STOPPED")

    def latest(self) -> tuple[Optional[np.ndarray], int]:
        with self._lock:
            return self._frame, self._seq

    def stop(self) -> None:
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout=3)
