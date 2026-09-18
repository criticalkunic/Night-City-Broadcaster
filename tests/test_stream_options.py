from app import config


def test_stream_preferences_persist_and_validate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'CONFIG_DIR', tmp_path)
    monkeypatch.setattr(config, 'OVERLAY_CONFIG_FILE', tmp_path/'stream.json')
    assert config.load_overlay_config()['minimal_position'] == 'bottom-right'
    for position in ('top-left', 'top-right', 'bottom-left', 'bottom-right'):
        saved = config.save_overlay_config({'minimal_position': position, 'overlay_theme': 'edgerunners'})
        assert saved['minimal_position'] == position
        assert config.load_overlay_config()['overlay_theme'] == 'edgerunners'
    saved = config.save_overlay_config({'minimal_position': 'bad', 'overlay_theme': 'bad'})
    assert saved['minimal_position'] == 'bottom-right'
    assert saved['overlay_theme'] == 'cyberpunk'


def test_corrected_broadcast_preference(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'CONFIG_DIR', tmp_path)
    monkeypatch.setattr(config, 'OVERLAY_CONFIG_FILE', tmp_path/'stream.json')
    assert config.load_overlay_config()['broadcast_corrected'] is False
    config.save_overlay_config({'broadcast_corrected': True})
    assert config.load_overlay_config()['broadcast_corrected'] is True
