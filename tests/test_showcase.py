import asyncio
import pytest
from fastapi import HTTPException
from app import runtime, showcase
from app.game.card_db import CardDatabase
from app.game.state_manager import StateManager

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(showcase, 'FILE', tmp_path/'showcase.json')
    monkeypatch.setattr(showcase, '_cached', None)
    monkeypatch.setattr(showcase, '_manual_override', False)
    monkeypatch.setattr(showcase, '_detected', None)
    monkeypatch.setattr(showcase, '_last_detected', None)
    db = CardDatabase(tmp_path/'cards.json')
    db.cards = [{'id':'a','name':'Alpha','card_type':'Unit'}, {'id':'b','name':'Beta','card_type':'Legend'}]
    db._by_id = {c['id']:c for c in db.cards}
    monkeypatch.setattr(runtime,'card_db',db)
    monkeypatch.setattr(runtime,'state_manager',StateManager())


def test_import_is_atomic_and_persistent():
    asyncio.run(showcase.import_deck(showcase.ImportRequest(text='3 Alpha\n1 Beta')))
    assert showcase.snapshot()['total'] == 4
    assert showcase.snapshot()['entries'][1]['section'] == 'Legends'
    with pytest.raises(HTTPException):
        asyncio.run(showcase.import_deck(showcase.ImportRequest(text='2 Alpha\n1 Missing')))
    assert showcase.load().entries[0].quantity == 3
    showcase._cached = None
    assert len(showcase.load().entries) == 2


def test_presentation_is_independent_from_match():
    asyncio.run(showcase.import_deck(showcase.ImportRequest(text='3 Alpha\n1 Beta')))
    before = runtime.state_manager.get_state().model_dump()
    asyncio.run(showcase.present(showcase.PresentRequest(action='next')))
    assert showcase.load().selected == 1
    asyncio.run(showcase.present(showcase.PresentRequest(action='next')))
    assert showcase.load().selected == 1
    assert runtime.state_manager.get_state().model_dump() == before
    assert runtime.snapshot_payload()['showcase']['pinned']


def test_bad_selection_and_duplicate_ids_rejected():
    asyncio.run(showcase.import_deck(showcase.ImportRequest(text='1 Alpha')))
    with pytest.raises(HTTPException):
        asyncio.run(showcase.present(showcase.PresentRequest(action='select',index=4)))
    with pytest.raises(HTTPException):
        asyncio.run(showcase.set_deck(showcase.Deck(entries=[showcase.Entry(card_id='a'),showcase.Entry(card_id='a')])))
    assert len(showcase.load().entries) == 1


def test_recognition_suggests_without_changing_match(monkeypatch):
    from types import SimpleNamespace
    from app.api import cameras
    monkeypatch.setattr(cameras,'load_overlay_config',lambda:{'activity_mode':'showcase'})
    monkeypatch.setattr(showcase,'_detected',None)
    before=runtime.state_manager.get_state().model_dump()
    event=cameras.apply_latest_card_match(1,SimpleNamespace(card_id='a'))
    assert event.type == 'showcase_detected'
    assert showcase.snapshot()['suggested_id'] == 'a'
    assert cameras.apply_legend_finding(1,0,False,None) == []
    assert runtime.state_manager.get_state().model_dump() == before


def test_pinning_holds_the_card_currently_followed(monkeypatch):
    asyncio.run(showcase.import_deck(showcase.ImportRequest(text='1 Alpha\n1 Beta')))
    asyncio.run(showcase.present(showcase.PresentRequest(action='pin')))
    monkeypatch.setattr(showcase,'_detected','b')
    asyncio.run(showcase.present(showcase.PresentRequest(action='pin')))
    assert showcase.load().selected == 1
    assert showcase.load().pinned


def test_phone_can_present_but_not_replace_deck(monkeypatch):
    import httpx
    from app.phone import phone_app
    asyncio.run(showcase.import_deck(showcase.ImportRequest(text='1 Alpha\n1 Beta')))
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=phone_app,client=('127.0.0.1',123)),base_url='http://127.0.0.1') as client:
            r=await client.post('/api/showcase/present',json={'action':'next'})
            assert r.status_code == 200
            assert r.json()['selected'] == 1
            assert (await client.post('/api/showcase/deck',json={})).status_code == 404
            assert (await client.post('/api/showcase/present',json={'action':'next'},headers={'Origin':'https://external.example'})).status_code == 403
    asyncio.run(check())


def test_supported_export_formats(monkeypatch):
    runtime.card_db.cards=[
        {'id':'panam','name':'Panam Palmer','subtitle':'Nomad Cavalry','card_type':'Legend'},
        {'id':'river','name':'River Ward','subtitle':'Detective on the Hunt','card_type':'Legend'},
        {'id':'v','name':'V','subtitle':'Streetkid','card_type':'Legend'},
        {'id':'unit','name':'Augmented Negotiators','card_type':'Unit'},
        {'id':'maton','name':'Gilded Matón','card_type':'Unit'}]
    runtime.card_db._by_id={c['id']:c for c in runtime.card_db.cards}
    official='// Legends (3)\n1 Panam Palmer: Nomad Cavalry\n1 River Ward: Detective on the Hunt\n1 V: Streetkid\n\n// Units (4)\n3 Augmented Negotiators\n1 Gilded Matón'
    sim='# Legends\n\n1x 075 Panam Palmer — Nomad Cavalry\n1x 039 River Ward — Detective on the Hunt\n1x 005a V — Streetkid\n\n# Main Deck\n3x 043 Augmented Negotiators\n1x 045 Gilded Matón'
    first=asyncio.run(showcase.import_deck(showcase.ImportRequest(text=official)))
    second=asyncio.run(showcase.import_deck(showcase.ImportRequest(text=sim)))
    assert first['entries']==second['entries']
    assert second['total']==7
    flattened=asyncio.run(showcase.import_deck(showcase.ImportRequest(text=official.replace('\n',' '))))
    assert flattened['entries']==first['entries']


def test_metric_panel_does_not_change_selected_card():
    asyncio.run(showcase.import_deck(showcase.ImportRequest(text='1 Alpha')))
    asyncio.run(showcase.present(showcase.PresentRequest(action='panel',panel='types')))
    assert showcase.load().panel=='types'
    assert showcase.load().selected==0


def test_manual_selection_releases_only_on_new_detection():
    asyncio.run(showcase.import_deck(showcase.ImportRequest(text='1 Alpha\n1 Beta')))
    asyncio.run(showcase.present(showcase.PresentRequest(action='detection',enabled=True)))
    showcase.observe('b')
    assert showcase.snapshot()['effective_selected'] == 1
    showcase.observe(None)
    assert showcase.snapshot()['effective_selected'] == 1
    showcase.observe('b')
    asyncio.run(showcase.present(showcase.PresentRequest(action='select',index=0)))
    showcase.observe('b')
    assert showcase.snapshot()['effective_selected'] == 0
    showcase.observe('a')
    showcase.observe('b')
    assert showcase.snapshot()['effective_selected'] == 1
    asyncio.run(showcase.present(showcase.PresentRequest(action='previous')))
    assert showcase.snapshot()['effective_selected'] == 0
    asyncio.run(showcase.present(showcase.PresentRequest(action='follow')))
    assert showcase.snapshot()['effective_selected'] == 1


def test_timestamped_library_preserves_independent_copies():
    asyncio.run(showcase.import_deck(showcase.ImportRequest(text='1 Alpha',title='First')))
    first=showcase.save_to_library()[0]
    deck=showcase.load();deck.title='Second';deck.entries[0].note='Combo piece'
    deck.display.camera=False
    asyncio.run(showcase.set_deck(deck))
    assert len(showcase.save_to_library()) == 2
    restored=asyncio.run(showcase.recall(showcase.RecallRequest(id=first['id'])))
    assert restored['title']=='First'
    assert restored['entries'][0]['note']==''
    assert restored['display']['camera']
    assert first['saved_at'].endswith('+00:00')


def test_drawings_and_display_persist_with_validation():
    from pydantic import ValidationError
    asyncio.run(showcase.set_display(showcase.Display(camera=False,layout="minimal")))
    stroke=showcase.Stroke(points=[(0,0),(1,1)])
    asyncio.run(showcase.draw(showcase.DrawRequest(action='add',stroke=stroke)))
    showcase._cached=None
    assert showcase.load().display.layout=="minimal"
    assert len(showcase.load().strokes)==1
    asyncio.run(showcase.draw(showcase.DrawRequest(action='undo')))
    assert not showcase.load().strokes
    with pytest.raises(ValidationError):
        showcase.Stroke(points=[(0,0),(1.2,1)])
    with pytest.raises(ValidationError):
        showcase.Display(layout="unknown")
    with pytest.raises(ValidationError):
        showcase.RecallRequest(id='../showcase')


def test_showcase_uses_only_its_board_region(monkeypatch):
    from types import SimpleNamespace
    from app.vision import showcase_regions
    monkeypatch.setattr(showcase_regions,'load_overlay_config',lambda:{'activity_mode':'showcase'})
    board={'x':0.1,'y':0.2,'w':0.7,'h':0.6}
    store=SimpleNamespace(cameras={'showcase_board_region':board})
    assert showcase_regions.detection_regions(store,1)=={}
    deck=showcase.load();deck.detect_latest=True;showcase.save(deck)
    assert showcase_regions.detection_regions(store,1)=={'card_play_region':board}
    assert showcase_regions.detection_regions(store,2)=={}


def test_replacing_deck_preserves_display_choices():
    asyncio.run(showcase.import_deck(showcase.ImportRequest(text='1 Alpha')))
    asyncio.run(showcase.set_display(showcase.Display(layout='minimal')))
    asyncio.run(showcase.set_charts(showcase.ChartOptions(sort='count_desc')))
    result=asyncio.run(showcase.import_deck(showcase.ImportRequest(text='1× Beta')))
    assert result['entries'][0]['card_id']=='b'
    assert result['display']['layout']=='minimal'
    assert result['chart_options']['sort']=='count_desc'


def test_corrected_width_is_bounded_and_persistent():
    from pydantic import ValidationError
    asyncio.run(showcase.set_display(showcase.Display(corrected_width=108)))
    showcase._cached=None
    assert showcase.load().display.corrected_width==108
    with pytest.raises(ValidationError):
        showcase.Display(corrected_width=201)


def test_corrected_scaling_controls_round_trip():
    display=showcase.Display(corrected_fit='contain',corrected_width=110,corrected_height=95,corrected_zoom=125,corrected_x=-10,corrected_y=5)
    asyncio.run(showcase.set_display(display))
    showcase._cached=None
    assert showcase.load().display==display


def test_live_drawing_preview_is_transient(monkeypatch):
    messages=[]
    async def broadcast(message): messages.append(message)
    monkeypatch.setattr(runtime.ws_manager,'broadcast',broadcast)
    stroke=showcase.Stroke(points=[(0,0),(0.5,0.5)],thickness=12)
    asyncio.run(showcase.preview_drawing(showcase.DrawingPreview(stroke=stroke)))
    assert messages[-1]['stroke']['thickness']==12
    assert not showcase.FILE.exists()
    assert not showcase.load().strokes
    asyncio.run(showcase.draw(showcase.DrawRequest(action='add',stroke=stroke)))
    showcase._cached=None
    assert showcase.load().strokes[0].thickness==12
    asyncio.run(showcase.preview_drawing(showcase.DrawingPreview()))
    assert messages[-1]['stroke'] is None
