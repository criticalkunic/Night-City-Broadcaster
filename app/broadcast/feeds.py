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
                entry = {'users': 0, 'data': None, 'stop': threading.Event(),
                         'fps': 0.0, 'encode_ms': 0.0}
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
        measured_at, frames = deadline, 0
        while not entry['stop'].is_set():
            interval = 1/self.fps()
            try:
                started = time.monotonic()
                entry['data'] = self.encode(area)
                now = time.monotonic()
                entry['encode_ms'] = round((now-started)*1000, 1)
                frames += 1
                if now-measured_at >= 1:
                    entry['fps'] = round(frames/(now-measured_at), 1)
                    measured_at, frames = now, 0
            except Exception:
                log.exception('Area feed failed: %s', area)
                if entry['stop'].wait(1):
                    return
            deadline += interval
            now = time.monotonic()
            if deadline < now-interval:
                deadline = now
            entry['stop'].wait(max(0, deadline-now))

    def status(self):
        """Encoding throughput, not camera or browser-rendered FPS."""
        with self.lock:
            return {area: {key: entry[key] for key in ('users', 'fps', 'encode_ms')}
                    for area, entry in self.entries.items()}

    def stop(self):
        with self.lock:
            for entry in self.entries.values():
                entry['stop'].set()
            self.entries.clear()
