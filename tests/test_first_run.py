import json
import pytest
from app.game.card_db import CardDatabase
from app.first_run import import_cards
from unittest.mock import Mock
import asyncio
import cv2
import numpy as np
from app.first_run import ArtworkSetup, ArtworkGate


def setup(tmp_path):
    images=tmp_path/'images';images.mkdir(exist_ok=True)
    path=tmp_path/'cards.json'
    if not path.exists():path.write_text(json.dumps([{'id':'a','image':'/cards/images/a.webp'}]))
    db=CardDatabase(path)
    downloader=Mock();downloader.status.return_value={'errors':[], 'completed':0}
    recognizer=Mock(ready=True)
    return ArtworkSetup(db, images, recognizer, downloader)


def write_art(s):
    cv2.imwrite(str(s.images/'a.webp'),np.zeros((20,20,3),np.uint8))


def test_missing_and_corrupt_art_stay_locked(tmp_path):
    s=setup(tmp_path);assert not s.ready
    (s.images/'a.webp').write_bytes(b'broken');s.run()
    assert not s.ready and s.error
    assert s.pending.exists()


def test_partial_failure_survives_restart_then_retry_unlocks(tmp_path):
    s=setup(tmp_path);write_art(s)
    s.downloader.status.return_value={'errors':['alternate art failed']};s.run()
    assert not s.ready
    s=setup(tmp_path);assert not s.ready
    s.run();assert s.ready and not s.pending.exists()
    assert setup(tmp_path).ready


def test_gate_blocks_api_websocket_and_ui(tmp_path):
    s=setup(tmp_path)
    async def app(scope,receive,send):
        await send({'type':'allowed'})
    gate=ArtworkGate(app,s)
    async def check(path,kind='http'):
        messages=[]
        async def send(message):messages.append(message)
        await gate({'type':kind,'path':path},None,send)
        return messages
    assert asyncio.run(check('/api/vision/start'))[0]['status']==503
    assert asyncio.run(check('/operator'))[0]['status']==307
    assert asyncio.run(check('/ws','websocket'))[0]['type']=='websocket.close'
    assert asyncio.run(check('/api/first-run/status'))[0]['type']=='allowed'
    s.ready=True
    assert asyncio.run(check('/api/vision/start'))[0]['type']=='allowed'


@pytest.fixture(autouse=True)
def online_catalog(monkeypatch):
    from app import first_run
    monkeypatch.setattr(first_run, 'has_card_back', lambda images: True)
    monkeypatch.setattr(first_run, 'ensure_card_back', lambda images: None)
    monkeypatch.setattr(import_cards, 'fetch_netdeck_items', lambda: [])
    monkeypatch.setattr(import_cards, 'transform_items', lambda _: [{'id':'a','image':'/cards/images/a.webp'}])


def test_bootstrap_without_catalog_uses_dynamic_total(tmp_path, monkeypatch):
    s=setup(tmp_path)
    s.database.path.unlink();s.database.reload()
    assert not s.database.cards
    cards=[{'id':str(i),'image':f'/cards/images/{i}.webp'} for i in range(163)]
    monkeypatch.setattr(import_cards,'transform_items',lambda _: cards)
    def download(cards, recognizer, online):
        assert len(online)==163
        for card in cards:
            cv2.imwrite(str(s.images/Path(card['image']).name),np.zeros((20,20,3),np.uint8))
    from pathlib import Path
    s.downloader.run.side_effect=download
    s.run()
    assert s.ready and s.status()['total']==163
    assert len(json.loads(s.database.path.read_text()))==163


def test_failed_catalog_fetch_does_not_replace_saved_catalog(tmp_path,monkeypatch):
    s=setup(tmp_path);original=s.database.path.read_bytes()
    monkeypatch.setattr(import_cards,'fetch_netdeck_items',Mock(side_effect=RuntimeError('offline')))
    s.run()
    assert not s.ready and s.database.path.read_bytes()==original
    s.downloader.run.assert_not_called()


def test_first_launch_unicode_catalog_on_windows_locale(tmp_path, monkeypatch):
    from pathlib import Path
    original_open = Path.open
    def windows_open(self, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
        if 'b' not in mode and encoding is None:
            encoding = 'cp1252'
        return original_open(self, mode, buffering, encoding, errors, newline)
    monkeypatch.setattr(Path, 'open', windows_open)
    s = setup(tmp_path)
    s.database.path.unlink()
    s.database.reload()
    monkeypatch.setattr(import_cards, 'transform_items', lambda _: [
        {'id': 'a', 'name': 'Star ☆ — Álvarez 日本', 'image': '/cards/images/a.webp'}])
    s.downloader.run.side_effect = lambda *a, **kw: write_art(s)
    s.run()
    assert s.ready, s.error
    assert CardDatabase(s.database.path).get('a')['name'] == 'Star ☆ — Álvarez 日本'
    assert '☆' in s.database.path.read_bytes().decode('utf-8')
