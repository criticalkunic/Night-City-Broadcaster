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
    capture=CaptureThread({'type':'camera','path':'/dev/video1','capture_mode':'mjpeg1080'})
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
    for source in ({'type':'video','path':'clip.avi'}, {'type':'stream','path':'rtsp://camera/live'}, {'type':'camera','index':1,'capture_mode':'native'}):
        fake=Camera()
        monkeypatch.setattr(cv2,'VideoCapture',lambda *args:fake)
        CaptureThread(source)._open()
        assert not fake.calls
