from types import SimpleNamespace
import numpy as np
from app.vision.calibration import CalibrationStore
from app.vision.frame_processor import VisionService


def test_rotation_shared_by_preview_crops_and_vision_and_persists(tmp_path):
    store = CalibrationStore(tmp_path/'cameras.json', tmp_path/'regions.json')
    service = VisionService(store, tmp_path/'captures')
    frame = np.arange(64*64*3, dtype=np.uint8).reshape(64,64,3)
    service.capture = SimpleNamespace(latest=lambda: (frame, 0))
    assert service.render_view('raw') is frame
    store.save_cameras({**store.cameras, 'rotate_source_180': True, 'corrected_size': [64,64]})
    expected = frame[::-1,::-1]
    np.testing.assert_array_equal(service.render_view('raw'), expected)
    np.testing.assert_array_equal(service.render_view('p1_crop'), expected)
    native, corrected = service.frame_and_view(1)
    np.testing.assert_array_equal(native, expected)
    np.testing.assert_array_equal(corrected, expected)
    assert CalibrationStore(store.cameras_path,store.regions_path).cameras['rotate_source_180'] is True
    # Paused frames remain in capture coordinates and are rotated exactly once.
    service._frozen = service._capture_frame().copy()
    service.paused = True
    np.testing.assert_array_equal(service._raw_frame(), expected)
    store.save_cameras({**store.cameras, 'rotate_source_180': False})
    np.testing.assert_array_equal(service._raw_frame(), frame)
    service.paused = False
    np.testing.assert_array_equal(service._raw_frame(), frame)


def test_invalid_rotation_values_do_not_enable_rotation(tmp_path):
    store = CalibrationStore(tmp_path/'cameras.json',tmp_path/'regions.json')
    for value in ['false', 180, None]:
        assert store.save_cameras({'rotate_source_180':value})['rotate_source_180'] is False
