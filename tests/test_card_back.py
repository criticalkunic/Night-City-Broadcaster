import cv2
import numpy as np
import pytest
from app.game import card_back
from app.first_run import ArtworkSetup
from unittest.mock import Mock


def test_download_crops_surround_and_reuses_cache(tmp_path, monkeypatch):
    scan = np.full((750, 600, 3), 255, np.uint8)
    scan[90:660, 96:508] = (0, 255, 255)
    ok, data = cv2.imencode('.webp', scan)
    download = Mock(return_value=data.tobytes())
    monkeypatch.setattr(card_back.import_cards, '_get', download)
    images = tmp_path/'images'
    card_back.ensure_card_back(images)
    assert cv2.imread(str(card_back.card_back_path(images))).shape[:2] == (570, 412)
    card_back.ensure_card_back(images)
    download.assert_called_once()


def test_bad_source_not_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(card_back.import_cards, '_get', lambda _: b'not an image')
    with pytest.raises(ValueError): card_back.ensure_card_back(tmp_path/'images')
    assert not card_back.has_card_back(tmp_path/'images')


def test_missing_back_locks_existing_install(tmp_path):
    images = tmp_path/'images';images.mkdir()
    cv2.imwrite(str(images/'a.webp'), np.zeros((20,20,3),np.uint8))
    database = Mock(cards=[{'image':'/cards/images/a.webp'}])
    setup = ArtworkSetup(database, images, Mock(), Mock())
    assert not setup.ready and setup.pending.exists()
