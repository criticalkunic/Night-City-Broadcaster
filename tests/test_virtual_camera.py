import pytest
from app.broadcast import virtual_camera as vc


def test_virtual_output_rejects_physical_or_unknown_device(monkeypatch):
    monkeypatch.setattr(vc, 'devices', lambda: [])
    with pytest.raises(ValueError, match='writable virtual-camera'):
        vc.VirtualCamera().start('/dev/video2', 'board', 'http://127.0.0.1:8765')


def test_virtual_output_rejects_remote_renderer(monkeypatch):
    monkeypatch.setattr(vc, 'devices', lambda: [{'path':'/dev/video10','writable':True}])
    with pytest.raises(ValueError, match='local app'):
        vc.VirtualCamera().start('/dev/video10', 'board', 'https://example.com')


def test_virtual_command_keeps_capture_cadence():
    args = vc.ffmpeg_command('ffmpeg', ':123', 30, '/dev/video10')
    assert args[args.index('-framerate')+1] == '30'
    assert args[args.index('-fps_mode')+1] == 'passthrough'
    assert args[-3:] == ['-f', 'v4l2', '/dev/video10']
    assert ':123.0' in args


def test_stream_clients_share_encode():
    import threading
    from app.broadcast.feeds import SharedFeeds
    encoded = threading.Event()
    def encode(area):
        encoded.set()
        return b'jpeg'
    feeds = SharedFeeds(encode, lambda: 30)
    first = feeds.attach('play')
    second = feeds.attach('play')
    try:
        assert first is second
        assert encoded.wait(1)
        feeds.detach('play', first)
        assert not second['stop'].is_set()
        feeds.detach('play', second)
        assert second['stop'].is_set()
        assert not feeds.entries
    finally:
        feeds.stop()


def test_display_read_waits_for_split_newline():
    import os
    import threading
    import time
    read_fd, write_fd = os.pipe()
    wrote_newline = threading.Event()
    def writer():
        try:
            os.write(write_fd, b'123')
            time.sleep(.02)
            os.write(write_fd, b'\n')
            wrote_newline.set()
        finally:
            os.close(write_fd)
    thread = threading.Thread(target=writer)
    thread.start()
    try:
        assert vc.read_display_number(read_fd) == '123'
    finally:
        os.close(read_fd)
        thread.join()
    assert wrote_newline.is_set()
