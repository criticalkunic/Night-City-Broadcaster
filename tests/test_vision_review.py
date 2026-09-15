from types import SimpleNamespace

import cv2
import numpy as np

from app.vision.background import MatBackground
from app.vision.card_detector import DetectionWorker, DEFAULT_DETECTION, Detection
from tests.test_live_recognition import FakeService, _match, _legend_service
from tests.test_recognizer import synth_db, recognizer, synth_card
from app.vision.calibration import CalibrationStore


def test_scene_localization_survives_shadow_without_card_outline(recognizer):
    card = cv2.resize(synth_card(5), (130,182))
    scene = np.full((400,600,3), 45, np.uint8)
    scene[110:292,350:480] = card
    scene[:,:430] = (scene[:,:430].astype(float)*.55).astype(np.uint8)
    quads = recognizer.locate(scene)
    assert any(np.linalg.norm(q.mean(axis=0)-[415,201]) < 20 for q in quads)
    assert recognizer.locate(np.full_like(scene,50)) == []


def test_all_play_candidates_checked_and_same_location_replacement(tmp_path, monkeypatch):
    service = FakeService(CalibrationStore(tmp_path/'c',tmp_path/'r'),None)
    worker = DetectionWorker(service)
    candidates=[]
    for x in [.2,.5,.8]:
        q=np.float32([[x*800-30,200],[x*800+30,200],[x*800+30,284],[x*800-30,284]])
        candidates.append(Detection(q,(x-.04,.3,.08,.14),(x,.4),.03,crop=np.zeros((420,300,3),np.uint8)))
    worker.detector.detect_all=lambda *args,**kwargs:(candidates,None)
    worker._candidate_crops=lambda frame,player,ds,config:[(str(ds[0].center[0]),np.zeros((420,300,3),np.uint8))]
    identities={'.5':'A','.8':'B'}
    def recognize(crops,card_type=None):
        name=identities.get(crops[0][0].removeprefix('0'))
        if name is None:return None
        m=_match(.9);m.card_id=name;return m
    service.recognize_crops=recognize
    now=[0.0]
    monkeypatch.setattr('app.vision.card_detector.time.monotonic',lambda:now[0])
    for tick in range(12):
        now[0]=tick*.3;worker._process(1,{**DEFAULT_DETECTION,'stable_frames':2})
    assert (1,'A') in service.applied and (1,'B') in service.applied
    identities['.5']='C'
    for tick in range(12,24):
        now[0]=tick*.3;worker._process(1,{**DEFAULT_DETECTION,'stable_frames':2})
    assert (1,'C') in service.applied
    visible=worker.results()['players']['1']['visible_cards']
    assert {m['card_id'] for m in visible}=={'C','B'}


def test_dark_legend_is_still_recognized_and_rechecked(tmp_path,monkeypatch):
    service=_legend_service(tmp_path,_match(.9))
    # Force pessimistic brightness classification independently of recognition.
    monkeypatch.setattr('app.vision.legends.classify_legend_slot',lambda *args:
        dict(present=False,face_up=False,back_visible=False))
    worker=DetectionWorker(service)
    for _ in range(2):worker._check_legends(1,DEFAULT_DETECTION)
    assert (1,0,True,'cb-x') in service.legend_events
    replacement=_match(.9);replacement.card_id='replacement';service.match=replacement
    for _ in range(6):worker._check_legends(1,DEFAULT_DETECTION)
    assert (1,0,True,'replacement') in service.legend_events


def test_shadow_does_not_become_whole_foreground(tmp_path):
    y,x=np.mgrid[:300,:500]
    mat=np.stack([80+40*np.sin(x/20),100+50*np.cos(y/30),140+30*np.sin((x+y)/25)],axis=2).astype(np.uint8)
    model=MatBackground(tmp_path/'mat.npz');model.capture(mat,'a')
    gain=.55+.45/(1+np.exp(-(x-250)/20))
    shadow=(mat*gain[:,:,None]).astype(np.uint8)
    foreground=model.foreground(shadow,'a')
    assert (foreground[:,:,0]>0).mean()<.05
