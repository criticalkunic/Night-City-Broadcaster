"""Shared latest-frame producers: slow consumers never queue camera frames."""
import logging
import threading
import time

log = logging.getLogger(__name__)


class SharedFeeds:
    def __init__(self, encode, fps):
        self.encode, self.fps = encode, fps
        self.lock = threading.Lock()
        self.entries = {}

    def attach(self, area):
        with self.lock:
            entry = self.entries.get(area)
            if entry is None:
                entry = {'users': 0, 'data': None, 'stop': threading.Event()}
                self.entries[area] = entry
                threading.Thread(target=self._produce, args=(area, entry), daemon=True,
                                 name='broadcast-'+area).start()
            entry['users'] += 1
            return entry

    def detach(self, area, entry):
        with self.lock:
            entry['users'] -= 1
            if entry['users'] == 0:
                entry['stop'].set()
                if self.entries.get(area) is entry:
                    del self.entries[area]

    def _produce(self, area, entry):
        deadline = time.monotonic()
        while not entry['stop'].is_set():
            interval = 1/self.fps()
            try:
                entry['data'] = self.encode(area)
            except Exception:
                log.exception('Area feed failed: %s', area)
                if entry['stop'].wait(1):
                    return
            deadline += interval
            now = time.monotonic()
            if deadline < now-interval:
                deadline = now
            entry['stop'].wait(max(0, deadline-now))

    def stop(self):
        with self.lock:
            for entry in self.entries.values():
                entry['stop'].set()
            self.entries.clear()
