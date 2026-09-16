"""Printing artwork survives recognition/state; presentation remains a preference."""
from types import SimpleNamespace
import cv2
import numpy as np
from app import runtime
from app.api import cameras, state as state_api
from app.game.state_manager import StateManager
from app.vision.recognizer import CardRecognizer, Match

CANON = '/cards/images/example.webp'
ALT = '/cards/images/recognition/example/official-alt.png'


def test_recognizer_preserves_official_printing_but_not_camera_sample(tmp_path):
    rng = np.random.default_rng(42)
    images = [rng.integers(0, 256, (420, 300, 3), dtype=np.uint8) for _ in range(3)]
    folder = tmp_path / 'recognition' / 'example'
    folder.mkdir(parents=True)
    for path, image in zip([tmp_path/'example.webp', folder/'official-alt.png', folder/'camera.png'], images):
        assert cv2.imwrite(str(path), image)
    rec = CardRecognizer(SimpleNamespace(cards=[{'id': 'example', 'image': CANON}]), tmp_path)
    rec.build()
    for image, expected in zip(images, [CANON, ALT, CANON]):
        match = rec.recognize(image)
        assert match.card_id == 'example'
        assert match.matched_image == expected
        assert match.image == CANON
        assert match.as_dict()['matched_image'] == expected


def test_toggle_and_vision_state(monkeypatch):
    manager = StateManager()
    monkeypatch.setattr(runtime, 'state_manager', manager)
    monkeypatch.setattr(runtime, 'card_db', SimpleNamespace(get=lambda _: {'image': CANON}))
    match = Match('example', 'Example', '', CANON, .95, 50, .9, False, matched_image=ALT)
    cameras.apply_latest_card_match(1, match)
    cameras.apply_legend_match(1, 0, match)
    for enabled, expected in [(False, CANON), (True, ALT), (False, CANON)]:
        monkeypatch.setattr(runtime, 'load_overlay_config', lambda: {'show_matched_art': enabled})
        snapshot = runtime.snapshot_payload()['state']
        assert snapshot['latest_cards']['1']['image'] == expected
        assert snapshot['legends']['1'][0]['image'] == expected
        assert manager.get_state().latest_cards['1'].image == CANON
    assert cameras.apply_latest_card_match(1, match) is None
    before = manager.history_info()['card_undo_count']
    match.matched_image = CANON
    assert cameras.apply_latest_card_match(1, match) is not None
    assert manager.history_info()['card_undo_count'] == before


def test_moves_manual_selection_and_undo_preserve_art():
    manager = StateManager()
    manager.observe_legend(1, 0, 'example', image=CANON, matched_image=ALT)
    manager.observe_legend(1, 2, 'example', image=CANON, matched_image=ALT, upside_down=True)
    legend = manager.get_state().legends['1'][2]
    assert legend.matched_image == ALT and legend.upside_down
    manager.set_legend(1, 2, 'example', image=CANON)
    assert manager.get_state().legends['1'][2].matched_image == ''
    manager.undo()
    assert manager.get_state().legends['1'][2].matched_image == ALT
    manager.set_latest_card(1, 'example', 'Example', image=CANON, matched_image=ALT)
    manager.set_latest_card(1, 'other', 'Other', image=CANON)
    manager.undo_card_play()
    assert manager.get_state().latest_cards['1'].matched_image == ALT


def test_setting_broadcasts_updated_artwork_immediately(monkeypatch):
    import asyncio
    messages = []
    async def broadcast(payload):
        messages.append(payload)
    monkeypatch.setattr(state_api, 'save_overlay_config', lambda config: config)
    monkeypatch.setattr(runtime.ws_manager, 'broadcast', broadcast)
    monkeypatch.setattr(runtime, 'snapshot_payload', lambda: {'state': {'updated': True}, 'history': {}})
    asyncio.run(state_api.set_config(state_api.OverlayConfigRequest(config={'show_matched_art': True})))
    assert messages[0]['state'] == {'updated': True}
    assert messages[0]['config']['show_matched_art'] is True


def test_refining_printing_only_updates_the_latest_play():
    from app.vision.play_tracker import PlayTracker
    tracker = PlayTracker()
    track = {'current': object()}
    tracker.tracks = [track]
    def match(image):
        return Match('example', 'Example', '', CANON, .95, 50, .9, False, matched_image=image)
    assert tracker.accept(track, match(CANON), 1)
    assert tracker.accept(track, match(ALT), 2)
    assert not tracker.accept(track, match(ALT), 3)
    tracker.latest_id = 'another-card'
    assert not tracker.accept(track, match(CANON), 4)
