import numpy as np
from app.game.state_manager import StateManager
from app.vision.calibration import CalibrationStore
from app.vision.frame_processor import VisionService


def test_legend_movement_and_rotation_are_independent():
    manager = StateManager()
    manager.observe_legend(1, 0, 'a', name='A', upside_down=True)
    manager.observe_legend(1, 1, 'b', name='B')
    manager.observe_legend(1, 1, 'a', name='A', upside_down=True)
    slots = manager.get_state().legends['1']
    assert [s.card_id for s in slots] == ['b', 'a', None]
    assert slots[1].upside_down and slots[1].revealed
    assert manager.observe_legend(1, 1, 'a', upside_down=True) is None
    manager.reveal_legend(1, 1, False)
    assert manager.get_state().legends['1'][1].upside_down
    manager.observe_legend(1, 1, 'a', upside_down=False)
    assert not manager.get_state().legends['1'][1].upside_down
    manager.set_legend(1, 1, None)
    assert not manager.get_state().legends['1'][1].upside_down


def test_vision_adjustments_preserve_broadcast_and_invalidate_mat(tmp_path):
    store = CalibrationStore(tmp_path/'cameras.json', tmp_path/'regions.json')
    service = VisionService(store, tmp_path)
    frame = np.full((100, 100, 3), 50, dtype=np.uint8)
    service._raw_frame = lambda: frame
    before = service.mat_signature()
    store.save_cameras({**store.cameras, 'vision_adjustments': {'brightness': -100, 'contrast': 1}})
    processed, view = service.frame_and_view(1)
    assert processed.max() == 0
    assert service.render_view('raw').min() == 50
    assert service.render_view('p1_corrected').max() == 0
    assert service.mat_signature() != before
    store.save_cameras({**store.cameras, 'vision_adjustments': {'brightness': 999, 'contrast': 99}})
    assert store.cameras['vision_adjustments'] == {'brightness': 100, 'contrast': 2}
