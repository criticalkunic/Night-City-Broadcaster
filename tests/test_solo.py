"""Single-player behavior and API regression coverage without hardware."""
import asyncio
import httpx
import pytest
from app import runtime
from app.main import app
from app.game.state_manager import StateManager, StateError
from app.vision.calibration import CalibrationStore
from app.vision.card_detector import DetectionWorker


def test_stolen_gig_and_return_are_atomic_and_undoable():
    manager = StateManager()
    manager.set_gig("p1-d6", 4)
    manager.set_gig("p2-d8", 7)
    assert manager.get_state().match.player1_cred == 11
    manager.set_gig("p2-d8", None)
    assert manager.get_state().match.player1_cred == 4
    manager.undo()
    assert manager.get_state().dice["p2-d8"].location == "p1_gig"
    assert manager.get_state().match.player1_cred == 11
    manager.redo()
    assert manager.get_state().dice["p2-d8"].location == "p2_fixer"


def test_invalid_gig_does_not_change_state_or_history():
    manager = StateManager()
    before = manager.get_state()
    for die, value in [("p2-d4", 5), ("missing", 2), ("p1-d8", 0)]:
        with pytest.raises(StateError):
            manager.set_gig(die, value)
    assert manager.get_state() == before
    assert not manager.history_info()["can_undo"]


def test_clear_latest_is_undoable():
    manager = StateManager()
    manager.set_latest_card(1, "card", "Card")
    manager.clear_latest_card()
    assert manager.get_state().latest_cards["1"] is None
    manager.undo()
    assert manager.get_state().latest_cards["1"].card_id == "card"


def test_full_webcam_default(tmp_path):
    store = CalibrationStore(tmp_path / "cameras.json", tmp_path / "regions.json")
    assert store.player(1)["source_rect"] == dict(x=0, y=0, width=1, height=1)


def test_detection_worker_only_processes_own_board(tmp_path):
    class Service:
        running = True
        paused = False
        store = CalibrationStore(tmp_path / "cameras.json", tmp_path / "regions.json")
    worker = DetectionWorker(Service())
    processed = []
    def process(player, config):
        processed.append(player)
        worker._stop_event.set()
    worker._process = process
    worker._check_legends = lambda *args: None
    worker.run()
    assert processed == [1]


def test_solo_api(monkeypatch, tmp_path):
    from app import config
    monkeypatch.setattr(runtime, "state_manager", StateManager())
    monkeypatch.setattr(config, "OVERLAY_CONFIG_FILE", tmp_path / "overlay.json")
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/config")).json()["show_dice"] is False
            response = await client.post("/api/solo/gigs/p2-d8", json={"value": 7})
            assert response.status_code == 200
            assert response.json()["state"]["match"]["player1_cred"] == 7
            assert (await client.post("/api/solo/gigs/p2-d4", json={"value": 7})).status_code == 400
            results = (await client.get("/api/cards/search?q=Johnny")).json()["results"]
            assert results
            await client.post("/api/card/latest", json={"player": 1, "card_id": results[0]["id"]})
            assert (await client.post("/api/solo/card/clear", json={})).json()["state"]["latest_cards"]["1"] is None
            assert (await client.post("/api/undo", json={})).json()["state"]["latest_cards"]["1"]["card_id"] == results[0]["id"]
            for path in ("/operator", "/setup", "/overlay", "/debug"):
                assert (await client.get(path)).status_code == 200
    asyncio.run(run())


def test_legend_assignment_hides_previous_reveal_atomically():
    manager = StateManager()
    manager.set_legend(1, 0, "first", name="First", image="/first.webp")
    manager.reveal_legend(1, 0, True)
    manager.set_legend(1, 0, "second", name="Second", image="/second.webp", revealed=False)
    legend = manager.get_state().legends["1"][0]
    assert legend.card_id == "second"
    assert not legend.revealed
    manager.undo()
    legend = manager.get_state().legends["1"][0]
    assert legend.card_id == "first"
    assert legend.revealed
    manager.redo()
    assert not manager.get_state().legends["1"][0].revealed


def test_new_game_always_accepts_vision_cards():
    manager = StateManager(require_fresh_play=True)
    manager.set_latest_card(1, "existing", "Existing", source="vision")
    assert manager.get_state().latest_cards["1"].card_id == "existing"
    manager.reset_match()
    assert manager.get_state().latest_cards["1"] is None
    assert not manager.get_state().awaiting_first_play
    manager.set_latest_card(1, "existing", "Existing", source="vision")
    assert manager.get_state().latest_cards["1"].card_id == "existing"


def test_manual_play_is_allowed_at_start_of_game():
    manager = StateManager(require_fresh_play=True)
    manager.set_latest_card(1, "chosen", "Chosen", source="manual")
    assert manager.get_state().latest_cards["1"].card_id == "chosen"


def test_overlay_default_is_settings_and_obs_url_is_clean():
    from app.main import _PAGES
    settings = _PAGES["/overlay"].read_text()
    shell = _PAGES["/broadcast/live"].read_text()
    assert "active-overlay.js" in shell
    assert "/overlay/board" not in _PAGES
    assert "board-url" not in settings and "play-feed-url" not in settings
    assert settings.count('id="preview-layout"') == 1
    live = (_PAGES["/broadcast/live"].parent.parent / "overlay" / "index.html").read_text()
    assert "Copy OBS stream link" in settings
    assert 'src="/broadcast/live"' in settings
    assert 'id="latest"' in live
    assert "Copy OBS stream link" not in live


def test_scan_does_not_apply_existing_card(monkeypatch):
    from app.api import cameras
    from unittest.mock import Mock
    manager = StateManager(require_fresh_play=True)
    monkeypatch.setattr(runtime, "state_manager", manager)
    monkeypatch.setattr(cameras, "scan_player", lambda *args: {
        "ok": True, "legends": [], "card_crop": object(), "card_crops": [],
    })
    service = Mock()
    monkeypatch.setattr(runtime, "vision_service", service)
    async def broadcast(payload):
        pass
    monkeypatch.setattr(runtime.ws_manager, "broadcast", broadcast)
    # This coroutine has no suspending I/O with the above isolated broadcast.
    coroutine = cameras._apply_scan()
    with pytest.raises(StopIteration):
        coroutine.send(None)
    assert manager.get_state().latest_cards["1"] is None
    service.recognize_crops.assert_not_called()


def test_debug_available_on_main_pages():
    from app.main import _PAGES
    for route in ("/operator", "/setup", "/overlay"):
        assert 'href="/debug"' in _PAGES[route].read_text()
    assert 'href="/debug"' not in _PAGES["/broadcast/live"].read_text()


def test_legend_debug_images_show_current_regions(tmp_path):
    import cv2
    import numpy as np
    from app.vision.frame_processor import VisionService
    store = CalibrationStore(tmp_path / "camera.json", tmp_path / "regions.json")
    store.player(1)["regions"]["legend_region"] = dict(x=.1, y=.2, width=.6, height=.3)
    service = VisionService(store, tmp_path / "captures")
    view = np.zeros((600, 800, 3), dtype=np.uint8)
    view[120:300,80:240] = (0, 0, 255)
    view[120:300,240:400] = (0, 255, 0)
    view[120:300,400:560] = (255, 0, 0)
    service.frame_and_view = lambda player: (view, view)
    for slot, channel in ((0, 2), (1, 1), (2, 0)):
        crop = cv2.imdecode(np.frombuffer(service.legend_debug_jpeg(1, slot), np.uint8), cv2.IMREAD_COLOR)
        assert crop.shape[:2] == (180, 160)
        assert crop[:, :, channel].mean() > 240
    board = cv2.imdecode(np.frombuffer(service.legend_debug_jpeg(1), np.uint8), cv2.IMREAD_COLOR)
    assert board.shape == view.shape
    service.frame_and_view = lambda player: (None, None)
    assert service.legend_debug_jpeg(1).startswith(b"\xff\xd8")


def test_new_match_is_atomic_and_keeps_tracking():
    manager = StateManager(require_fresh_play=True)
    manager.set_player_names("V", "Opponent")
    manager.set_latest_card(1, "old", "Old")
    manager.set_gig("p1-d6", 4)
    before = manager.get_state()
    manager.reset_match(start=True)
    state = manager.get_state()
    assert state.match.started
    assert state.match.player1_name == "V"
    assert not state.awaiting_first_play
    assert state.latest_cards["1"] is None
    assert not any(d.location == "p1_gig" for d in state.dice.values())
    manager.undo()
    assert manager.get_state() == before
    manager.redo()
    assert manager.get_state().latest_cards["1"] is None
