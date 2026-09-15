"""User-captured empty playmat reference, independent of legend detection."""
import threading
from pathlib import Path

import cv2
import numpy as np


class MatBackground:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.image = None
        self.signature = None
        self.generation = 0
        try:
            with np.load(path, allow_pickle=False) as data:
                self.image = data["image"].copy()
                self.signature = str(data["signature"])
        except (OSError, ValueError, KeyError):
            pass

    def capture(self, image, signature):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with self.lock:
            with temporary.open("wb") as file:
                np.savez_compressed(file, image=image, signature=signature)
            temporary.replace(self.path)
            self.image = image.copy()
            self.signature = signature
            self.generation += 1

    def clear(self):
        with self.lock:
            self.path.unlink(missing_ok=True)
            self.image = self.signature = None
            self.generation += 1

    def status(self, signature):
        with self.lock:
            saved = self.image is not None
            active = saved and signature == self.signature
        return {"saved": saved, "active": active,
                "message": "Empty mat active" if active else
                "Camera or calibration changed: capture the empty mat again" if saved else "No empty mat captured"}

    def foreground(self, image, signature):
        with self.lock:
            reference = self.image
            valid = self.signature == signature
        if reference is None or not valid or reference.shape != image.shape:
            return None
        current = cv2.GaussianBlur(image, (5, 5), 0).astype(np.float32)
        base = cv2.GaussianBlur(reference, (5, 5), 0).astype(np.float32)
        # Estimate smooth local illumination, rather than classifying every
        # darker pixel under a hand's shadow as a new object. Color ratios
        # retain real artwork changes even when its brightness resembles mat.
        gray_now = current.mean(axis=2)
        gray_base = base.mean(axis=2)
        gain = cv2.GaussianBlur(gray_now, (0, 0), 25) / np.maximum(
            cv2.GaussianBlur(gray_base, (0, 0), 25), 15)
        gain = np.clip(gain, .35, 2.8)
        corrected = current / gain[:, :, None]
        difference = np.max(np.abs(corrected-base), axis=2)
        chroma_now = current / np.maximum(current.sum(axis=2, keepdims=True), 30)
        chroma_base = base / np.maximum(base.sum(axis=2, keepdims=True), 30)
        chroma_change = np.max(np.abs(chroma_now-chroma_base), axis=2)
        raw_change = np.max(np.abs(current-base), axis=2)
        mask = ((difference > 35) | ((chroma_change > .10) & (raw_change > 25))).astype(np.uint8)*255
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        # Solid silhouettes retain dark text/art holes inside the new card.
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros_like(mask)
        cv2.drawContours(filled, [c for c in contours if cv2.contourArea(c) >= 60], -1, 255, -1)
        return cv2.cvtColor(filled, cv2.COLOR_GRAY2BGR)
