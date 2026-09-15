import pytest
from types import SimpleNamespace
from app.game.state_manager import StateManager, StateError
from app.vision.sources import service_source


def play(manager, name):
    manager.set_latest_card(1, name, name, image='/'+name+'.webp')


def test_card_back_ignores_gigs_and_removal():
    m=StateManager()
    play(m,'A')
    m.clear_latest_card()
    play(m,'B')
    m.set_gig('p1-d6',4)
    m.undo_card_play()
    state=m.get_state()
    assert state.latest_cards['1'].card_id=='A'
    assert state.dice['p1-d6'].last_roll==4
    assert state.dice['p1-d6'].location=='p1_gig'
    m.undo_card_play()
    assert m.get_state().latest_cards['1'] is None
    with pytest.raises(StateError):m.undo_card_play()


def test_card_history_rolls_at_100_and_branches():
    m=StateManager()
    for i in range(105):play(m,str(i))
    assert m.history_info()['card_undo_count']==100
    for _ in range(100):m.undo_card_play()
    assert m.get_state().latest_cards['1'].card_id=='4'
    assert not m.history_info()['can_undo_card']
    play(m,'branch')
    m.undo_card_play()
    assert m.get_state().latest_cards['1'].card_id=='4'


def test_regular_undo_and_new_match_keep_card_history_consistent():
    m=StateManager()
    play(m,'A');play(m,'B')
    m.undo()
    assert m.history_info()['card_undo_count']==1
    m.redo()
    assert m.history_info()['card_undo_count']==2
    m.reset_match()
    assert not m.history_info()['can_undo_card']


def test_input_excludes_own_outputs_but_accepts_other_sources():
    output=SimpleNamespace(device='/dev/video10',owned_devices={'/dev/video11'})
    assert service_source({'path':'/dev/video10'},output)
    assert service_source({'index':11},output)
    assert service_source({'path':'http://127.0.0.1:8765/api/vision/area-stream/play'},output)
    assert not service_source({'path':'/dev/video8'},output)
    assert not service_source({'path':'rtsp://camera.local/live'},output)
    assert not service_source({'path':'/tmp/video.mp4'},output)
