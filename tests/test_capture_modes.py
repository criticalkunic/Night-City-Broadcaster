import cv2
from app.vision.capture import CaptureThread

class Camera:
    def __init__(self, accept=True):
        self.calls=[];self.accept=accept
        self.props={cv2.CAP_PROP_FPS:5,cv2.CAP_PROP_FOURCC:cv2.VideoWriter_fourcc(*'YUYV')}
    def isOpened(self):return True
    def set(self,key,value):
        self.calls.append((key,value))
        if self.accept:self.props[key]=value
        return self.accept
    def get(self,key):return self.props.get(key,0)


def test_mjpeg_negotiated_before_size_and_rate(monkeypatch):
    fake=Camera()
    monkeypatch.setattr(cv2,'VideoCapture',lambda *args:fake)
    capture=CaptureThread({'type':'camera','path':'/dev/video1','capture_mode':'mjpeg1080','exposure_mode':'keep'})
    capture._open()
    assert [key for key,_ in fake.calls]==[cv2.CAP_PROP_FOURCC,cv2.CAP_PROP_FRAME_WIDTH,cv2.CAP_PROP_FRAME_HEIGHT,cv2.CAP_PROP_FPS]
    assert capture.pixel_format=='MJPG'
    assert capture.native_fps==30
    assert capture.capture_warning is None


def test_rejected_mode_reports_actual_camera_rate(monkeypatch):
    fake=Camera(accept=False)
    monkeypatch.setattr(cv2,'VideoCapture',lambda *args:fake)
    capture=CaptureThread({'type':'camera','index':1,'capture_mode':'mjpeg720'})
    capture._open()
    assert capture.native_fps==5
    assert 'YUYV' in capture.capture_warning
    assert (cv2.CAP_PROP_FRAME_WIDTH,1280) in fake.calls


def test_files_streams_and_native_mode_are_not_reconfigured(monkeypatch):
    for source in ({'type':'video','path':'clip.avi'}, {'type':'stream','path':'rtsp://camera/live'}, {'type':'camera','index':1,'capture_mode':'native','exposure_mode':'keep'}):
        fake=Camera()
        monkeypatch.setattr(cv2,'VideoCapture',lambda *args:fake)
        CaptureThread(source)._open()
        assert not fake.calls


def test_windows_dshow_keeps_mjpeg_after_fps_reopens_device(monkeypatch):
    from app.vision import capture as module
    class DirectShow(Camera):
        def set(self, key, value):
            super().set(key, value)
            # DirectShow reopens without the requested media subtype on FPS change.
            if key == cv2.CAP_PROP_FPS:
                self.props[cv2.CAP_PROP_FOURCC] = cv2.VideoWriter_fourcc(*'YUY2')
            return True
        def getBackendName(self):return 'DSHOW'
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    fake=DirectShow()
    opened=[]
    monkeypatch.setattr(cv2,'VideoCapture',lambda *args: opened.append(args) or fake)
    capture=CaptureThread({'type':'camera','index':0,'capture_mode':'mjpeg1080','exposure_mode':'keep'})
    capture._open()
    assert opened == [(0, cv2.CAP_DSHOW)]
    assert capture.pixel_format == 'MJPG'
    assert capture.native_fps == 30
    assert capture.backend_name == 'DSHOW'
    assert capture.capture_warning is None


def test_windows_exposure_choices_and_restore_auto(monkeypatch):
    from app.vision import capture as module
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    for mode, expected in [('keep', []), ('motion', [(cv2.CAP_PROP_AUTO_EXPOSURE,0),(cv2.CAP_PROP_EXPOSURE,-6)]), ('auto', [(cv2.CAP_PROP_AUTO_EXPOSURE,1)])]:
        fake=Camera()
        monkeypatch.setattr(cv2,'VideoCapture',lambda *args:fake)
        capture=CaptureThread({'type':'camera','index':0,'capture_mode':'native','exposure_mode':mode})
        capture._open()
        assert fake.calls == expected
    fake=Camera(accept=False)
    monkeypatch.setattr(cv2,'VideoCapture',lambda *args:fake)
    capture=CaptureThread({'type':'camera','index':0,'capture_mode':'native','exposure_mode':'motion'})
    capture._open()
    assert 'rejected the exposure' in capture.capture_warning


def test_exposure_does_not_reconfigure_unsupported_platforms_or_files(monkeypatch):
    from app.vision import capture as module
    for platform, source in [('darwin',{'type':'camera','index':0}),('win32',{'type':'video','path':'clip.avi'}),('linux',{'type':'stream','path':'rtsp://camera/live'})]:
        monkeypatch.setattr(module.sys,'platform',platform)
        fake=Camera()
        monkeypatch.setattr(cv2,'VideoCapture',lambda *args:fake)
        CaptureThread({**source,'capture_mode':'native','exposure_mode':'motion'})._open()
        assert not fake.calls


def test_linux_exposure_uses_v4l2_units_and_leaves_keep_unchanged(monkeypatch):
    from app.vision import capture as module
    monkeypatch.setattr(module.sys, 'platform', 'linux')
    for mode, expected in [('keep', []), ('motion', [(cv2.CAP_PROP_AUTO_EXPOSURE,1),(cv2.CAP_PROP_EXPOSURE,156)]), ('auto', [(cv2.CAP_PROP_AUTO_EXPOSURE,3)])]:
        fake=Camera()
        monkeypatch.setattr(cv2,'VideoCapture',lambda *args:fake)
        capture=CaptureThread({'type':'camera','path':'/dev/video0','capture_mode':'native','exposure_mode':mode})
        capture._open()
        assert fake.calls == expected
        assert capture.exposure_units == '100 µs'
        assert capture.capture_warning is None
        if mode == 'motion': assert capture.exposure == 156


def test_linux_normalized_controls_and_auto_fallback(monkeypatch):
    from app.vision import capture as module
    monkeypatch.setattr(module.sys, 'platform', 'linux')
    class V4L2(Camera):
        def set(self,key,value):
            if key == cv2.CAP_PROP_AUTO_EXPOSURE and value == 3:
                self.calls.append((key,value));return False
            return super().set(key,value)
    fake=V4L2();fake.props[cv2.CAP_PROP_MODE]=1
    monkeypatch.setattr(cv2,'VideoCapture',lambda *args:fake)
    capture=CaptureThread({'type':'camera','index':0,'capture_mode':'native','exposure_mode':'auto'})
    capture._open()
    assert fake.calls == [(cv2.CAP_PROP_MODE,0),(cv2.CAP_PROP_AUTO_EXPOSURE,3),(cv2.CAP_PROP_AUTO_EXPOSURE,0)]
    assert capture.capture_warning is None


def test_linux_rejected_manual_mode_does_not_change_exposure(monkeypatch):
    from app.vision import capture as module
    monkeypatch.setattr(module.sys, 'platform', 'linux')
    fake=Camera(accept=False)
    monkeypatch.setattr(cv2,'VideoCapture',lambda *args:fake)
    capture=CaptureThread({'type':'camera','index':0,'capture_mode':'native','exposure_mode':'motion'})
    capture._open()
    assert fake.calls == [(cv2.CAP_PROP_AUTO_EXPOSURE,1)]
    assert 'rejected' in capture.capture_warning


def test_default_exposure_is_short_on_linux_and_windows(monkeypatch):
    from app.vision import capture as module
    for platform, exposure in [('linux',156),('win32',-6)]:
        monkeypatch.setattr(module.sys,'platform',platform)
        fake=Camera()
        monkeypatch.setattr(cv2,'VideoCapture',lambda *args:fake)
        CaptureThread({'type':'camera','index':0,'capture_mode':'native'})._open()
        assert (cv2.CAP_PROP_EXPOSURE,exposure) in fake.calls
