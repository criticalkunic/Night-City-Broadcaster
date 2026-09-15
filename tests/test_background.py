from pathlib import Path

import cv2
import numpy as np

from app.vision.background import MatBackground
from app.vision.card_detector import CardDetector


def busy_mat():
    # Real playmat texture is the stationary background for this controlled
    # fixture. Only the added rectangle is a new object.
    return cv2.imread(str(Path(__file__).parent / 'fixtures/two-play-cards.png'))


def test_background_ignores_static_texture_and_finds_added_card(tmp_path):
    background = MatBackground(tmp_path / 'mat.npz')
    mat = busy_mat()
    background.capture(mat, 'camera-a')
    assert not background.foreground(mat, 'camera-a').any()
    brighter = cv2.convertScaleAbs(mat, alpha=1, beta=12)
    assert np.mean(background.foreground(brighter, 'camera-a') > 0) < .01
    frame = mat.copy()
    cv2.rectangle(frame, (570, 90), (680, 244), (100, 110, 150), -1)
    foreground = background.foreground(frame, 'camera-a')
    found, _ = CardDetector().detect_all(foreground, dict(x=0, y=0, width=1, height=1), max_candidates=8)
    assert len(found) == 1
    assert abs(found[0].center[0] - 625/frame.shape[1]) < .03
    assert not background.foreground(mat, 'camera-a').any(), 'Removed card must leave no foreground'


def test_reference_persists_and_rejects_changed_calibration(tmp_path):
    path = tmp_path / 'mat.npz'
    background = MatBackground(path)
    assert background.foreground(busy_mat(), 'a') is None
    background.capture(busy_mat(), 'a')
    loaded = MatBackground(path)
    assert loaded.status('a')['active']
    assert loaded.status('b')['saved'] and not loaded.status('b')['active']
    assert loaded.foreground(busy_mat(), 'b') is None
    loaded.clear()
    assert not path.exists()
    assert not loaded.status('a')['saved']
