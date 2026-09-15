"""Render the existing HTML in a private X display and publish it over V4L2.

No desktop capture and no OBS dependency. Processes belong to this instance;
stop never kills another application's browser, display, or camera producer.
"""
import os
from collections import deque
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit

from app.config import BASE_DIR

LAYOUTS = {name: '/broadcast/live' for name in ('board', 'play', 'eddies')}  # Legacy selections use the one output.


def devices():
    result = []
    for entry in sorted(Path('/sys/devices/virtual/video4linux').glob('video*')):
        device = Path('/dev') / entry.name
        # Only kernel virtual video devices, never a physical webcam.
        if device.exists():
            result.append({'path': str(device), 'name': (entry/'name').read_text().strip(),
                           'writable': os.access(device, os.W_OK)})
    return result


def dependencies():
    local = BASE_DIR/'tools/xvfb/usr/bin/Xvfb'
    return {'ffmpeg': shutil.which('ffmpeg'),
            'chrome': shutil.which('google-chrome') or shutil.which('chromium'),
            'xvfb': shutil.which('Xvfb') or (str(local) if local.exists() else None)}


def ffmpeg_command(binary, display, fps, device):
    return [binary, '-hide_banner', '-loglevel', 'warning', '-nostdin',
            '-f', 'x11grab', '-draw_mouse', '0', '-framerate', str(fps),
            '-video_size', '1920x1080', '-i', display+'.0',
            '-an', '-c:v', 'rawvideo', '-pix_fmt', 'yuv420p', '-threads', '2',
            '-fps_mode', 'passthrough', '-progress', 'pipe:1', '-nostats', '-f', 'v4l2', device]


def read_display_number(fd, timeout=5):
    import select
    data = b''
    deadline = time.monotonic()+timeout
    # Xvfb may write digits and the final newline separately. Do not close the
    # pipe after reading only digits: its newline write would fail with EPIPE.
    while b'\n' not in data:
        if not select.select([fd], [], [], max(0, deadline-time.monotonic()))[0]:
            raise ValueError('Private display did not start.')
        chunk = os.read(fd, 32)
        if not chunk:
            raise ValueError('Private display closed before becoming ready.')
        data += chunk
    return data.decode().strip()


class VirtualCamera:
    def __init__(self):
        self.lock = threading.RLock()
        self.processes = []
        self.folder = None
        self.error = None
        self.device = None
        self.owned_devices = set()
        self.layout = None
        self.target_fps = 30
        self.output_fps = 0.0
        self.frames = 0
        self.ready = threading.Event()
        self.token = None

    def status(self):
        with self.lock:
            if self.processes and any(p.poll() is not None for p in self.processes):
                if self.folder:
                    log = Path(self.folder.name)/'output.log'
                    self.error = log.read_text(errors='replace')[-1600:] or 'Output process stopped.'
                self._stop()
            return {'running': bool(self.processes), 'device': self.device, 'layout': self.layout,
                    'target_fps': self.target_fps, 'output_fps': self.output_fps, 'frames': self.frames,
                    'error': self.error, 'devices': devices(), 'dependencies': dependencies()}

    def _spawn(self, args, log, **kwargs):
        p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stderr=log,
                             start_new_session=True, **kwargs)
        self.processes.append(p)
        return p

    def start(self, device, layout, origin, fps=30):
        with self.lock:
            if self.processes:
                raise ValueError('Stop the current virtual camera before starting another output.')
            if layout not in LAYOUTS:
                raise ValueError('Unknown output layout.')
            if device not in {d['path'] for d in devices() if d['writable']}:
                raise ValueError('Select a writable virtual-camera device. Physical cameras are not output targets.')
            parsed = urlsplit(origin)
            if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError('The renderer must connect to this local app.')
            deps = dependencies()
            missing = [k for k,v in deps.items() if not v]
            if missing:
                raise ValueError('Missing output dependencies: '+', '.join(missing))
            self.error = None
            self.ready.clear()
            self.token = secrets.token_urlsafe(24)
            self.frames = 0
            self.output_fps = 0
            self.device, self.layout = device, layout
            self.owned_devices.add(device)
            self.target_fps = max(1, min(60, round(fps)))
            self.folder = tempfile.TemporaryDirectory(prefix='cyberpunk-camera-')
            root = Path(self.folder.name)
            try:
                with (root/'output.log').open('wb') as log:
                    # Xvfb allocates an unused display; no hardcoded :99 conflicts.
                    read_fd, write_fd = os.pipe()
                    try:
                        xvfb = self._spawn([deps['xvfb'], '-displayfd', str(write_fd), '-screen', '0',
                                            '1920x1080x24', '-nolisten', 'tcp', '-noreset'], log,
                                           stdout=log, pass_fds=(write_fd,))
                    finally:
                        os.close(write_fd)
                    try:
                        number = read_display_number(read_fd)
                        if not number.isdigit() or xvfb.poll() is not None:
                            raise ValueError('Private display failed to start.')
                    finally:
                        os.close(read_fd)
                    display = ':'+number
                    env = {**os.environ, 'DISPLAY': display, 'XDG_CONFIG_HOME': str(root/'config'),
                           'XDG_CACHE_HOME': str(root/'cache')}
                    self._spawn([deps['chrome'], '--ozone-platform=x11', '--kiosk', '--no-first-run',
                                 '--no-default-browser-check', '--disable-gpu', '--disable-dev-shm-usage',
                                 '--password-store=basic', '--disable-breakpad', '--disable-background-networking', '--disable-extensions', '--disable-session-crashed-bubble',
                                 '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
                                 '--disable-backgrounding-occluded-windows', '--autoplay-policy=no-user-gesture-required',
                                 '--force-device-scale-factor=1', '--window-position=0,0', '--window-size=1920,1080',
                                 '--user-data-dir='+str(root/'chrome'), origin+LAYOUTS[layout]+"?renderer="+self.token], log,
                                stdout=log, env=env)
                    if not self.ready.wait(20):
                        raise ValueError("The private browser did not finish loading the overlay.")
                    time.sleep(.25)
                    p = self._spawn(ffmpeg_command(deps['ffmpeg'], display, self.target_fps, device),
                                    log, stdout=subprocess.PIPE, env=env)
                    time.sleep(.4)
                    if any(p.poll() is not None for p in self.processes):
                        raise ValueError((root/'output.log').read_text(errors='replace')[-1600:])
                    threading.Thread(target=self._progress, args=(p,), daemon=True).start()
                    threading.Thread(target=self._monitor, args=(p,), daemon=True).start()
            except Exception as exc:
                self.error = str(exc)
                log_path = root/"output.log"
                if log_path.exists():
                    self.error += "\n"+log_path.read_text(errors="replace")[-2000:]
                self._stop()
                raise ValueError(self.error) from exc
            return self.status()

    def _monitor(self, process):
        while True:
            time.sleep(1)
            with self.lock:
                if process not in self.processes:
                    return
                self.status()  # Reap failed children even after settings is closed.

    def _progress(self, process):
        # FFmpeg reports delivered frames. Sample deltas instead of configured FPS.
        samples = deque([(time.monotonic(), 0)])
        for raw in process.stdout:
            line = raw.decode(errors='replace').strip()
            if line.startswith('frame='):
                try:
                    frames = int(line.split('=',1)[1])
                except ValueError:
                    continue
                now = time.monotonic()
                with self.lock:
                    if process not in self.processes:
                        return
                    self.frames = frames
                    samples.append((now, frames))
                    while len(samples) > 2 and now-samples[0][0] > 4:
                        samples.popleft()
                    stamp, previous = samples[0]
                    self.output_fps = round((frames-previous)/max(now-stamp,.001),1)

    def _stop(self):
        for p in reversed(self.processes):
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()
                except ProcessLookupError:
                    pass
        self.processes = []
        self.token = None
        self.ready.clear()
        if self.folder:
            self.folder.cleanup()
            self.folder = None

    def stop(self):
        with self.lock:
            self._stop()
            return self.status()
