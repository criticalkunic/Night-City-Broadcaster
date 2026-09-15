"""Discover local capture devices without starting a camera."""
from pathlib import Path
from urllib.parse import urlsplit


def service_source(source, output):
    path = source.get('path') or '/dev/video'+str(source.get('index', 0))
    if path.startswith('/dev/'):
        canonical = str(Path(path).resolve())
        excluded = {str(Path(p).resolve()) for p in output.owned_devices}
        if output.device:
            excluded.add(str(Path(output.device).resolve()))
        label = Path('/sys/class/video4linux')/Path(canonical).name/'name'
        return canonical in excluded or (label.exists() and label.read_text().strip().startswith('Cyberpunk Board'))
    parsed = urlsplit(path)
    return (parsed.hostname in ('localhost', '127.0.0.1', '::1') and
            (parsed.path.startswith('/api/vision/') or parsed.path.startswith('/overlay/')))


def camera_sources(output):
    import sys
    if sys.platform == 'win32':
        from pygrabber.dshow_graph import FilterGraph
        return [{'path': str(i), 'name': name} for i, name in enumerate(FilterGraph().get_input_devices())
                if name != 'Night City Broadcast Camera']
    devices = []
    for item in sorted(Path('/sys/class/video4linux').glob('video*')):
        path = '/dev/'+item.name
        if service_source({'path':path}, output) or not Path(path).exists():
            continue
        try:
            import fcntl, os, struct
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            try:
                caps = bytearray(104)
                fcntl.ioctl(fd, 0x80685600, caps, True)  # VIDIOC_QUERYCAP
                capabilities, device_caps = struct.unpack_from('II', caps, 84)
                effective = device_caps if capabilities & 0x80000000 else capabilities
                if not effective & (0x1 | 0x1000):  # VIDEO_CAPTURE / VIDEO_CAPTURE_MPLANE
                    continue
            finally:
                os.close(fd)
            devices.append({'path':path, 'name':(item/'name').read_text().strip()})
        except OSError:
            continue
    return devices
