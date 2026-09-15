"""API + WebSocket tests against the FastAPI app."""
import pytest
from fastapi.testclient import TestClient

from app import runtime
from app.game.state_manager import StateManager
from app.main import app


@pytest.fixture
def client():
    # Fresh authoritative state per test; card DB is read-only and shared.
    runtime.state_manager = StateManager()
    with TestClient(app) as c:
        yield c


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["cards_loaded"] > 0


def test_pages_load(client):
    for path in ("/", "/operator", "/overlay", "/setup", "/debug"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert "<html" in res.text.lower(), path


def test_get_state(client):
    res = client.get("/api/state")
    assert res.status_code == 200
    body = res.json()
    assert body["type"] == "state_snapshot"
    assert len(body["state"]["dice"]) == 12
    assert body["history"]["can_undo"] is False


def test_move_and_roll(client):
    res = client.post("/api/dice/p1-d8/move", json={"location": "p2_gig"})
    assert res.status_code == 200
    assert res.json()["state"]["dice"]["p1-d8"]["location"] == "p2_gig"

    res = client.post("/api/dice/p1-d8/roll", json={"value": 6})
    assert res.status_code == 200
    assert res.json()["state"]["dice"]["p1-d8"]["last_roll"] == 6


def test_invalid_roll_rejected(client):
    res = client.post("/api/dice/p1-d4/roll", json={"value": 7})
    assert res.status_code == 400
    assert "1-4" in res.json()["detail"]


def test_unknown_die_rejected(client):
    res = client.post("/api/dice/p9-d4/roll", json={"value": 2})
    assert res.status_code == 400


def test_card_search(client):
    res = client.get("/api/cards/search", params={"q": "reb"})
    assert res.status_code == 200
    names = [c["name"] for c in res.json()["results"]]
    assert "Rebecca" in names


def test_card_alias_search(client):
    # display_name ("Rebecca: Having a Moment") is indexed as an alias.
    res = client.get("/api/cards/search", params={"q": "having a moment"})
    names = [c["name"] for c in res.json()["results"]]
    assert "Rebecca" in names


def test_set_latest_card(client):
    res = client.post("/api/card/latest", json={"player": 1, "card_id": "cb-rebecca-having-a-moment"})
    assert res.status_code == 200
    lc = res.json()["state"]["latest_cards"]["1"]
    assert lc["name"] == "Rebecca"
    assert lc["image"].startswith("/cards/images/")
    assert lc["source"] == "manual"


def test_legend_endpoints(client):
    res = client.post("/api/legends/1/0", json={"card_id": "cb-v-streetkid"})
    assert res.status_code == 200
    legend = res.json()["state"]["legends"]["1"][0]
    assert legend["card_id"] == "cb-v-streetkid" and legend["revealed"] is False

    res = client.post("/api/legends/1/0", json={"revealed": True})
    assert res.json()["state"]["legends"]["1"][0]["revealed"] is True

    res = client.post("/api/legends/1/0", json={"card_id": ""})
    legend = res.json()["state"]["legends"]["1"][0]
    assert legend["card_id"] is None and legend["revealed"] is False

    assert client.post("/api/legends/1/0", json={}).status_code == 400
    assert client.post("/api/legends/1/0", json={"card_id": "card-999"}).status_code == 404
    assert client.post("/api/legends/1/5", json={"card_id": "cb-v-streetkid"}).status_code == 400
    # Revealing an empty slot is rejected.
    assert client.post("/api/legends/2/0", json={"revealed": True}).status_code == 400


def test_cred_endpoint(client):
    res = client.post("/api/cred/2", json={"value": 5})
    assert res.status_code == 200
    assert res.json()["state"]["match"]["player2_cred"] == 5
    assert client.post("/api/cred/2", json={"value": 120}).status_code == 422


def test_set_unknown_card(client):
    res = client.post("/api/card/latest", json={"player": 1, "card_id": "card-999"})
    assert res.status_code == 404


def test_undo_redo_endpoints(client):
    client.post("/api/dice/p1-d8/roll", json={"value": 6})
    res = client.post("/api/undo")
    assert res.status_code == 200
    assert res.json()["state"]["dice"]["p1-d8"]["last_roll"] is None
    res = client.post("/api/redo")
    assert res.json()["state"]["dice"]["p1-d8"]["last_roll"] == 6
    res = client.post("/api/redo")
    assert res.status_code == 400


def test_reset_endpoint(client):
    client.post("/api/dice/p1-d8/move", json={"location": "p2_gig"})
    res = client.post("/api/reset")
    assert res.json()["state"]["dice"]["p1-d8"]["location"] == "p1_fixer"


def test_websocket_snapshot_and_broadcast(client):
    with client.websocket_connect("/ws") as ws:
        snapshot = ws.receive_json()
        assert snapshot["type"] == "state_snapshot"
        assert len(snapshot["state"]["dice"]) == 12

        client.post("/api/dice/p1-d8/roll", json={"value": 6})
        update = ws.receive_json()
        assert update["type"] == "die_rolled"
        assert update["event"]["data"]["die_id"] == "p1-d8"
        assert update["state"]["dice"]["p1-d8"]["last_roll"] == 6


def test_vision_status(client):
    res = client.get("/api/vision/status")
    assert res.status_code == 200
    body = res.json()
    assert body["running"] is False
    assert "raw" in body["views"]


def test_vision_frame_placeholder(client):
    res = client.get("/api/vision/frame/raw.jpg")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert res.content[:2] == b"\xff\xd8"


def test_vision_unknown_view(client):
    assert client.get("/api/vision/frame/nope.jpg").status_code == 404


def test_vision_save_frame_without_source(client):
    res = client.post("/api/vision/save_frame", json={"view": "raw"})
    assert res.status_code == 400


def test_vision_calibration_roundtrip(client, tmp_path, monkeypatch):
    from app.vision.calibration import CalibrationStore
    store = CalibrationStore(tmp_path / "cameras.json", tmp_path / "regions.json")
    monkeypatch.setattr(runtime, "calibration_store", store)
    monkeypatch.setattr(runtime.vision_service, "store", store)

    res = client.get("/api/vision/calibration")
    assert res.status_code == 200
    assert res.json()["regions"]["player1"]["source_rect"]["width"] == 1.0

    res = client.post("/api/vision/calibration", json={
        "regions": {"player1": {"source_rect": {"x": 0.1, "y": 0, "width": 0.4, "height": 1}}}
    })
    assert res.status_code == 200
    assert res.json()["regions"]["player1"]["source_rect"]["x"] == 0.1
    assert (tmp_path / "regions.json").exists()


def test_vision_scan_requires_running(client):
    res = client.post("/api/vision/scan")
    assert res.status_code == 400


def test_vision_scan_applies_state(client, tmp_path, monkeypatch):
    import numpy as np
    from app.vision.calibration import CalibrationStore
    from app.vision.perspective import rect_to_pixels
    from tests.test_scan import legend_slot_rects, make_table, paint_face_card

    store = CalibrationStore(tmp_path / "cameras.json", tmp_path / "regions.json")
    view = make_table()
    regions = store.player(1)["regions"]
    paint_face_card(view, legend_slot_rects(regions["legend_region"])[0])
    play = regions["card_play_region"]
    h, w = view.shape[:2]
    px, py, pw, ph = rect_to_pixels(play, w, h)
    cx, cy = px + pw // 2 - 45, py + ph // 2 - 63
    view[cy:cy + 126, cx:cx + 90] = (235, 235, 235)

    class FakeVision:
        running = True
        paused = False
        recognizer = None

        def __init__(self, match=None):
            self.store = store
            self.match = match
            self.calls = []

        def render_view(self, name, rois=False):
            return view

        def frame_and_view(self, player):
            return view, view

        def native_crop(self, frame, player, quad):
            from app.vision.card_detector import rectify_quad
            return rectify_quad(frame, quad)

        def recognition_config(self):
            return {"min_confidence": 0.45, "auto_apply": True, "candidates": 2, "try_splits": True}

        def recognize_crops(self, crops, card_type=None):
            assert crops and all(c is not None for _, c in crops)
            self.calls.append(card_type)
            return self.match

    fake = FakeVision()
    monkeypatch.setattr(runtime, "vision_service", fake)
    import app.api.cameras as cameras_api
    monkeypatch.setattr(cameras_api, "CAPTURES_DIR", tmp_path / "captures")

    # Unrecognized: a brightness guess must not reveal an assigned legend. Existing table cards must not populate latest play.
    client.post("/api/legends/1/0", json={"card_id": "cb-v-streetkid"})

    res = client.post("/api/vision/scan")
    assert res.status_code == 200
    actions = res.json()["actions"]
    assert not any("legend 1 revealed" in a for a in actions)
    assert not any("latest card" in a for a in actions)
    assert "Legend" in fake.calls  # legend slot was matched against Legend cards only

    state = client.get("/api/state").json()["state"]
    assert state["legends"]["1"][0]["revealed"] is False
    lc = state["latest_cards"]["1"]
    assert lc is None

    # Recognized: only the legend slot gets the identified DB card.
    from app.vision.recognizer import Match
    rebecca = runtime.card_db.get("cb-rebecca-having-a-moment")
    fake.match = Match(card_id=rebecca["id"], name=rebecca["name"], subtitle=rebecca["subtitle"],
                       image=rebecca["image"], confidence=0.9, inliers=40, thumb_score=0.8,
                       rotated=False, card_type="Legend")
    runtime.state_manager.reset_match()
    res = client.post("/api/vision/scan")
    actions = res.json()["actions"]
    assert any("legend 1 identified: Rebecca" in a for a in actions)
    assert not any("latest card" in a for a in actions)
    state = client.get("/api/state").json()["state"]
    legend = state["legends"]["1"][0]
    assert legend["card_id"] == rebecca["id"] and legend["revealed"] is True
    lc = state["latest_cards"]["1"]
    assert lc is None
    # Same card again: no duplicate latest-card event.
    before = len(state["recent_events"])
    client.post("/api/vision/scan")
    after = client.get("/api/state").json()["state"]["recent_events"]
    assert not any("latest card identified" in e["description"] for e in after[:len(after) - before])


def test_config_roundtrip(client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "OVERLAY_CONFIG_FILE", tmp_path / "overlay.json")
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    res = client.get("/api/config")
    assert res.status_code == 200
    assert "show_card_art" in res.json()


def test_apply_legend_finding(client, monkeypatch):
    import app.api.cameras as cameras_api
    from app.vision.recognizer import Match

    class FakeVision:
        def __init__(self, auto_hide=False):
            self.auto_hide = auto_hide

        def recognition_config(self):
            return {"min_confidence": 0.45, "legend_auto_hide": self.auto_hide}

    fake = FakeVision()
    monkeypatch.setattr(runtime, "vision_service", fake)
    rebecca = runtime.card_db.get("cb-rebecca-having-a-moment")
    good = Match(card_id=rebecca["id"], name=rebecca["name"], subtitle=rebecca["subtitle"],
                 image=rebecca["image"], confidence=0.9, inliers=40, thumb_score=0.8,
                 rotated=False, card_type="Legend")
    weak = Match(**{**good.__dict__, "confidence": 0.2})

    # Face-up, unrecognized, empty slot: nothing to do.
    assert cameras_api.apply_legend_finding(1, 0, True, weak) == []
    # Face-up + confident: assigned and revealed.
    actions = cameras_api.apply_legend_finding(1, 0, True, good)
    assert any("identified: Rebecca" in a for a in actions) and any("revealed" in a for a in actions)
    legend = runtime.state_manager.get_state().legends["1"][0]
    assert legend.card_id == rebecca["id"] and legend.revealed is True
    # Same again: no duplicate actions.
    assert cameras_api.apply_legend_finding(1, 0, True, good) == []
    # Face-down: hidden only with legend_auto_hide.
    assert cameras_api.apply_legend_finding(1, 0, False, None) == []
    assert runtime.state_manager.get_state().legends["1"][0].revealed is True
    fake.auto_hide = True
    assert cameras_api.apply_legend_finding(1, 0, False, None) == ["P1 legend 1 hidden (face-down on table)"]
    assert runtime.state_manager.get_state().legends["1"][0].revealed is False


def test_card_search_type_filter(client):
    # Legend-only search (legend slot assignment) never returns units...
    res = client.get("/api/cards/search", params={"q": "", "type": "Legend", "limit": 50})
    results = res.json()["results"]
    assert results and all(c["card_type"] == "Legend" for c in results)
    # ...while the unrestricted search (latest card) still finds a legend.
    names = [c["name"] for c in client.get("/api/cards/search", params={"q": "rebecca"}).json()["results"]]
    assert "Rebecca" in names
    assert client.get("/api/cards/search", params={"q": "corpo security", "type": "Legend"}).json()["results"] == []


def test_swap_legends_endpoint(client):
    client.post("/api/legends/2/1", json={"card_id": "cb-v-streetkid"})
    res = client.post("/api/legends/2/swap", json={"a": 1, "b": 0})
    assert res.status_code == 200
    legends = res.json()["state"]["legends"]["2"]
    assert legends[0]["card_id"] == "cb-v-streetkid" and legends[1]["card_id"] is None
    assert res.json()["event"]["type"] == "legends_swapped"
    assert client.post("/api/legends/2/swap", json={"a": 0, "b": 0}).status_code == 400


def test_new_solo_match_endpoint(client):
    client.post("/api/solo/gigs/p2-d8", json={"value": 7})
    response = client.post("/api/solo/match/new", json={})
    assert response.status_code == 200
    state = response.json()["state"]
    assert state["match"]["started"] is True
    assert state["latest_cards"]["1"] is None
    assert not any(d["location"] == "p1_gig" for d in state["dice"].values())
    restored = client.post("/api/undo").json()["state"]
    assert restored["dice"]["p2-d8"]["last_roll"] == 7
    assert restored["dice"]["p2-d8"]["location"] == "p1_gig"


def test_board_area_feeds_keep_landscape_orientation(client, tmp_path, monkeypatch):
    import cv2
    import numpy as np
    from app.vision.calibration import CalibrationStore
    store = CalibrationStore(tmp_path/'cameras.json',tmp_path/'regions.json')
    store.player(1)['regions']['card_play_region'] = dict(x=.25,y=.2,width=.5,height=.4)
    frame = np.zeros((600,800,3), np.uint8)
    frame[:,:400] = (0,0,230)
    frame[:,400:] = (230,0,0)
    monkeypatch.setattr(runtime.vision_service,'store',store)
    monkeypatch.setattr(runtime.vision_service,'_raw_frame',lambda:frame)
    def unused_corrected(*args):
        raise AssertionError('Area feeds must not render the full corrected board')
    monkeypatch.setattr(runtime.vision_service,'frame_and_view',unused_corrected)
    response = client.get('/api/vision/area/play.jpg')
    assert response.status_code == 200
    image = cv2.imdecode(np.frombuffer(response.content,np.uint8),cv2.IMREAD_COLOR)
    assert image.shape[:2] == (240,400)
    assert image[100,30,2] > 200 and image[100,370,0] > 200
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/api/vision/area/eddies.jpg').status_code == 200
    assert client.get('/api/vision/area/unknown.jpg').status_code == 404
    assert client.get('/overlay/board').status_code == 200
    assert client.get('/overlay/feed/play').status_code == 200


def test_learn_artwork_uses_frozen_crop_and_checks_paths(client, tmp_path, monkeypatch):
    import cv2
    import numpy as np
    from types import SimpleNamespace
    import app.api.cameras as cameras_api
    folder = tmp_path/'crops'
    folder.mkdir()
    cv2.imwrite(str(folder/'p1-sample.png'), np.full((100,80,3), 120, np.uint8))
    builds = []
    monkeypatch.setattr(runtime, 'vision_service', SimpleNamespace(captures_dir=tmp_path))
    monkeypatch.setattr(runtime, 'recognizer', SimpleNamespace(images_dir=tmp_path/'images', build=lambda:builds.append(True)))
    card = runtime.card_db.cards[0]
    body = {'card_id': card['id'], 'capture': 'p1-sample.png'}
    assert client.get('/api/vision/artwork/capture/p1-sample.png').status_code == 200
    assert client.post('/api/vision/artwork/learn', json=body).status_code == 200
    assert len(list((tmp_path/'images'/'recognition'/card['id']).glob('*.png'))) == 1
    assert client.post('/api/vision/artwork/learn', json=body).status_code == 200
    assert len(builds) == 1
    assert client.post('/api/vision/artwork/learn', json={**body, 'capture':'../p1-sample.png'}).status_code == 400
    assert client.post('/api/vision/artwork/learn', json={**body, 'card_id':'invalid'}).status_code == 404


def test_legacy_overlays_redirect_to_one_output(client):
    from app.broadcast.virtual_camera import LAYOUTS
    assert set(LAYOUTS.values()) == {'/overlay/live'}
    for path in ('/overlay/board', '/overlay/feed/play', '/overlay/feed/eddies'):
        response = client.get(path+'?renderer=test', follow_redirects=False)
        assert response.status_code == 307
        assert response.headers['location'] == '/overlay/live?renderer=test'


def test_arm_current_cards_opens_gate_and_requests_fresh_detection(client, monkeypatch):
    from types import SimpleNamespace
    runtime.state_manager = StateManager(require_fresh_play=True)
    resets = []
    monkeypatch.setattr(runtime.vision_service, 'detection',
                        SimpleNamespace(request_play_reset=lambda: resets.append(True)))
    assert not client.get('/api/state').json()['state']['awaiting_first_play']
    response = client.post('/api/solo/play/arm', json={})
    assert response.status_code == 200
    state = response.json()['state']
    assert state['awaiting_first_play'] is False
    assert state['latest_cards']['1'] is None  # Arming never invents a play.
    assert resets == [True]
    response = client.post('/api/solo/match/new', json={})
    assert response.json()['state']['awaiting_first_play'] is False
    assert resets == [True, True]
