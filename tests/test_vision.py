"""Vision pipeline tests: perspective math, calibration store, capture + views."""
import time

import cv2
import numpy as np
import pytest

from app.vision.calibration import DEFAULT_REGIONS, CalibrationStore
from app.vision.capture import CaptureThread
from app.vision.frame_processor import VIEWS, VisionService
from app.vision.perspective import clamp01, crop_rect, rect_to_pixels, warp_quad


# ------------------------------------------------------------- perspective

def test_clamp01():
    assert clamp01(-0.5) == 0.0
    assert clamp01(1.5) == 1.0
    assert clamp01(0.25) == 0.25


def test_rect_to_pixels():
    rect = {"x": 0.5, "y": 0.0, "width": 0.5, "height": 1.0}
    assert rect_to_pixels(rect, 1920, 1080) == (960, 0, 960, 1080)


def test_rect_to_pixels_clamps_overflow():
    rect = {"x": 0.9, "y": 0.9, "width": 0.5, "height": 0.5}
    x, y, w, h = rect_to_pixels(rect, 100, 100)
    assert x + w <= 100 and y + h <= 100
    assert w >= 1 and h >= 1


def test_crop_rect():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[:, 100:] = 255
    right = crop_rect(frame, {"x": 0.5, "y": 0.0, "width": 0.5, "height": 1.0})
    assert right.shape == (100, 100, 3)
    assert right.min() == 255


def test_warp_quad_identity():
    image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    points = [[0, 0], [1, 0], [1, 1], [0, 1]]
    warped = warp_quad(image, points, (100, 100))
    assert warped.shape == image.shape
    # Identity homography: images match (borders may interpolate slightly).
    assert np.abs(warped[5:-5, 5:-5].astype(int) - image[5:-5, 5:-5].astype(int)).mean() < 2


def test_warp_quad_output_size():
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    points = [[0.1, 0.1], [0.9, 0.15], [0.85, 0.9], [0.12, 0.88]]
    warped = warp_quad(image, points, (800, 600))
    assert warped.shape == (600, 800, 3)


# ------------------------------------------------------------- calibration

@pytest.fixture
def store(tmp_path):
    return CalibrationStore(tmp_path / "cameras.json", tmp_path / "regions.json")


def test_calibration_defaults(store):
    assert store.regions["player1"]["source_rect"]["width"] == 1.0
    assert store.regions["player2"]["source_rect"]["x"] == 0.5
    assert "card_play_region" in store.regions["player1"]["regions"]
    assert store.corrected_size == (800, 600)


def test_calibration_roundtrip(store, tmp_path):
    regions = {
        "player1": {
            "source_rect": {"x": 0.1, "y": 0.05, "width": 0.4, "height": 0.9},
            "homography_points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
            "regions": {"card_play_region": {"x": 0.2, "y": 0.2, "width": 0.3, "height": 0.3}},
        }
    }
    store.save_regions(regions)
    reloaded = CalibrationStore(tmp_path / "cameras.json", tmp_path / "regions.json")
    p1 = reloaded.regions["player1"]
    assert p1["source_rect"]["x"] == 0.1
    assert p1["homography_points"][2] == [0.9, 0.9]
    assert p1["regions"]["card_play_region"]["width"] == 0.3
    # Unspecified regions fall back to defaults, player2 fully defaulted.
    assert "gig_region" in p1["regions"]
    assert reloaded.regions["player2"]["source_rect"]["x"] == 0.5


def test_calibration_clamps_out_of_range(store):
    saved = store.save_regions({
        "player1": {"source_rect": {"x": -1, "y": 2, "width": 5, "height": 0.5},
                    "homography_points": [[2, 2], [-1, 0], [1, 1], [0, 1]]}
    })
    rect = saved["player1"]["source_rect"]
    assert rect["x"] == 0.0 and rect["y"] == 1.0 and rect["width"] == 1.0
    assert saved["player1"]["homography_points"][0] == [1.0, 1.0]


def test_calibration_rejects_bad_homography(store):
    saved = store.save_regions({"player1": {"homography_points": [[0, 0], [1, 1]]}})
    assert saved["player1"]["homography_points"] is None


# --------------------------------------------------------- capture + views

@pytest.fixture(scope="module")
def sample_video(tmp_path_factory):
    path = tmp_path_factory.mktemp("video") / "sample.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (320, 180))
    assert writer.isOpened(), "MJPG VideoWriter unavailable"
    for i in range(30):
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[:, :160] = (0, 128, 0)
        frame[:, 160:] = (128, 0, 0)
        cv2.putText(frame, str(i), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()
    return path


def _wait_for_frame(capture, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        frame, seq = capture.latest()
        if frame is not None:
            return frame
        time.sleep(0.05)
    raise AssertionError("no frame captured within timeout")


def test_capture_video_file(sample_video):
    cap = CaptureThread({"type": "video", "path": str(sample_video)})
    cap.start()
    try:
        frame = _wait_for_frame(cap)
        assert frame.shape == (180, 320, 3)
        assert cap.resolution == (320, 180)
        assert cap.error is None
    finally:
        cap.stop()
    assert not cap.is_alive()


def test_capture_missing_video_errors(tmp_path):
    cap = CaptureThread({"type": "video", "path": str(tmp_path / "nope.avi")})
    cap.start()
    cap.join(timeout=3)
    assert not cap.is_alive()
    assert cap.error


def test_vision_service_views(sample_video, tmp_path):
    store = CalibrationStore(tmp_path / "cameras.json", tmp_path / "regions.json")
    service = VisionService(store, tmp_path / "captures")
    service.start({"type": "video", "path": str(sample_video)})
    try:
        _wait_for_frame(service.capture)
        status = service.status()
        assert status["running"] is True

        raw = service.render_view("raw")
        assert raw.shape == (180, 320, 3)
        p1 = service.render_view("p1_crop")
        assert p1.shape == (180, 320, 3)
        # The solo crop includes both halves of the full webcam frame.
        assert p1[:, :150, 1].mean() > p1[:, :150, 0].mean()
        assert p1[:, 170:, 0].mean() > p1[:, 170:, 1].mean()
        corrected = service.render_view("p1_corrected")
        assert corrected.shape == (600, 800, 3)
        with_rois = service.render_view("p1_corrected", rois=True)
        assert with_rois.shape == (600, 800, 3)

        jpeg = service.jpeg("raw")
        assert jpeg[:2] == b"\xff\xd8"  # JPEG magic

        # Homography kicks in once points exist.
        store.save_regions({
            "player1": {"homography_points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]}
        })
        warped = service.render_view("p1_corrected")
        assert warped.shape == (600, 800, 3)

        saved = service.save_frame("raw")
        assert saved.exists()

        service.pause()
        assert service.status()["paused"] is True
        frozen1 = service.jpeg("raw")
        frozen2 = service.jpeg("raw")
        assert frozen1 == frozen2  # frame frozen while paused
        service.resume()
        assert service.status()["paused"] is False
    finally:
        service.stop()
    assert service.status()["running"] is False


def test_vision_service_placeholder_without_source(tmp_path):
    store = CalibrationStore(tmp_path / "cameras.json", tmp_path / "regions.json")
    service = VisionService(store, tmp_path / "captures")
    assert service.render_view("raw") is None
    jpeg = service.jpeg("raw")  # placeholder image, not an error
    assert jpeg[:2] == b"\xff\xd8"
    with pytest.raises(ValueError):
        service.save_frame("raw")


def test_views_constant():
    assert set(VIEWS) == {"raw", "p1_crop", "p2_crop", "p1_corrected", "p2_corrected"}


# ---------------------------------------------------------------- M4 native crops

def test_corrected_to_raw_roundtrip_homography(tmp_path):
    """Corrected-view pixels map back onto the raw frame through the inverse
    homography; a card drawn in the raw frame comes out as a clean crop."""
    import numpy as np
    from app.vision.calibration import CalibrationStore
    from app.vision.frame_processor import VisionService
    from app.vision.perspective import rect_to_pixels

    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    store.save_cameras({**store.cameras, "corrected_size": [400, 300]})
    store.save_regions({**store.regions, "player1": {
        **store.player(1),
        "source_rect": {"x": 0.1, "y": 0.0, "width": 0.5, "height": 1.0},
        "homography_points": [[0.1, 0.1], [0.9, 0.15], [0.85, 0.95], [0.12, 0.9]],
    }})
    service = VisionService(store, tmp_path)
    frame = np.full((720, 1280, 3), (40, 60, 35), dtype=np.uint8)
    # Card in raw-frame pixels inside P1's source rect.
    frame[300:426, 400:490] = (230, 230, 230)
    frame[310:340, 410:480] = (30, 30, 200)  # blue stripe near the "top"

    view = service._corrected(frame, 1)
    # Locate the card in the corrected view and map its bbox corners back.
    ys, xs = np.where(view[:, :, 0] > 200)
    quad = np.float32([[xs.min(), ys.min()], [xs.max(), ys.min()], [xs.max(), ys.max()], [xs.min(), ys.max()]])
    raw = service.corrected_to_raw(frame.shape, 1, quad)
    assert abs(raw[:, 0].min() - 400) < 6 and abs(raw[:, 0].max() - 490) < 6
    assert abs(raw[:, 1].min() - 300) < 6 and abs(raw[:, 1].max() - 426) < 6

    crop = service.native_crop(frame, 1, quad)
    assert crop.shape[:2] == (420, 300)
    # The blue stripe is in the crop, near one of the short edges.
    blue = (crop[:, :, 2] > 150) & (crop[:, :, 0] < 90)
    assert blue.mean() > 0.03
    rows = np.where(blue.any(axis=1))[0]
    assert rows.min() < 60 or rows.max() > 360


def test_corrected_to_raw_letterbox(tmp_path):
    import numpy as np
    from app.vision.calibration import CalibrationStore
    from app.vision.frame_processor import VisionService

    store = CalibrationStore(tmp_path / "c.json", tmp_path / "r.json")
    store.save_regions({**store.regions, "player1": {
        **store.player(1),
        "source_rect": {"x": 0.0, "y": 0.0, "width": 0.5, "height": 1.0},
        "homography_points": None,
    }})
    service = VisionService(store, tmp_path)
    frame = np.zeros((600, 1600, 3), dtype=np.uint8)   # source crop 800x600 -> fits 800x600 exactly
    pts = service.corrected_to_raw(frame.shape, 1, np.float32([[0, 0], [800, 600]]))
    assert np.allclose(pts, [[0, 0], [800, 600]], atol=1)


def test_split_quad_halves():
    import numpy as np
    from app.vision.card_detector import split_quad
    quad = np.float32([[0, 0], [100, 0], [100, 200], [0, 200]])
    halves = dict(split_quad(quad))
    assert set(halves) == {"split-top", "split-bottom", "split-left", "split-right"}
    assert np.allclose(halves["split-top"], [[0, 0], [100, 0], [100, 100], [0, 100]])
    assert np.allclose(halves["split-right"], [[50, 0], [100, 0], [100, 200], [50, 200]])
