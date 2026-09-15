import json
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from app.game.card_db import CardDatabase
from app.game.art_download import ArtDownload, import_cards, import_printings


def make_database(tmp_path, monkeypatch):
    images=tmp_path/'images'; images.mkdir()
    monkeypatch.setattr(import_cards, 'IMAGES_DIR', images)
    monkeypatch.setattr(import_printings, 'import_card_printings', lambda card: {'added':0})
    card={'id':'old','name':'My saved card','image':'/cards/images/old.webp','aliases':['custom']}
    path=tmp_path/'cards.json';path.write_text(json.dumps([card]))
    return CardDatabase(path), images


def test_current_catalog_adds_all_new_cards_and_preserves_existing(tmp_path, monkeypatch):
    db,images=make_database(tmp_path,monkeypatch)
    data=cv2.imencode('.webp',np.full((20,20,3),100,np.uint8))[1].tobytes()
    (images/'old.webp').write_bytes(data)
    (images/'learned.webp').write_bytes(data)
    remote=[{'id':str(i),'name':f'Card {i}','image':f'/cards/images/{i}.webp','_image_url':'image'} for i in range(164)]
    monkeypatch.setattr(import_cards,'fetch_netdeck_items',lambda: remote)
    monkeypatch.setattr(import_cards,'transform_items',lambda items: items)
    monkeypatch.setattr(import_cards,'_get',lambda url:data)
    job=ArtDownload();recognizer=Mock()
    job.update(running=True)
    job.refresh_catalog(db,recognizer)
    assert len(db.cards)==165 and db.get('163') is not None
    assert db.get('old')['aliases']==['custom']
    assert (images/'old.webp').read_bytes()==data and (images/'learned.webp').read_bytes()==data
    assert '_image_url' not in db.path.read_text()
    assert job.status()['added']==164 and job.status()['errors']==[]
    assert not job.status()['running']
    recognizer.build.assert_called_once()
    job.refresh_catalog(db,recognizer)
    assert len(db.cards)==165 and job.status()['added']==0


@pytest.mark.parametrize('remote', [[], [{'id':'bad'}]])
def test_invalid_catalog_preserves_saved_file(tmp_path,monkeypatch,remote):
    db,_=make_database(tmp_path,monkeypatch);original=db.path.read_bytes()
    monkeypatch.setattr(import_cards,'fetch_netdeck_items',lambda:remote)
    monkeypatch.setattr(import_cards,'transform_items',lambda items:items)
    job=ArtDownload();job.update(running=True);job.refresh_catalog(db,Mock())
    assert db.path.read_bytes()==original and len(db.cards)==1
    assert job.status()['errors'] and not job.status()['running']


def test_partial_catalog_fetch_failure_preserves_file(tmp_path,monkeypatch):
    db,_=make_database(tmp_path,monkeypatch);original=db.path.read_bytes()
    monkeypatch.setattr(import_cards,'fetch_netdeck_items',Mock(side_effect=RuntimeError('page 2 failed')))
    job=ArtDownload();job.refresh_catalog(db,Mock())
    assert db.path.read_bytes()==original and job.status()['errors']==['page 2 failed']


def test_catalog_check_shares_artwork_job_lock(tmp_path,monkeypatch):
    db,_=make_database(tmp_path,monkeypatch)
    job=ArtDownload();job.update(running=True)
    assert not job.start(db,Mock(),refresh_catalog=True)


def test_failed_artwork_can_be_retried_without_duplicate_cards(tmp_path,monkeypatch):
    db,images=make_database(tmp_path,monkeypatch)
    data=cv2.imencode('.webp',np.full((20,20,3),100,np.uint8))[1].tobytes()
    (images/'old.webp').write_bytes(data)
    remote=[{'id':'new','name':'New','image':'/cards/images/new.webp','_image_url':'image'}]
    monkeypatch.setattr(import_cards,'fetch_netdeck_items',lambda:remote)
    monkeypatch.setattr(import_cards,'transform_items',lambda items:items)
    monkeypatch.setattr(import_cards,'_get',Mock(side_effect=RuntimeError('offline')))
    job=ArtDownload();job.refresh_catalog(db,Mock())
    assert len(db.cards)==2 and job.status()['errors']
    monkeypatch.setattr(import_cards,'_get',lambda url:data)
    job.refresh_catalog(db,Mock())
    assert len(db.cards)==2 and not job.status()['errors']
    assert (images/'new.webp').read_bytes()==data


def test_catalog_endpoint_requests_catalog_refresh(monkeypatch):
    from app.api.cards import update_catalog
    from app.game.art_download import art_download
    start=Mock()
    monkeypatch.setattr(art_download,'start',start)
    update_catalog()
    assert start.call_args.kwargs=={'refresh_catalog':True}
