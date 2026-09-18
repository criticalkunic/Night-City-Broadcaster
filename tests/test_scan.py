"""Table-scan tests: legend face-up classification + full scan_player pass."""
import cv2
import numpy as np
import pytest

from app.vision.calibration import CalibrationStore
from app.vision.card_detector import rectify_quad
from app.vision.perspective import rect_to_pixels
from app.vision.scan import classify_legend_slot, legend_slot_rects, scan_player

MAT = (40, 60, 35)  # dark green felt, BGR


def paint_yellow_back(view, rect):
    """Yellow striped card back covering ~all of the given normalized rect."""
    h, w = view.shape[:2]
    x, y, rw, rh = rect_to_pixels(rect, w, h)
    for i in range(0, rw, 8):
        color = (30, 200, 230) if (i // 8) % 2 == 0 else (10, 20, 30)  # yellow / dark
        view[y:y + rh, x + i:min(x + i + 8, x + rw)] = color


def paint_face_card(view, rect):
    """Bright non-yellow card face."""
    h, w = view.shape[:2]
    x, y, rw, rh = rect_to_pixels(rect, w, h)
    view[y:y + rh, x:x + rw] = (200, 190, 180)  # pale face
    cv2.rectangle(view, (x + 4, y + 4), (x + rw - 4, y + rh // 2), (160, 60, 200), -1)


def make_table(width=800, height=600):
    return np.full((height, width, 3), MAT, dtype=np.uint8)


RECT = {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.3}


def test_empty_slot():
    result = classify_legend_slot(make_table(), RECT)
    assert result["present"] is False
    assert result["face_up"] is False


def test_face_down_back():
    view = make_table()
    paint_yellow_back(view, RECT)
    result = classify_legend_slot(view, RECT)
    assert result["present"] is True
    assert result["face_up"] is False


def test_face_up_card():
    view = make_table()
    paint_face_card(view, RECT)
    result = classify_legend_slot(view, RECT)
    assert result["present"] is True
    assert result["face_up"] is True


def test_legend_slot_rects_split():
    region = {"x": 0.1, "y": 0.2, "width": 0.6, "height": 0.2}
    rects = legend_slot_rects(region)
    assert len(rects) == 3
    assert abs(rects[0]["width"] - 0.2) < 1e-9
    assert abs(rects[1]["x"] - 0.3) < 1e-9
    assert all(r["y"] == 0.2 and r["height"] == 0.2 for r in rects)


class FakeService:
    """Minimal stand-in for VisionService: fixed corrected view + store.
    The "raw frame" is the corrected view itself, so native crops are just
    rectified quads of the view."""

    def __init__(self, view, store):
        self.view = view
        self.store = store

    def render_view(self, name, rois=False):
        return self.view

    def frame_and_view(self, player):
        return self.view, self.view

    def native_crop(self, frame, player, quad):
        return None if frame is None else rectify_quad(frame, quad)

    def recognition_config(self):
        return {"candidates": 3, "try_splits": True}


def test_scan_player(tmp_path):
    store = CalibrationStore(tmp_path / "cameras.json", tmp_path / "regions.json")
    view = make_table()
    regions = store.player(1)["regions"]

    # Legend region: slot 0 face-up, slot 1 back, slot 2 empty.
    slots = legend_slot_rects(regions["legend_region"])
    paint_face_card(view, slots[0])
    paint_yellow_back(view, slots[1])

    # A card in the play region (card-shaped, so the detector finds it).
    play = regions["card_play_region"]
    h, w = view.shape[:2]
    px, py, pw, ph = rect_to_pixels(play, w, h)
    card_w, card_h = 90, 126
    cx, cy = px + pw // 2 - card_w // 2, py + ph // 2 - card_h // 2
    view[cy:cy + card_h, cx:cx + card_w] = (235, 235, 235)

    result = scan_player(FakeService(view, store), 1)
    assert result["ok"] is True
    assert result["legends"][0]["face_up"] is True
    assert result["legends"][1]["present"] is True and result["legends"][1]["face_up"] is False
    assert result["legends"][2]["present"] is False
    assert result["card_bbox"] is not None
    assert result["card_crop"].shape[0] > result["card_crop"].shape[1]  # portrait
    labels = [label for label, _ in result["card_crops"]]
    assert labels[0] == "quad0" and "split-top" in labels and "split-left" in labels
    assert all(crop.shape[:2] == (420, 300) for _, crop in result["card_crops"])
    # Face-up legend slot yields crop candidates; back / empty slots yield none.
    assert result["legend_crops"][0] and result["legend_crops"][0][-1][0] == "slot"
    assert all(crops and crops[-1][0] == "slot" for crops in result["legend_crops"])


def test_scan_player_no_frame(tmp_path):
    store = CalibrationStore(tmp_path / "cameras.json", tmp_path / "regions.json")
    result = scan_player(FakeService(None, store), 1)
    assert result["ok"] is False


@pytest.mark.parametrize("width,height", [(0.3, 0.9), (0.6, 0.6), (0.9, 0.3)])
def test_legend_slots_always_run_left_to_right(width, height):
    """Tall, square, and wide regions retain the same legend ordering."""
    region = {"x": 0.05, "y": 0.05, "width": width, "height": height}
    rects = legend_slot_rects(region)
    assert len(rects) == 3
    for i, rect in enumerate(rects):
        assert rect == pytest.approx({
            "x": region["x"] + i * width / 3,
            "y": region["y"],
            "width": width / 3,
            "height": height,
        })
