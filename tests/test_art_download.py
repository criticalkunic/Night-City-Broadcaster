from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np

from app.game.art_download import ArtDownload, import_cards, import_printings


def test_download_repairs_missing_and_preserves_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(import_cards, 'IMAGES_DIR', tmp_path)
    cards = [dict(id='a', name='A', image='/cards/images/a.webp'),
             dict(id='b', name='B', image='/cards/images/b.webp')]
    existing = cv2.imencode('.webp', np.full((20,20,3), 120, np.uint8))[1].tobytes()
    (tmp_path/'b.webp').write_bytes(existing)
    monkeypatch.setattr(import_cards, 'fetch_netdeck_items', lambda: [])
    monkeypatch.setattr(import_cards, 'transform_items', lambda _: [dict(id='a', _image_url='image')])
    data = cv2.imencode('.webp', np.zeros((20,20,3), np.uint8))[1].tobytes()
    fetch = Mock(return_value=data)
    monkeypatch.setattr(import_cards, '_get', fetch)
    monkeypatch.setattr(import_printings, 'import_card_printings', lambda _: {'added': 0})
    recognizer = Mock()
    job = ArtDownload()
    job.run(cards, recognizer)
    assert (tmp_path/'a.webp').read_bytes() == data
    assert (tmp_path/'b.webp').read_bytes() == existing
    assert job.status()['downloaded'] == 1
    assert job.status()['errors'] == []
    recognizer.build.assert_called_once()
    fetch.assert_called_once()


def test_network_failure_releases_job(monkeypatch):
    monkeypatch.setattr(import_cards, 'fetch_netdeck_items', Mock(side_effect=RuntimeError('offline')))
    job = ArtDownload()
    job.update(running=True)
    recognizer = Mock()
    job.run([], recognizer)
    assert not job.status()['running']
    assert job.status()['errors'] == ['offline']
    recognizer.build.assert_not_called()


def test_duplicate_download_does_not_start():
    job = ArtDownload()
    job.update(running=True)
    assert job.start(SimpleNamespace(cards=[]), Mock()) is False
