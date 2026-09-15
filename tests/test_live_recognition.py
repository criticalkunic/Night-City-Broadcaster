"""DetectionWorker -> recognizer -> on_recognized hand-off (Milestone 4 live path)."""
import numpy as np

from app.vision.calibration import CalibrationStore
from app.vision.card_detector import DEFAULT_DETECTION, DetectionWorker
from app.vision.perspective import rect_to_pixels
from app.vision.recognizer import Match


def _table_with_card(store: CalibrationStore, player: int = 1) -> np.ndarray:
    view = np.full((600, 800, 3), (40, 60, 35), dtype=np.uint8)
    play = store.player(player)["regions"]["card_play_region"]
    px, py, pw, ph = rect_to_pixels(play, 800, 600)
    cx, cy = px + pw // 2 - 45, py + ph // 2 - 63
    view[cy:cy + 126, cx:cx + 90] = (235, 235, 235)
    return view


class FakeRecognizer:
    ready = True


class FakeService:
    running = True
    paused = False

    def __init__(self, store, match, min_confidence=0.45, auto_apply=True):
        self.store = store
        self.match = match
        self.recognizer = FakeRecognizer()
        self.applied = []
        self.recognize_calls = 0
        self._cfg = {"min_confidence": min_confidence, "auto_apply": auto_apply,
                     "candidates": 3, "try_splits": True}
        self.on_recognized = lambda player, m: self.applied.append((player, m.card_id))
        self.view = _table_with_card(store)

    def render_view(self, name, rois=False):
        return self.view

    def frame_and_view(self, player):
        return self.view, self.view

    def native_crop(self, frame, player, quad):
        from app.vision.card_detector import rectify_quad
        return rectify_quad(frame, quad)

    def recognition_config(self):
        return dict(self._cfg)

    def recognize_crops(self, crops, card_type=None):
        self.recognize_calls += 1
        self.last_labels = [label for label, _ in crops]
        assert all(c is not None and c.shape[:2] == (420, 300) for _, c in crops)
        return self.match


def _match(conf: float) -> Match:
    return Match(card_id="cb-x", name="X", subtitle="", image="/cards/images/x.webp",
                 confidence=conf, inliers=30, thumb_score=0.8, rotated=False, card_type="Unit")


def _run(service, frames: int) -> DetectionWorker:
    worker = DetectionWorker(service, {"stable_frames": 3})
    config = {**DEFAULT_DETECTION, "stable_frames": 3}
    worker.detector.config = config
    for _ in range(frames):
        worker._process(1, config)
    return worker


def test_stable_card_is_recognized_once_and_applied(tmp_path):
    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    service = FakeService(store, _match(0.9))
    worker = _run(service, frames=8)
    assert service.recognize_calls == 1          # once per stable episode, not per frame
    assert service.applied == [(1, "cb-x")]
    assert service.last_labels == ["quad0"]  # recognize each actual card, not arbitrary halves
    result = worker.results()["players"]["1"]
    assert result["stable"] is True
    assert result["match"]["card_id"] == "cb-x" and result["match"]["confidence"] == 0.9


def test_low_confidence_is_reported_not_applied(tmp_path):
    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    service = FakeService(store, _match(0.2))
    worker = _run(service, frames=5)
    assert service.recognize_calls == 1
    assert service.applied == []
    assert worker.results()["players"]["1"]["match"]["confidence"] == 0.2


def test_auto_apply_off(tmp_path):
    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    service = FakeService(store, _match(0.95), auto_apply=False)
    _run(service, frames=5)
    assert service.recognize_calls == 1 and service.applied == []


def test_match_cleared_when_card_leaves(tmp_path):
    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    service = FakeService(store, _match(0.9))
    worker = _run(service, frames=4)
    assert worker.results()["players"]["1"]["match"] is not None
    service.view = np.full((600, 800, 3), (40, 60, 35), dtype=np.uint8)  # card removed
    worker._process(1, {**DEFAULT_DETECTION, "stable_frames": 3})
    assert worker.results()["players"]["1"]["match"] is None
    assert worker.results()["players"]["1"]["present"] is False


def test_no_recognizer_index_is_harmless(tmp_path):
    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    service = FakeService(store, None)
    worker = _run(service, frames=5)
    assert service.applied == []
    assert worker.results()["players"]["1"]["match"] is None


# ------------------------------------------------------------- live legends

from tests.test_scan import legend_slot_rects, paint_face_card, paint_yellow_back


def _legend_service(tmp_path, match, face_up_slots=(0,), back_slots=(1,)):
    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    service = FakeService(store, match)
    service.legend_events = []
    service.on_legend = lambda p, s, up, m: service.legend_events.append((p, s, up, m.card_id if m else None))
    view = np.full((600, 800, 3), (40, 60, 35), dtype=np.uint8)
    slots = legend_slot_rects(store.player(1)["regions"]["legend_region"])
    for i in face_up_slots:
        paint_face_card(view, slots[i])
    for i in back_slots:
        paint_yellow_back(view, slots[i])
    service.view = view
    recognize = service.recognize_crops
    def recognize_legend(crops, card_type=None):
        result = recognize(crops, card_type)
        # The stub must not claim every blank mat and yellow back is a card.
        return result if any(float(crop[:,:,0].mean()) > 90 for _,crop in crops) else None
    service.recognize_crops = recognize_legend
    return service


def test_legend_flip_up_recognized_once(tmp_path):
    service = _legend_service(tmp_path, _match(0.9))
    worker = DetectionWorker(service, {"legend_checks": 2})
    config = {**DEFAULT_DETECTION, "legend_checks": 2}
    worker._check_legends(1, config)
    assert service.legend_events == []                 # one check is not settled yet
    worker._check_legends(1, config)
    assert service.legend_events == [(1, 0, True, "cb-x")]
    worker._check_legends(1, config)
    assert len(service.legend_events) == 1             # no repeat while it stays up
    legends = worker.results()["legends"]["1"]
    assert legends[0]["face_up"] is True and legends[0]["match"]["card_id"] == "cb-x"
    assert legends[1]["present"] is True and legends[1]["face_up"] is False
    assert legends[2]["present"] is False


def test_legend_flip_down_needs_long_streak(tmp_path):
    service = _legend_service(tmp_path, _match(0.9))
    worker = DetectionWorker(service, {"legend_checks": 2})
    config = {**DEFAULT_DETECTION, "legend_checks": 2}
    for _ in range(2):
        worker._check_legends(1, config)
    assert service.legend_events[-1] == (1, 0, True, "cb-x")
    # Cover slot 0 with the back for a few checks: needs 5 before reporting.
    slots = legend_slot_rects(service.store.player(1)["regions"]["legend_region"])
    paint_yellow_back(service.view, slots[0])
    for _ in range(4):
        worker._check_legends(1, config)
    assert len(service.legend_events) == 1
    for _ in range(8):
        worker._check_legends(1, config)
    assert service.legend_events[-1] == (1, 0, False, None)


def test_play_region_must_be_empty_for_stable_frames_before_arming(tmp_path):
    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    service = FakeService(store, _match(0.9))
    observed = []
    service.on_play_region_empty = lambda: observed.append(True)
    worker = _run(service, frames=5)
    assert not observed
    service.view = np.full((600, 800, 3), (40, 60, 35), dtype=np.uint8)
    config = {**DEFAULT_DETECTION, "stable_frames": 3}
    for _ in range(2):
        worker._process(1, config)
    assert not observed
    worker._process(1, config)
    assert observed == [True]


def test_disappearing_card_clears_crop_and_manual_candidates(tmp_path):
    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    service = FakeService(store, _match(0.9))
    worker = _run(service, frames=5)
    assert worker.crop(1) is not None
    service.view = np.full((600, 800, 3), (40, 60, 35), dtype=np.uint8)
    worker._process(1, DEFAULT_DETECTION)
    assert worker.crop(1) is None
    assert worker.recognize_now(1) is None


def test_weak_legend_retries_and_later_confident_match_applies(tmp_path):
    service = _legend_service(tmp_path, _match(0.05))
    worker = DetectionWorker(service)
    for _ in range(6):
        worker._check_legends(1, DEFAULT_DETECTION)
    first_calls = service.recognize_calls
    service.match = _match(0.9)
    for _ in range(6):
        worker._check_legends(1, DEFAULT_DETECTION)
    assert service.recognize_calls > first_calls
    assert worker.legend_results()["1"][0]["match"]["confidence"] == 0.9
    calls = service.recognize_calls
    for _ in range(6):
        worker._check_legends(1, DEFAULT_DETECTION)
    assert service.recognize_calls > calls  # accepted slots still get rechecked


def test_recalibration_rechecks_previously_recognized_legends(tmp_path):
    service = _legend_service(tmp_path, _match(0.9))
    worker = DetectionWorker(service)
    for _ in range(2):
        worker._check_legends(1, DEFAULT_DETECTION)
    calls = service.recognize_calls
    service.store.player(1)["regions"]["legend_region"]["x"] += 0.001
    for _ in range(2):
        worker._check_legends(1, DEFAULT_DETECTION)
    assert service.recognize_calls > calls


def test_card_retries_when_index_was_not_ready_at_first_detection(tmp_path):
    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    service = FakeService(store, None)
    worker = _run(service, frames=8)
    assert service.recognize_calls == 1
    service.match = _match(0.9)
    for track in worker._play[1].tracks:
        track["checked"] = -1e9
    worker._process(1, {**DEFAULT_DETECTION, "stable_frames": 3})
    assert service.applied == [(1, "cb-x")]
    assert worker.results()["players"]["1"]["match"]["confidence"] == 0.9
    worker._process(1, {**DEFAULT_DETECTION, "stable_frames": 3})
    assert service.recognize_calls == 2


def test_lost_camera_frame_clears_previous_crop(tmp_path):
    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    service = FakeService(store, _match(0.9))
    worker = _run(service, frames=5)
    service.view = None
    worker._process(1, DEFAULT_DETECTION)
    assert worker.crop(1) is None
    assert worker.recognize_now(1) is None
    assert not worker.results()["players"]["1"]["present"]


def test_same_card_after_empty_gate_is_published(tmp_path):
    store = CalibrationStore(tmp_path / 'c.json', tmp_path / 'r.json')
    service = FakeService(store, _match(.9))
    armed = []
    published = []
    service.on_play_region_empty = lambda: armed.append(True)
    service.on_recognized = lambda p, m: published.append(m.card_id) if armed else None
    worker = _run(service, 5)
    assert published == []
    config = {**DEFAULT_DETECTION, 'stable_frames': 3}
    service.view = np.full((600, 800, 3), (40, 60, 35), dtype=np.uint8)
    for _ in range(3):
        worker._process(1, config)
    service.view = _table_with_card(store)
    for _ in range(5):
        worker._process(1, config)
    assert published == ['cb-x']


def test_explicit_reset_rechecks_card_without_moving_it(tmp_path):
    store = CalibrationStore(tmp_path / 'c.json', tmp_path / 'r.json')
    service = FakeService(store, _match(.9))
    worker = _run(service, 5)
    previous = worker._play[1]
    worker.request_play_reset()
    assert worker._play[1] is previous  # API thread only requests, worker owns tracks.
    config = {**DEFAULT_DETECTION, 'stable_frames': 3}
    for _ in range(5):
        worker._process(1, config)
    assert service.applied == [(1, 'cb-x'), (1, 'cb-x')]
    assert worker._play[1] is not previous


def test_rejected_mat_rectangles_do_not_block_first_play(tmp_path):
    store = CalibrationStore(tmp_path / 'c.json', tmp_path / 'r.json')
    service = FakeService(store, _match(.05))
    armed = []
    published = []
    service.on_play_region_empty = lambda: armed.append(True)
    service.on_recognized = lambda p, m: published.append(m.card_id) if armed else None
    worker = _run(service, 8)
    assert armed
    assert published == []
    service.match = _match(.95)
    for track in worker._play[1].tracks:
        track['checked'] = -1e9
    worker._process(1, {**DEFAULT_DETECTION, 'stable_frames': 3})
    assert published == ['cb-x']


def test_unchecked_or_confident_cards_do_not_auto_arm(tmp_path):
    store = CalibrationStore(tmp_path / 'c.json', tmp_path / 'r.json')
    for match in (None, _match(.95)):
        service = FakeService(store, match)
        armed = []
        service.on_play_region_empty = lambda: armed.append(True)
        _run(service, 8)
        assert not armed


def test_saved_background_is_never_used_for_detection(tmp_path):
    from unittest.mock import Mock
    store = CalibrationStore(tmp_path / 'c.json', tmp_path / 'r.json')
    service = FakeService(store, _match(.95))
    service.play_foreground = Mock(side_effect=AssertionError('Background feature removed'))
    _run(service, 8)
    service.play_foreground.assert_not_called()
    assert service.applied == [(1, 'cb-x')]
