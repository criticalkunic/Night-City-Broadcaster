"""Milestone 3: card-shape detection tests on synthetic frames."""
import cv2
import numpy as np
import pytest

from app.vision.card_detector import CARD_ASPECT, CROP_SIZE, CardDetector, order_quad

ROI = {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8}


def make_view(with_card=True, angle=0.0, size=(120, 168), color=(230, 230, 230)):
    """640x480 dark felt view with an optional card-like rectangle."""
    view = np.full((480, 640, 3), (40, 60, 35), dtype=np.uint8)
    if with_card:
        rect = ((320, 240), size, angle)
        box = cv2.boxPoints(rect).astype(np.int32)
        cv2.fillConvexPoly(view, box, color)
        # Simple "art" so the crop is not uniform.
        cv2.circle(view, (320, 220), 30, (60, 160, 220), -1)
    return view


def test_order_quad():
    pts = np.array([[10, 100], [100, 100], [100, 10], [10, 10]], dtype=np.float32)
    ordered = order_quad(pts)
    assert (ordered[0] == [10, 10]).all()    # TL
    assert (ordered[1] == [100, 10]).all()   # TR
    assert (ordered[2] == [100, 100]).all()  # BR
    assert (ordered[3] == [10, 100]).all()   # BL


def detect(view, roi=ROI, config=None):
    detection, _ = CardDetector(config).detect(view, roi)
    return detection


def test_detects_card():
    detection = detect(make_view())
    assert detection is not None
    assert detection.crop.shape == (CROP_SIZE[1], CROP_SIZE[0], 3)
    # bbox centered around the card.
    x, y, w, h = detection.bbox
    assert 0.3 < x + w / 2 < 0.7
    assert 0.3 < y + h / 2 < 0.7


def test_detects_rotated_card():
    detection = detect(make_view(angle=25.0))
    assert detection is not None
    assert detection.crop.shape == (CROP_SIZE[1], CROP_SIZE[0], 3)


def test_landscape_card_normalized_to_portrait():
    detection = detect(make_view(size=(168, 120)))
    assert detection is not None
    assert detection.crop.shape[0] > detection.crop.shape[1]  # portrait


def test_no_card_no_detection():
    assert detect(make_view(with_card=False)) is None


def test_wrong_aspect_rejected():
    # A long thin strip is not card-shaped.
    assert detect(make_view(size=(200, 40))) is None


def test_card_outside_roi_ignored():
    view = make_view(with_card=False)
    box = cv2.boxPoints(((50, 50), (60, 84), 0.0)).astype(np.int32)
    cv2.fillConvexPoly(view, box, (230, 230, 230))
    tight_roi = {"x": 0.4, "y": 0.4, "width": 0.5, "height": 0.5}
    assert detect(view, tight_roi) is None


def test_min_area_threshold():
    assert detect(make_view(size=(60, 84)), config={"min_area_frac": 0.2}) is None


def test_detects_low_contrast_card():
    # Dark card on a dark mat: only slightly brighter than the background.
    detection = detect(make_view(color=(75, 95, 70)))
    assert detection is not None


def test_detects_card_with_busy_art():
    # Full-bleed noisy art breaks single clean contours; the min-area-rect
    # fallback must still find the card.
    view = make_view(with_card=False)
    rng = np.random.default_rng(42)
    art = rng.integers(90, 255, (168, 120, 3), dtype=np.uint8)
    view[156:324, 260:380] = art
    detection = detect(view)
    assert detection is not None
    x, y, w, h = detection.bbox
    assert 0.35 < x + w / 2 < 0.65


def test_debug_image_returned():
    detection, debug_img = CardDetector().detect(make_view(), ROI, debug=True)
    assert detection is not None
    assert debug_img is not None
    assert debug_img.ndim == 3


def test_picks_card_over_non_card_shape():
    # A square blob and a card in the same ROI: the card must win.
    view = make_view()
    cv2.rectangle(view, (100, 100), (180, 180), (220, 220, 220), -1)
    detection = detect(view)
    assert detection is not None
    x, y, w, h = detection.bbox
    assert 0.35 < x + w / 2 < 0.65  # centered on the card, not the square


def test_aspect_constant_sane():
    assert 0.7 < CARD_ASPECT < 0.75


def test_detect_all_returns_distinct_candidates():
    """Two separate cards in the ROI -> two candidates, best first, no duplicates."""
    view = np.full((600, 800, 3), (40, 60, 35), dtype=np.uint8)
    view[100:226, 100:190] = (235, 235, 235)
    view[300:426, 500:590] = (235, 235, 235)
    roi = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    detections, _ = CardDetector().detect_all(view, roi, max_candidates=3)
    assert len(detections) == 2
    centers = sorted((round(d.center[0], 1), round(d.center[1], 1)) for d in detections)
    assert centers == [(0.2, 0.3), (0.7, 0.6)]
    assert all(d.crop.shape[:2] == (420, 300) for d in detections)


def test_detect_all_allow_border_for_slots():
    """A card filling its slot touches 3+ edges; only allow_border accepts it."""
    view = np.full((600, 800, 3), (40, 60, 35), dtype=np.uint8)
    view[100:226, 100:190] = (235, 235, 235)
    # Slot exactly as wide as the card, a little taller: the card touches the
    # left, right and top slot edges (3 edges = "hugs border").
    slot = {"x": 100 / 800, "y": 100 / 600, "width": 90 / 800, "height": 140 / 600}
    detector = CardDetector({"max_area_frac": 0.98, "min_area_frac": 0.15})
    strict, _ = detector.detect_all(view, slot, max_candidates=1)
    loose, _ = detector.detect_all(view, slot, max_candidates=1, allow_border=True)
    assert strict == [] and len(loose) == 1


@pytest.mark.parametrize("angle", [0, 45, 60])
def test_curved_mat_blob_is_not_a_card(angle):
    view = make_view(with_card=False)
    cv2.ellipse(view, (320, 240), (60, 84), angle, 0, 360, (230, 230, 230), -1)
    assert detect(view) is None


def test_card_wins_over_card_aspect_mat_ellipse():
    view = make_view()
    cv2.ellipse(view, (160, 230), (45, 63), 45, 0, 360, (230, 230, 230), -1)
    candidates, _ = CardDetector().detect_all(view, ROI)
    assert candidates
    assert all(0.4 < candidate.center[0] < 0.6 for candidate in candidates)


def test_perspective_card_keeps_four_supported_edges():
    view = make_view(with_card=False)
    points = np.int32([[260, 145], [374, 163], [389, 320], [245, 335]])
    cv2.fillConvexPoly(view, points, (230, 230, 230))
    assert detect(view) is not None


def test_card_on_real_busy_mat_is_first_candidate():
    from pathlib import Path
    view = cv2.imread(str(Path(__file__).parent / "fixtures/busy-mat-card.png"))
    candidates, _ = CardDetector().detect_all(view, dict(x=0, y=0, width=1, height=1))
    assert candidates
    x, y, width, height = candidates[0].bbox
    assert abs(x - 248 / 650) < 0.02
    assert abs(y - 65 / 287) < 0.02
    assert abs(width - 103 / 650) < 0.03
    assert abs(height - 143 / 287) < 0.04


def test_full_webcam_board_recovers_both_play_cards(tmp_path):
    from pathlib import Path
    from app.vision.calibration import CalibrationStore
    from app.vision.frame_processor import VisionService
    frame = cv2.imread(str(Path(__file__).parent / "fixtures/legend-board.jpg"))
    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    view = VisionService(store, tmp_path / "captures")._corrected(frame, 1)
    region = dict(x=0.16254980079681275, y=0.21223404255319145,
                  width=0.7109561752988047, height=0.41826236806017286)
    candidates, _ = CardDetector().detect_all(view, region)
    assert any(0.29 < d.center[0] < 0.35 for d in candidates)  # Les Élémens
    assert any(0.47 < d.center[0] < 0.53 for d in candidates)  # All Is Lost


def test_removal_requires_sustained_valid_empty_frames(monkeypatch):
    from types import SimpleNamespace
    from app.vision.card_detector import DetectionWorker, DEFAULT_DETECTION
    from app.game.state_manager import StateManager
    from app.vision.recognizer import DEFAULT_RECOGNITION

    manager = StateManager()
    manager.set_latest_card(1, "card", "Card")
    now = [0.0]
    view = [make_view(False)]
    monkeypatch.setattr("app.vision.card_detector.time.monotonic", lambda: now[0])
    events = []
    def removed(player):
        event = manager.remove_detected_card(player)
        if event is not None:
            events.append(event)
    service = SimpleNamespace(
        frame_and_view=lambda player: (view[0], view[0]),
        store=SimpleNamespace(player=lambda player: {"regions": {"card_play_region": ROI}}),
        recognition_config=lambda: DEFAULT_RECOGNITION,
        on_play_region_empty=manager.observe_empty_play_region,
        on_card_removed=removed,
    )
    worker = DetectionWorker(service)
    config = dict(DEFAULT_DETECTION)
    for t in [0, .1, .2, .3, .4]:
        now[0] = t
        worker._process(1, config)
    assert manager.get_state().latest_cards["1"] is not None
    # Missing camera frames are not proof of removal and reset the timer.
    view[0] = None
    now[0] = 2
    worker._process(1, config)
    assert manager.get_state().latest_cards["1"] is not None
    view[0] = make_view(False)
    for t in [3, 3.3, 3.6, 3.9, 4.2, 4.5]:
        now[0] = t
        worker._process(1, config)
    assert manager.get_state().latest_cards["1"] is None
    assert len(events) == 1
    assert events[0].type == "card_removed"
    manager.undo()
    assert manager.get_state().latest_cards["1"].card_id == "card"
