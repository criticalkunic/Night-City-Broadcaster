"""Importer transform tests (no network): netdeck API item -> local schema."""
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "import_cards.py"
spec = importlib.util.spec_from_file_location("import_cards", SCRIPT)
import_cards = importlib.util.module_from_spec(spec)
sys.modules["import_cards"] = import_cards
spec.loader.exec_module(import_cards)

ITEM = {
    "id": "81a8dec7-9541-4020-93e1-7d798a57dcbc",
    "external_id": "cb-v-streetkid",
    "name": "V",
    "subname": "Streetkid",
    "display_name": "V: Streetkid",
    "slug": "v-streetkid",
    "rules_text": "{Call} Trash 3.",
    "flavor_text": None,
    "printing_id": "3fc63c58-5954-4744-a5af-047bfc5cb159",
    "set": {"code": "welcometonightcityretail", "name": "Welcome to Night City — Retail"},
    "rarity": "Rare",
    "image_url": "https://example.invalid/render-mq9zzfnq.webp?Expires=1&Signature=abc",
    "color": "Red",
    "card_type": "Legend",
    "classifications": ["Merc"],
    "keywords": [],
    "cost": 5,
    "power": "6",
    "ram": None,
    "artist": "Olgierd Ciszak",
    "print_number": "005a",
}


def test_item_to_card_schema():
    card = import_cards.netdeck_item_to_card(ITEM)
    assert card["id"] == "cb-v-streetkid"
    assert card["name"] == "V" and card["subtitle"] == "Streetkid"
    assert card["image"] == "/cards/images/cb-v-streetkid.webp"
    assert card["set"] == "welcometonightcityretail" and card["number"] == "005a"
    assert card["card_type"] == "Legend" and card["color"] == "Red"
    assert card["cost"] == 5 and card["power"] == 6 and card["ram"] is None
    assert "V: Streetkid" in card["aliases"] and "v streetkid" in card["aliases"]
    assert card["url"] == "https://cyberpunktcg.com/cards/v-streetkid"
    assert card["_image_url"].startswith("https://example.invalid/")


def test_transform_dedupes_and_sorts():
    other = {**ITEM, "external_id": "cb-aaa", "name": "Aaa", "display_name": "Aaa",
             "subname": None, "slug": "aaa", "print_number": "001"}
    cards = import_cards.transform_items([ITEM, other, ITEM])
    assert [c["id"] for c in cards] == ["cb-aaa", "cb-v-streetkid"]
    assert cards[0]["aliases"] == []  # display_name == name, slug == name


def test_item_without_id_is_skipped():
    assert import_cards.netdeck_item_to_card({"name": "nameless"}) is None


def test_write_strips_private_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(import_cards, "CARDS_FILE", tmp_path / "cards.json")
    import_cards.write_cards([import_cards.netdeck_item_to_card(ITEM)])
    text = (tmp_path / "cards.json").read_text()
    assert "_image_url" not in text and "example.invalid" not in text


def test_validate_downloaded_catalog(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(import_cards, 'CARDS_FILE', tmp_path/'cards.json')
    monkeypatch.setattr(import_cards, 'IMAGES_DIR', tmp_path)
    (tmp_path/'cards.json').write_text(json.dumps([{'id':'a','name':'A','image':'/cards/images/a.png'}]))
    assert import_cards.validate() == 1
    (tmp_path/'a.png').touch()
    assert import_cards.validate() == 0


def test_printings_import_preserves_card_and_multiple_arts(tmp_path, monkeypatch):
    import cv2
    import numpy as np
    spec = importlib.util.spec_from_file_location('import_printings', SCRIPT.parent/'import_printings.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'IMAGES_DIR', tmp_path)
    base = np.zeros((420, 300, 3), np.uint8)
    alt = np.full_like(base, (220, 80, 50))
    cv2.imwrite(str(tmp_path/'card.png'), base)
    import json
    detail = {'printings':[{'id':'base','image_url':'base'}, {'id':'alt','image_url':'alt'}, {'id':'duplicate','image_url':'alt'}]}
    payload = {'base': cv2.imencode('.png',base)[1].tobytes(), 'alt':cv2.imencode('.png',alt)[1].tobytes()}
    monkeypatch.setattr(module, '_get', lambda url: payload[url] if url in payload else json.dumps(detail).encode())
    card = {'id':'card','image':'/cards/images/card.png','url':'https://cyberpunktcg.com/cards/card'}
    result = module.import_card_printings(card)
    assert result['checked'] == 3 and result['added'] == 1
    assert len(list((tmp_path/'recognition'/'card').glob('*.png'))) == 1
    assert module.import_card_printings(card)['added'] == 0
    assert np.array_equal(cv2.imread(str(tmp_path/'card.png')), base)


def test_catalog_fetch_paginates_using_remote_count(monkeypatch):
    import json
    pages = iter([{'items':[{'id':i} for i in range(100)],'total':164},
                  {'items':[{'id':i} for i in range(100,164)],'total':164}])
    calls=[]
    def get(url):
        calls.append(url)
        return json.dumps(next(pages)).encode()
    monkeypatch.setattr(import_cards,'_get',get)
    assert len(import_cards.fetch_netdeck_items())==164
    assert 'offset=100' in calls[1]


def test_catalog_rejects_truncated_download(monkeypatch):
    import json, pytest
    pages=iter([{'items':[{'id':1}],'total':2},{'items':[],'total':2}])
    monkeypatch.setattr(import_cards,'_get',lambda _:json.dumps(next(pages)).encode())
    with pytest.raises(RuntimeError):import_cards.fetch_netdeck_items()
