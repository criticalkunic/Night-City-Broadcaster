from app.vision.showcase_regions import detection_regions
"""Milestone 3: detect card-shaped quads inside the card-play ROI.

Detection only — no recognition. Finds a convex 4-sided contour with a
card-like aspect ratio inside the configured ROI of a corrected player view,
perspective-corrects it to a normalized portrait crop, and tracks stability
across frames. Recognition (Milestone 4) will consume the normalized crop.
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from app.vision.perspective import rect_to_pixels
from app.vision.play_tracker import PlayTracker

log = logging.getLogger("app.vision.detector")

CARD_ASPECT = 63 / 88  # physical TCG card, short/long side
CROP_SIZE = (300, 420)  # normalized portrait crop (w, h)

DEFAULT_DETECTION = {
    "fps": 10,
    "min_area_frac": 0.006,     # of the ROI area (a ~80 px card in a big ROI is ~0.5%)
    "max_area_frac": 0.60,      # a card should not fill the whole ROI
    "aspect_tol": 0.25,         # relative deviation from CARD_ASPECT
    "min_rectangularity": 0.75, # contour area / min-area-rect area (noisy outlines)
    # Expected single-card area as a fraction of the FULL corrected view
    # (read it from the debug page with one card placed alone). 0 = disabled.
    # After calibration the card size is constant, so this kills merged
    # multi-card blobs that happen to have a card-like aspect.
    "card_area_frac": 0.0,
    "stable_frames": 5,
    "removal_seconds": 1.0,     # sustained valid frames without a card before clearing state
    "center_jitter": 0.05,      # max center movement (normalized) to stay "stable"
    # Live legend monitoring: every legend_interval seconds each legend slot is
    # classified (yellow back = face-down); a slot that stays face-up for
    # legend_checks consecutive checks is recognized and revealed.
    "legend_interval": 1.0,
    "legend_checks": 2,
}


@dataclass
class Detection:
    quad: np.ndarray            # 4x2 pixel coords in the corrected view (TL TR BR BL)
    bbox: tuple                 # normalized (x, y, w, h) in the corrected view
    center: tuple               # normalized center
    area_frac: float            # contour area / ROI area
    view_area_frac: float = 0.0  # contour area / full corrected view (for card_area_frac tuning)
    crop: np.ndarray = field(repr=False, default=None)


def rectify_quad(image: np.ndarray, quad: np.ndarray, size: tuple = CROP_SIZE) -> np.ndarray:
    """Perspective-correct a TL,TR,BR,BL quad (pixel coords in `image`) to a
    portrait crop of `size`. Landscape quads are rotated to portrait (which
    of the two portrait orientations is right is the recognizer's job)."""
    quad = np.asarray(quad, dtype=np.float32)
    w1 = np.linalg.norm(quad[1] - quad[0])
    w2 = np.linalg.norm(quad[2] - quad[3])
    h1 = np.linalg.norm(quad[3] - quad[0])
    h2 = np.linalg.norm(quad[2] - quad[1])
    out_w = max(1, int((w1 + w2) / 2))
    out_h = max(1, int((h1 + h2) / 2))
    dst = np.float32([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]])
    matrix = cv2.getPerspectiveTransform(quad, dst)
    warped = cv2.warpPerspective(image, matrix, (out_w, out_h))
    if out_w > out_h:  # landscape: rotate to portrait
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    return cv2.resize(warped, size, interpolation=cv2.INTER_AREA if warped.shape[0] > size[1] else cv2.INTER_CUBIC)


def split_quad(quad: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Halves of a quad along both axes (TL,TR,BR,BL order kept). Two cards
    lying side by side often pass as one card-aspect blob; recognizing the
    halves separately recovers the individual cards."""
    q = np.asarray(quad, dtype=np.float32)
    tl, tr, br, bl = q
    top_mid, bottom_mid = (tl + tr) / 2, (bl + br) / 2
    left_mid, right_mid = (tl + bl) / 2, (tr + br) / 2
    return [
        ("split-top", np.float32([tl, tr, right_mid, left_mid])),
        ("split-bottom", np.float32([left_mid, right_mid, br, bl])),
        ("split-left", np.float32([tl, top_mid, bottom_mid, bl])),
        ("split-right", np.float32([top_mid, tr, br, bottom_mid])),
    ]


def order_quad(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as TL, TR, BR, BL."""
    pts = pts.reshape(4, 2).astype(np.float32)
    ordered = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    ordered[0] = pts[np.argmin(s)]
    ordered[2] = pts[np.argmax(s)]
    ordered[1] = pts[np.argmin(d)]
    ordered[3] = pts[np.argmax(d)]
    return ordered


class CardDetector:
    """Multi-method quad finder tuned for cards on a dark play mat.

    Real footage rarely gives one clean Canny contour (busy card art, dark
    borders on dark mats, neighboring cards). Three binary masks are tried in
    order and every plausible contour becomes a candidate, either as an exact
    convex 4-gon or via its minimum-area rectangle when the outline is noisy
    but still rectangular. The best-scoring card-aspect candidate wins.
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = {**DEFAULT_DETECTION, **(config or {})}

    # ------------------------------------------------------------ masks

    @staticmethod
    def _masks(roi: np.ndarray):
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        kernel = np.ones((3, 3), np.uint8)

        # Single dilate pass: heavier morphology merges neighboring cards
        # into one giant blob on a real table.
        edges = cv2.Canny(blurred, 40, 120)
        edges = cv2.dilate(edges, kernel, iterations=1)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
        yield "canny", edges

        # Local contrast recovers shadowed/dim borders without altering the
        # original pixels subsequently supplied to recognition.
        normalized = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
        local_edges = cv2.Canny(cv2.GaussianBlur(normalized, (3, 3), 0), 25, 80)
        yield "local-contrast", cv2.morphologyEx(local_edges, cv2.MORPH_CLOSE, kernel)

        # Bright card face vs dark mat.
        _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        otsu = cv2.morphologyEx(otsu, cv2.MORPH_CLOSE, kernel, iterations=2)
        yield "otsu", otsu

        # Locally brighter regions (uneven lighting, dim cards).
        adaptive = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, -5)
        adaptive = cv2.morphologyEx(adaptive, cv2.MORPH_CLOSE, kernel, iterations=2)
        yield "adaptive", adaptive

        # Colorful mask: real card faces have saturated art/borders while play
        # mats are dark AND desaturated — brightness alone leaves dark card art
        # patchy. Union of bright-or-saturated, closed to solidify each card.
        sat = cv2.GaussianBlur(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)[:, :, 1], (5, 5), 0)
        bright_thresh, _ = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        sat_thresh, _ = cv2.threshold(sat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        colorful = (((blurred > bright_thresh) | (sat > sat_thresh)).astype(np.uint8)) * 255
        colorful = cv2.morphologyEx(colorful, cv2.MORPH_CLOSE, kernel, iterations=3)
        colorful = cv2.morphologyEx(colorful, cv2.MORPH_OPEN, kernel, iterations=1)
        yield "colorful", colorful

        # Eroded variants split cards that touch each other on the table.
        for iterations in (2, 4):
            yield f"colorful-e{iterations}", cv2.erode(colorful, kernel, iterations=iterations)

    # ---------------------------------------------------------- detection

    def detect(self, view: np.ndarray, roi_rect: dict,
               debug: bool = False) -> tuple[Optional[Detection], Optional[np.ndarray]]:
        """Find the best card-like quad inside roi_rect of a corrected view.

        Returns (detection, debug_image). debug_image (only when debug=True)
        shows the ROI with rejected candidates in grey and the winner in green.
        """
        detections, debug_img = self.detect_all(view, roi_rect, debug=debug, max_candidates=1)
        return (detections[0] if detections else None), debug_img

    def detect_all(self, view: np.ndarray, roi_rect: dict, debug: bool = False,
                   max_candidates: int = 3, allow_border: bool = False, recover_lines: bool = True,
                   ) -> tuple[list[Detection], Optional[np.ndarray]]:
        """Ranked distinct card-like quads inside roi_rect (best first).

        allow_border: accept quads hugging the ROI edges (legend slots, where
        the card fills the whole slot).
        """
        vh, vw = view.shape[:2]
        rx, ry, rw, rh = rect_to_pixels(roi_rect, vw, vh)
        roi = view[ry:ry + rh, rx:rx + rw]
        if roi.size == 0:
            return [], None
        roi_area = rw * rh

        debug_img = roi.copy() if debug else None
        scored: list[tuple[float, np.ndarray, float]] = []  # (score, quad, frac)

        for mask_name, mask in self._masks(roi):
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
                area = cv2.contourArea(contour)
                frac = area / roi_area
                if frac < self.config["min_area_frac"]:
                    break
                if frac > self.config["max_area_frac"]:
                    continue
                quad, rectangularity = self._quad_from_contour(contour, area)
                if quad is None:
                    continue
                if not allow_border and self._hugs_roi_border(quad, rw, rh):
                    if debug_img is not None:
                        cv2.polylines(debug_img, [quad.astype(np.int32)], True, (60, 60, 60), 1)
                    continue
                expected = float(self.config.get("card_area_frac") or 0)
                if expected > 0:
                    view_frac = area / (vw * vh)
                    if not (0.5 * expected <= view_frac <= 1.8 * expected):
                        if debug_img is not None:
                            cv2.polylines(debug_img, [quad.astype(np.int32)], True, (60, 60, 60), 1)
                        continue
                aspect_score = self._aspect_score(quad)
                if debug_img is not None:
                    cv2.polylines(debug_img, [quad.astype(np.int32)], True, (140, 140, 140), 1)
                if aspect_score <= 0:
                    continue
                scored.append((aspect_score * rectangularity, quad, frac))
            # No early break: later (eroded) masks split touching cards into
            # single-card candidates whose aspect scores beat merged blobs.

        if not scored and recover_lines:
            # Recover open card outlines connected to busy playmat contours.
            for score, quad in self._line_quads(roi):
                area = cv2.contourArea(quad)
                frac = area / roi_area
                expected = float(self.config.get("card_area_frac") or 0)
                if not self.config["min_area_frac"] <= frac <= self.config["max_area_frac"]:
                    continue
                if expected and not 0.5 * expected <= area / (vw * vh) <= 1.8 * expected:
                    continue
                if not allow_border and self._hugs_roi_border(quad, rw, rh):
                    continue
                scored.append((score, quad, frac))
        if max_candidates > 1 and recover_lines:
            # Slightly wider edge support recovers dim borders, but never
            # replaces an existing outline at the same card location.
            for score, quad in self._line_quads(roi, tolerance=5):
                area = cv2.contourArea(quad)
                frac = area / roi_area
                expected = float(self.config.get("card_area_frac") or 0)
                if not self.config["min_area_frac"] <= frac <= self.config["max_area_frac"]:
                    continue
                if expected and not 0.5 * expected <= area / (vw * vh) <= 1.8 * expected:
                    continue
                if not allow_border and self._hugs_roi_border(quad, rw, rh):
                    continue
                if any(np.linalg.norm(quad.mean(axis=0)-other.mean(axis=0)) < 0.5*np.sqrt(area)
                       for _, other, _ in scored):
                    continue
                scored.append((score * 0.7, quad, frac))
        if not scored:
            return [], debug_img
        scored.sort(key=lambda item: -item[0])

        # Distinct quads only: the same card is found by several masks; keep
        # the best-scoring one per location.
        picked: list[tuple[float, np.ndarray, float]] = []
        for score, quad, frac in scored:
            center = quad.mean(axis=0)
            if any(np.linalg.norm(center - other[1].mean(axis=0)) < 0.35 * np.sqrt(frac * roi_area)
                   for other in picked):
                continue
            picked.append((score, quad, frac))
            if len(picked) >= max_candidates:
                break

        detections: list[Detection] = []
        for i, (score, quad, frac) in enumerate(picked):
            quad_full = quad + np.float32([rx, ry])
            crop = rectify_quad(view, quad_full)
            xs, ys = quad_full[:, 0], quad_full[:, 1]
            bbox = (
                float(xs.min() / vw), float(ys.min() / vh),
                float((xs.max() - xs.min()) / vw), float((ys.max() - ys.min()) / vh),
            )
            center = (float(xs.mean() / vw), float(ys.mean() / vh))
            if debug_img is not None:
                color = (80, 220, 80) if i == 0 else (60, 200, 220)
                cv2.polylines(debug_img, [quad.astype(np.int32)], True, color, 2 if i == 0 else 1)
            detections.append(Detection(quad=quad_full, bbox=bbox, center=center,
                                        area_frac=float(frac),
                                        view_area_frac=float(frac * roi_area / (vw * vh)),
                                        crop=crop))
        return detections, debug_img

    @staticmethod
    def _line_quads(roi: np.ndarray, tolerance: float = 3):
        """Recover broken card outlines, requiring aligned segments on all sides."""
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        detected = cv2.createLineSegmentDetector().detect(gray)[0]
        if detected is None:
            return []
        segments = detected.reshape(-1, 4)
        origins = segments[:, :2]
        vectors = segments[:, 2:] - origins
        lengths = np.linalg.norm(vectors, axis=1)
        keep = lengths > 5
        origins, vectors, lengths = origins[keep], vectors[keep], lengths[keep]
        directions = vectors / lengths[:, None]
        height, width = roi.shape[:2]
        found = []
        proposals = [(a, vector, length, direction)
                     for a, vector, length, direction in zip(origins, vectors, lengths, directions)]
        # At webcam scale, glare and text break one border into short segments.
        # Join only collinear, nearby segments; support still uses original lines.
        for i in range(len(origins)):
            if lengths[i] < 20:
                continue
            aligned = np.flatnonzero((np.abs(directions @ directions[i]) > 0.99) & (lengths >= 20))
            for j in aligned:
                if j <= i:
                    continue
                delta = np.array([origins[j], origins[j] + vectors[j]]) - origins[i]
                across = np.abs(delta[:, 0] * directions[i, 1] - delta[:, 1] * directions[i, 0])
                if across.max() > 3:
                    continue
                along = delta @ directions[i]
                if along.min() > lengths[i] + 20 or along.max() < -20:
                    continue
                low, high = min(0, along.min()), max(lengths[i], along.max())
                proposals.append((origins[i] + directions[i] * low,
                                  directions[i] * (high - low), high - low, directions[i]))
        for a, vector, length, direction in proposals:
            if length < 30:
                continue
            normal = np.array([-direction[1], direction[0]])
            # LSD stops short of corners; modest extension recovers the border.
            for extension in (0, min(3.0, length * 0.04)):
                start, end = a - direction * extension, a + vector + direction * extension
                for factor in (CARD_ASPECT, 1 / CARD_ASPECT):
                    for sign in (-1, 1):
                        offset = normal * (length + 2 * extension) * factor * sign
                        quad = order_quad(np.array([start, end, end + offset, start + offset]))
                        if quad.min() < 1 or quad[:, 0].max() >= width - 1 or quad[:, 1].max() >= height - 1:
                            continue
                        support = []
                        for side in range(4):
                            edge = quad[(side + 1) % 4] - quad[side]
                            aligned = np.abs(directions @ (edge / np.linalg.norm(edge))) > 0.97
                            points = quad[side] + np.linspace(0.08, 0.92, 32)[:, None] * edge
                            delta = points[:, None, :] - origins[None, aligned, :]
                            along = (delta * directions[None, aligned, :]).sum(axis=2)
                            across = np.abs(delta[:, :, 0] * directions[None, aligned, 1]
                                            - delta[:, :, 1] * directions[None, aligned, 0])
                            hits = (across <= tolerance) & (along >= -2) & (along <= lengths[None, aligned] + 2)
                            fraction = float(hits.any(axis=1).mean())
                            if fraction < 0.50:
                                break
                            support.append(fraction)
                        if len(support) == 4 and sum(support) / 4 >= 0.72:
                            found.append((sum(support) / 4, quad))
        return found

    @staticmethod
    def _hugs_roi_border(quad: np.ndarray, rw: int, rh: int, margin: int = 3) -> bool:
        """A quad touching 3+ ROI edges is the ROI/mat itself, not a card."""
        xs, ys = quad[:, 0], quad[:, 1]
        touched = sum([
            xs.min() <= margin,
            ys.min() <= margin,
            xs.max() >= rw - margin,
            ys.max() >= rh - margin,
        ])
        return touched >= 3

    def _quad_from_contour(self, contour, area) -> tuple[Optional[np.ndarray], float]:
        """Exact convex 4-gon if the outline allows it, else min-area-rect
        fallback for noisy-but-rectangular blobs. Returns (quad, rectangularity).

        Both paths gate on fill (contour area / quad area): a convex 4-gon
        stretched around an L-shaped blob of several touching cards passes
        approxPolyDP but fills poorly, and must be rejected.
        """
        min_fill = self.config["min_rectangularity"]
        peri = cv2.arcLength(contour, True)
        for eps in (0.02, 0.04, 0.06):
            approx = cv2.approxPolyDP(contour, eps * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                quad_area = cv2.contourArea(approx)
                fill = float(area / quad_area) if quad_area > 0 else 0.0
                ordered = order_quad(approx)
                if min_fill <= fill <= 1.12 and self._has_straight_edges(contour, ordered):
                    return ordered, min(1.0, fill)
                break  # poorly-filled 4-gon: fall through to min-area-rect
        rect = cv2.minAreaRect(contour)
        rect_area = rect[1][0] * rect[1][1]
        if rect_area <= 0:
            return None, 0.0
        rectangularity = float(area / rect_area)
        if rectangularity < min_fill:
            return None, 0.0
        ordered = order_quad(cv2.boxPoints(rect))
        if not self._has_straight_edges(contour, ordered):
            return None, 0.0
        return ordered, rectangularity

    @staticmethod
    def _has_straight_edges(contour, quad: np.ndarray) -> bool:
        """A bounding rectangle is not evidence that the object has four edges.

        Sample the middle 80% of each side, allowing rounded card corners and
        modest contour noise. Curved mat artwork touches a fitted rectangle
        only near tangents; a real card supports most of every side.
        """
        lengths = [np.linalg.norm(quad[(i + 1) % 4] - quad[i]) for i in range(4)]
        tolerance = max(2.0, min(lengths) * 0.025)
        for i in range(4):
            a, b = quad[i], quad[(i + 1) % 4]
            supported = 0
            for t in np.linspace(0.1, 0.9, 17):
                point = a + t * (b - a)
                distance = abs(cv2.pointPolygonTest(contour, (float(point[0]), float(point[1])), True))
                supported += distance <= tolerance
            if supported / 17 < 0.70:
                return False
        return True

    def _aspect_score(self, quad: np.ndarray) -> float:
        """1.0 at perfect card aspect, 0 at/outside the tolerance edge."""
        w1 = np.linalg.norm(quad[1] - quad[0])
        w2 = np.linalg.norm(quad[2] - quad[3])
        h1 = np.linalg.norm(quad[3] - quad[0])
        h2 = np.linalg.norm(quad[2] - quad[1])
        width, height = (w1 + w2) / 2, (h1 + h2) / 2
        if width < 8 or height < 8:
            return 0.0
        aspect = min(width, height) / max(width, height)
        deviation = abs(aspect - CARD_ASPECT) / CARD_ASPECT
        tolerance = self.config["aspect_tol"]
        return max(0.0, 1.0 - deviation / tolerance)

class DetectionWorker(threading.Thread):
    """Runs detection at a bounded rate on the freshest corrected views.

    Never blocks capture or the web server; results are read via `results()`.
    """

    def __init__(self, service, config: Optional[dict] = None):
        super().__init__(daemon=True, name="vision-detect")
        self.service = service
        self.detector = CardDetector(config)
        self._stop_event = threading.Event()
        self._reset_play = threading.Event()
        self._lock = threading.Lock()
        self._results: dict[int, dict] = {1: self._empty(), 2: self._empty()}
        self._crops: dict[int, Optional[np.ndarray]] = {1: None, 2: None}
        self._candidates: dict[int, list] = {1: [], 2: []}   # (label, native crop) per tick
        self._legend_state: dict[int, list] = {
            p: [{"face_up": False, "streak": 0, "handled": None} for _ in range(3)] for p in (1, 2)}
        self._legend_results: dict[int, list] = {1: [None, None, None], 2: [None, None, None]}
        self._legend_next = 0.0
        self._legend_region_keys = {}
        self._legend_ticks = {1: 0, 2: 0}
        self._debug_imgs: dict[int, Optional[np.ndarray]] = {1: None, 2: None}
        self._matches: dict[int, Optional[dict]] = {1: None, 2: None}
        self._empty_frames = {1: 0, 2: 0}
        self._play = {1: PlayTracker(), 2: PlayTracker()}
        self._background_generation = None
        self.fps = 0.0

    @property
    def config(self) -> dict:
        """Live-merged config: saved calibration wins so tuning applies
        immediately without restarting vision."""
        saved = self.service.store.cameras.get("detection") or {}
        return {**DEFAULT_DETECTION, **saved}

    @staticmethod
    def _empty() -> dict:
        return {"present": False, "stable": False, "stable_frames": 0,
                "bbox": None, "area_frac": None, "view_area_frac": None, "ms": 0.0,
                "match": None}

    def run(self) -> None:
        tick_times: list[float] = []
        while not self._stop_event.is_set():
            started = time.monotonic()
            config = self.config  # re-read every tick: tuning applies live
            self.detector.config = config
            if self.service.running and not self.service.paused:
                for player in (1,):
                    try:
                        self._process(player, config)
                    except Exception:
                        log.exception("PLAY_CHECK_FAILED player=%s", player)
                if started >= self._legend_next:
                    self._legend_next = started + max(0.2, float(config["legend_interval"]))
                    for player in (1,):
                        try:
                            self._check_legends(player, config)
                        except Exception as exc:  # never kill the loop
                            log.error("LEGEND_CHECK_FAILED player=%s error=%s", player, exc)
                tick_times.append(started)
                while tick_times and started - tick_times[0] > 2.0:
                    tick_times.pop(0)
                self.fps = len(tick_times) / 2.0
            else:
                self.fps = 0.0
            elapsed = time.monotonic() - started
            interval = 1.0 / float(config["fps"])
            self._stop_event.wait(max(0.01, interval - elapsed))
        log.info("DETECTION_STOPPED")

    def request_play_reset(self):
        """Request a fresh observation on the worker thread; capture stays running."""
        self._reset_play.set()

    def _process(self, player: int, config: dict) -> None:
        if player == 1 and self._reset_play.is_set():
            self._reset_play.clear()
            self._play[player] = PlayTracker()
            self._empty_frames[player] = 0
        frame, view = self.service.frame_and_view(player)
        tracker = self._play[player]
        if view is None:
            tracker.absent_since = None
            tracker.empty_frames = 0
            for track in tracker.tracks:
                track['count'] = 0
            with self._lock:
                self._results[player] = self._empty()
                self._crops[player] = None
                self._candidates[player] = []
                self._matches[player] = None
            return
        roi = detection_regions(self.service.store, player).get('card_play_region')
        if roi is None:
            tracker.absent_since = None
            tracker.empty_frames = 0
            return
        rcfg = self.service.recognition_config()
        now = time.monotonic()
        t0 = time.perf_counter()
        # Original pixels always remain eligible; background subtraction adds
        # proposals instead of destroying card edges under shadows or glare.
        recognizer = getattr(self.service, 'recognizer', None)
        artwork_locator = recognizer is not None and hasattr(recognizer, 'locate') and recognizer.ready
        detections, debug_img = self.detector.detect_all(view, roi, debug=True, max_candidates=10,
                                                       recover_lines=not artwork_locator)
        recognizer = getattr(self.service, 'recognizer', None)
        if recognizer is not None and hasattr(recognizer, 'locate') and recognizer.ready:
            rx, ry, rw, rh = rect_to_pixels(roi, view.shape[1], view.shape[0])
            for quad in recognizer.locate(view[ry:ry+rh, rx:rx+rw]):
                quad = quad + np.float32([rx, ry])
                center = tuple(quad.mean(axis=0)/np.float32([view.shape[1],view.shape[0]]))
                if any(np.linalg.norm(np.array(center)-d.center) < .04 for d in detections):
                    continue
                xs, ys = quad[:,0], quad[:,1]
                area = cv2.contourArea(quad)
                detections.append(Detection(quad=quad, center=center,
                    bbox=(float(xs.min()/view.shape[1]),float(ys.min()/view.shape[0]),
                          float(np.ptp(xs)/view.shape[1]),float(np.ptp(ys)/view.shape[0])),
                    area_frac=area/(rw*rh), view_area_frac=area/(view.shape[0]*view.shape[1])))
        if not detections and artwork_locator:
            # Unknown printings and glare can defeat artwork location. Recover
            # open rectangular borders independently of the recognition library.
            detections, debug_img = self.detector.detect_all(
                view, roi, debug=True, max_candidates=10, recover_lines=True)
        for det in detections:
            det.crop = rectify_quad(view, det.quad)
        tracker.update(detections, now)
        checked = tracker.next_check(now, max(2, int(config['stable_frames'])))
        match = None
        if checked is not None:
            checked['checked'] = now
            candidates = self._candidate_crops(frame, player, [checked['current']], {**rcfg, 'try_splits': False})
            try:
                match = self.service.recognize_crops(candidates)
            except Exception as exc:
                log.error('RECOGNIZE_FAILED player=%s error=%s', player, exc)
            checked['guess'] = match
            if match is not None and match.confidence >= float(rcfg['min_confidence']):
                fresh = tracker.accept(checked, match, now)
                if fresh and rcfg.get('auto_apply', True) and self.service.on_recognized is not None:
                    self.service.on_recognized(player, match)
            else:
                checked['failures'] += 1
                # Do not retain an identity forever after a replacement or a
                # reflection that completely hides it. One bad check is tolerated.
                if checked['failures'] >= 3:
                    checked['match'] = None
        # Rectangles on a patterned mat are proposals, not proof of a card.
        # Once every visible proposal has actually been checked and rejected,
        # allow the new-game gate to clear without requiring a featureless mat.
        visible_tracks = [t for t in tracker.tracks if t['current'] is not None]
        rejected_scene = bool(visible_tracks) and bool(getattr(recognizer, 'ready', False)) and all(
            t.get('guess') is not None and t['guess'].confidence < float(rcfg['min_confidence'])
            and t['match'] is None and t['count'] >= int(config['stable_frames'])
            for t in visible_tracks)
        if not detections or rejected_scene:
            self._empty_frames[player] += 1
            if self._empty_frames[player] >= int(config['stable_frames']):
                # Cached identities from before the gate opened must not swallow
                # the first subsequent play (including the same card returning).
                if not detections:
                    tracker.tracks.clear()
                callback = getattr(self.service, 'on_play_region_empty', None)
                if callback is not None:
                    callback()
        else:
            self._empty_frames[player] = 0
        if tracker.removed(now, max(1.5, float(config.get('removal_seconds', 1.5))), int(config['stable_frames'])):
            callback = getattr(self.service, 'on_card_removed', None)
            if callback is not None:
                callback(player)
        current = [t for t in tracker.tracks if t['current'] is not None]
        display = next((t for t in current if t['match'] is not None and
                        t['match'].card_id == tracker.latest_id), checked or (current[0] if current else None))
        det = display['current'] if display else None
        display_match = (display['match'] or display.get('guess')) if display else None
        if checked is display and match is not None:
            display_match = match
        candidates = self._candidate_crops(frame, player, [det], rcfg) if det else []
        if debug_img is not None:
            rx, ry, _, _ = rect_to_pixels(roi, view.shape[1], view.shape[0])
            for track in current:
                quad = (track['current'].quad-np.float32([rx, ry])).astype(np.int32)
                color = (80, 220, 80) if track['match'] is not None else (60, 200, 220)
                cv2.polylines(debug_img, [quad], True, color, 2)
        with self._lock:
            self._matches[player] = display_match.as_dict() if display_match else None
            self._results[player] = {
                'present': bool(current), 'stable': bool(display and display['count'] >= int(config['stable_frames'])),
                'stable_frames': display['count'] if display else 0,
                'bbox': list(det.bbox) if det else None, 'area_frac': det.area_frac if det else None,
                'view_area_frac': det.view_area_frac if det else None,
                'ms': round((time.perf_counter()-t0)*1000, 1), 'match': self._matches[player],
                'candidates': len(current),
                'visible_cards': [t['match'].as_dict() for t in current if t['match'] is not None],
            }
            self._crops[player] = candidates[0][1] if candidates else None
            self._candidates[player] = candidates
            self._debug_imgs[player] = debug_img

    # ------------------------------------------------------------- legends

    def _check_legends(self, player: int, config: dict) -> None:
        """Classify each legend slot; on a settled flip to face-up, recognize the
        card (Legend cards only) and hand the finding to the app. A settled flip
        back to face-down is reported too (the app decides whether to hide)."""
        from app.vision.legends import (LEGEND_DETECTION, classify_legend_slot,
                                        legend_slot_crops, legend_slot_rects)
        frame, view = self.service.frame_and_view(player)
        if view is None:
            return
        region = detection_regions(self.service.store, player).get("legend_region")
        if not region:
            return
        region_key = repr(region)
        if self._legend_region_keys.get(player) != region_key:
            self._legend_region_keys[player] = region_key
            self._legend_state[player] = [
                {"face_up": False, "streak": 0, "handled": None} for _ in range(3)]
            with self._lock:
                self._legend_results[player] = [None, None, None]
        slot_detector = CardDetector({**config, **LEGEND_DETECTION})
        checks = max(1, int(config["legend_checks"]))
        selected_slot = (self._legend_ticks[player] // checks) % 3
        self._legend_ticks[player] += 1
        for slot, rect in enumerate(legend_slot_rects(region)):
            finding = classify_legend_slot(view, rect)
            state = self._legend_state[player][slot]
            face_up = bool(finding["face_up"])
            state["streak"] = state["streak"] + 1 if face_up == state["face_up"] else 1
            state["face_up"] = face_up
            match = None
            previous = self._legend_results[player][slot] or {}
            # Recheck every slot, including dark/yellow artwork and slots
            # already accepted. A color heuristic never vetoes recognition.
            state["checks"] = state.get("checks", 0) + 1
            attempted = slot == selected_slot and state["checks"] % checks == 0
            if attempted:
                crops = legend_slot_crops(self.service, frame, view, rect, slot_detector, player)
                match = self.service.recognize_crops(crops, card_type="Legend")
            accepted = match is not None and match.confidence >= float(self.service.recognition_config()["min_confidence"])
            if attempted:
                state['back_checks'] = state.get('back_checks', 0) + 1 if finding.get('back_visible') and not accepted else 0
            if accepted:
                state['handled'] = True
                finding['face_up'] = True
                if self.service.on_legend is not None:
                    self.service.on_legend(player, slot, True, match)
            # Only an explicit back appearance can hide an assigned legend;
            # darkness/absence/failed recognition are uncertainty, never flips.
            elif attempted and state.get('back_checks', 0) >= 2 and state.get('handled') is True:
                if self.service.on_legend is not None:
                    self.service.on_legend(player, slot, False, None)
                state['handled'] = False
            with self._lock:
                self._legend_results[player][slot] = {
                    **finding, 'streak': state['streak'],
                    'match': match.as_dict() if match else (None if attempted else previous.get('match')),
                    'checked': attempted, 'accepted': accepted if attempted else previous.get('accepted', False),
                }

    def legend_results(self) -> dict:
        with self._lock:
            return {str(p): [dict(r) if r else None for r in slots]
                    for p, slots in self._legend_results.items()}

    def _candidate_crops(self, frame, player: int, detections: list, rcfg: dict) -> list:
        """(label, crop) list to recognize: each candidate quad at native
        resolution, plus the halves of the best quad when enabled."""
        crops: list = []
        for i, det in enumerate(detections):
            crop = self.service.native_crop(frame, player, det.quad)
            crops.append((f"quad{i}", crop if crop is not None else det.crop))
        if detections and rcfg.get("try_splits", True):
            for label, half in split_quad(detections[0].quad):
                crop = self.service.native_crop(frame, player, half)
                if crop is not None:
                    crops.append((label, crop))
        return crops

    def recognize_now(self, player: int):
        """On-demand recognition of the current candidates (debug page)."""
        with self._lock:
            candidates = list(self._candidates.get(player) or [])
        if not candidates:
            return None
        match = self.service.recognize_crops(candidates)
        self.set_match(player, match)
        return match

    def set_match(self, player: int, match) -> None:
        """Record an on-demand recognition result so the debug page shows it."""
        with self._lock:
            self._matches[player] = match.as_dict() if match else None
            self._results[player]["match"] = self._matches[player]

    def results(self) -> dict:
        with self._lock:
            return {
                "fps": round(self.fps, 1),
                "config": dict(self.config),
                "recognition": self.service.recognition_config(),
                "recognizer_ready": bool(self.service.recognizer and self.service.recognizer.ready),
                "players": {str(p): dict(r) for p, r in self._results.items()},
                "legends": {str(p): [dict(r) if r else None for r in slots]
                            for p, slots in self._legend_results.items()},
            }

    def crop(self, player: int) -> Optional[np.ndarray]:
        with self._lock:
            crop = self._crops.get(player)
            return None if crop is None else crop.copy()

    def debug_image(self, player: int) -> Optional[np.ndarray]:
        with self._lock:
            img = self._debug_imgs.get(player)
            return None if img is None else img.copy()

    def bbox_quad(self, player: int) -> Optional[list]:
        with self._lock:
            result = self._results.get(player)
            return result["bbox"] if result and result["present"] else None

    def stop(self) -> None:
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout=3)
