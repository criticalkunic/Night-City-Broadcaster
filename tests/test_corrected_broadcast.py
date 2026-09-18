def test_corrected_broadcast_preserves_camera_colors(tmp_path, monkeypatch):
    from app import runtime
    from app.api.cameras import board_area_image
    import cv2
    import numpy as np
    from app.vision.calibration import CalibrationStore
    service = runtime.vision_service
    store = CalibrationStore(tmp_path/'cameras.json', tmp_path/'regions.json')
    store.player(1)['homography_points'] = [[.1,.1],[.9,.2],[.8,.9],[.2,.8]]
    store.cameras['vision_adjustments'] = {'brightness': 100, 'contrast': 2}
    frame = np.full((600,800,3), (30,80,140), np.uint8)
    monkeypatch.setattr(service, 'store', store)
    monkeypatch.setattr(service, '_raw_frame', lambda: frame)
    expected = service._corrected(frame, 1)
    response = board_area_image('board_corrected')
    assert response.status_code == 200
    image = cv2.imdecode(np.frombuffer(response.body,np.uint8),cv2.IMREAD_COLOR)
    assert image.shape == expected.shape
    assert np.abs(image.astype(float)-expected).mean() < 3
    monkeypatch.setattr(service, '_raw_frame', lambda: None)
    assert board_area_image('board_corrected').status_code == 200
