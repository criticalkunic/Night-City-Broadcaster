import threading
from app.broadcast.feeds import SharedFeeds


def test_feed_metrics_measure_processing_and_are_removed_on_detach(monkeypatch):
    from app.broadcast import feeds as module
    clock = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    class Stop:
        def is_set(self):return clock[0] >= 1.2
        def wait(self, delay):clock[0] += delay;return self.is_set()
        def set(self):clock[0] = 2.0
    def encode(area):
        clock[0] += .01
        return b'jpeg'
    feeds = SharedFeeds(encode, lambda:30)
    entry = {'users':1,'data':None,'stop':Stop(),'fps':0.0,'encode_ms':0.0}
    feeds.entries['raw'] = entry
    feeds._produce('raw',entry)
    status = feeds.status()['raw']
    assert 29 <= status['fps'] <= 31
    assert status['encode_ms'] == 10.0
    assert status['users'] == 1 and entry['data'] == b'jpeg'
    status['users'] = 99
    assert feeds.status()['raw']['users'] == 1
    feeds.detach('raw',entry)
    assert feeds.status() == {}
