"""Persistent presentation state, separate from live match tracking."""
import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
from app.config import CONFIG_DIR

FILE = CONFIG_DIR / 'showcase.json'
SECTIONS = ('Legends', 'Core units', 'Gear & support', 'Full deck')

class Entry(BaseModel):
    card_id: str = Field(max_length=200)
    quantity: int = Field(default=1, ge=1, le=99)
    section: Literal['Legends', 'Core units', 'Gear & support', 'Full deck'] = 'Core units'
    note: str = Field(default='', max_length=300)

class Stroke(BaseModel):
    thickness: int = Field(default=5, ge=1, le=24)
    color: Literal['#22d3ee', '#ffd23f', '#ef5969', '#ffffff'] = '#ffd23f'
    points: list[tuple[Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)]]] = Field(min_length=2, max_length=1000)

class ChartOptions(BaseModel):
    color: str = Field(default="", max_length=80)
    card_type: str = Field(default="", max_length=80)
    sort: Literal["default", "count_desc", "count_asc", "name"] = "default"
    tag_limit: Literal[5, 10, 20] = 5

class Display(BaseModel):
    corrected_width: int = Field(default=100, ge=50, le=200)
    corrected_height: int = Field(default=100, ge=50, le=200)
    corrected_zoom: int = Field(default=100, ge=100, le=200)
    corrected_x: int = Field(default=0, ge=-50, le=50)
    corrected_y: int = Field(default=0, ge=-50, le=50)
    corrected_fit: Literal["contain", "cover"] = "cover"
    layout: Literal["full", "minimal"] = "full"
    camera: bool = True
    sidebar: bool = True
    header: bool = True
    footer: bool = True
    summary: bool = True
    sections: bool = True
    drawings: bool = True

class Deck(BaseModel):
    title: str = Field(default='My deck walkthrough', max_length=100)
    entries: list[Entry] = Field(default_factory=list, max_length=200)
    selected: int = Field(default=0, ge=0)
    pinned: bool = True
    detect_latest: bool = False
    chart_options: ChartOptions = Field(default_factory=ChartOptions)
    display: Display = Field(default_factory=Display)
    strokes: list[Stroke] = Field(default_factory=list, max_length=100)
    panel: Literal["card", "types", "tags", "curve"] = "card"

_cached = None
_detected = None
_last_detected = None
_manual_override = False

def load():
    global _cached
    if _cached is None:
        try:
            _cached = Deck.model_validate_json(FILE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _cached = Deck()
    return _cached.model_copy(deep=True)

def save(deck):
    global _cached
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix('.tmp')
    tmp.write_text(deck.model_dump_json(indent=2), encoding='utf-8')
    tmp.replace(FILE)
    _cached = deck

def snapshot():
    from app import runtime
    deck = load()
    data = deck.model_dump()
    data['entries'] = []
    for entry in deck.entries:
        card = runtime.card_db.get(entry.card_id)
        summary = {key: card.get(key) for key in ('id', 'name', 'subtitle', 'display_name', 'image')} if card else None
        data['entries'].append({**entry.model_dump(), 'card': summary})
    from app.deck_metrics import metrics
    data['metrics'] = metrics(deck.entries, runtime.card_db, deck.chart_options.model_dump())
    data['suggested_id'] = _detected
    data['manual_override'] = _manual_override
    index = deck.selected
    if deck.detect_latest and not _manual_override:
        index = next((i for i,e in enumerate(deck.entries) if e.card_id == _last_detected), index)
    data['effective_selected'] = index
    data['total'] = sum(e.quantity for e in deck.entries)
    return data

def observe(card_id):
    global _detected, _last_detected, _manual_override
    if _detected == card_id:
        return None
    _detected = card_id
    if card_id is not None:
        _last_detected = card_id
    if card_id is not None and load().detect_latest:
        _manual_override = False
    from datetime import datetime, timezone
    from app.game.models import GameEvent
    return GameEvent(type='showcase_detected', description='Deck card detected',
                     timestamp=datetime.now(timezone.utc).isoformat())

router = APIRouter()

@router.get('/showcase')
def get_showcase():
    return snapshot()

async def publish(deck):
    from app import runtime
    save(deck)
    await runtime.ws_manager.broadcast(runtime.snapshot_payload())
    return snapshot()

@router.post('/showcase/deck')
async def set_deck(body: Deck):
    from app import runtime
    ids = [e.card_id for e in body.entries]
    if len(set(ids)) != len(ids):
        raise HTTPException(400, 'Use one row per card, with its quantity.')
    if any(runtime.card_db.get(cid) is None for cid in ids):
        raise HTTPException(400, 'One or more cards are missing from your catalog.')
    body.selected = min(body.selected, max(0, len(body.entries)-1))
    return await publish(body)

def normalize_name(value):
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r'\s*[—–:]\s*|\s+-\s+', ': ', value)
    return ' '.join(value.replace('’', "'").split()).casefold()

class ImportRequest(BaseModel):
    text: str = Field(max_length=30000)
    title: str = Field(default='My deck walkthrough', max_length=100)

@router.post('/showcase/import')
async def import_deck(body: ImportRequest):
    global _manual_override
    from app import runtime
    entries = {}
    errors = []
    text = body.text.replace("×", "x").lstrip("\ufeff")
    # Official exports use // Units (18); accepting flattened clipboard text
    # is safe here because a quantity must precede a name, not a section total.
    text = re.sub(r'//\s*[^\n]*?\(\d+\)', '\n', text)
    text = re.sub(r'(?<=\S)[ \t]+(?=[1-9]\d?x?[ \t]+(?:\d{3}[A-Za-z]?[ \t]+)?[A-Za-z])', '\n', text)
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith(('#', '//')):
            continue
        match = re.fullmatch(r'\s*(\d+)\s*x?\s+(.+?)\s*', line, re.I)
        if not match:
            errors.append(f'Line {number}: use “3 Card name”.')
            continue
        quantity = int(match[1])
        raw_name = re.sub(r'^\d{3}[A-Za-z]?\s+', '', match[2])
        name = normalize_name(raw_name)
        matches = []
        for card in runtime.card_db.cards:
            labels = [card['id'], card.get('name', ''), card.get('display_name', ''),
                      *card.get('aliases', [])]
            if card.get('subtitle'):
                labels.append(card['name'] + ': ' + card['subtitle'])
            if name in [normalize_name(v) for v in labels if v]:
                matches.append(card)
        if len(matches) != 1:
            errors.append(f'Line {number}: {match[2]} is ambiguous or not found. Use its full name and subtitle, or card ID.')
            continue
        card = matches[0]
        cid = card['id']
        quantity += entries[cid].quantity if cid in entries else 0
        if not 1 <= quantity <= 99:
            errors.append(f'Line {number}: quantity must be between 1 and 99.')
            continue
        section = 'Legends' if card.get('card_type') == 'Legend' else 'Core units' if card.get('card_type') == 'Unit' else 'Gear & support'
        entries[cid] = Entry(card_id=cid, quantity=quantity, section=section)
    if errors:
        raise HTTPException(400, '\n'.join(errors))
    if not entries or len(entries) > 200:
        raise HTTPException(400, 'Enter between 1 and 200 different cards.')
    _manual_override = True
    current = load()
    return await publish(Deck(title=body.title, entries=list(entries.values()),
                              display=current.display, chart_options=current.chart_options,
                              detect_latest=current.detect_latest))

class PresentRequest(BaseModel):
    action: Literal['next', 'previous', 'select', 'pin', 'suggestion', 'panel', 'follow', 'detection']
    index: int = Field(default=0, ge=0)
    panel: Literal['card', 'types', 'tags', 'curve'] = 'card'
    enabled: bool = False

@router.post('/showcase/present')
async def present(body: PresentRequest):
    global _manual_override
    deck = load()
    if body.action == 'detection':
        deck.detect_latest = body.enabled
        _manual_override = False
    elif body.action == 'follow':
        _manual_override = False
        deck.pinned = False
    elif body.action == 'panel':
        deck.panel = body.panel
    elif body.action == 'pin':
        if not deck.pinned:
            deck.selected = next((i for i,e in enumerate(deck.entries) if e.card_id == _detected), deck.selected)
        deck.pinned = not deck.pinned
    elif deck.entries:
        if body.action == 'select':
            if body.index >= len(deck.entries):
                raise HTTPException(400, 'That card is no longer in the deck.')
            deck.selected = body.index
        elif body.action == 'suggestion':
            cid = snapshot()['suggested_id']
            index = next((i for i,e in enumerate(deck.entries) if e.card_id == cid), None)
            if index is None:
                raise HTTPException(400, 'The detected card is not in this deck.')
            deck.selected = index
        else:
            deck.selected = max(0, min(len(deck.entries)-1, snapshot()['effective_selected'] + (1 if body.action == 'next' else -1)))
        deck.pinned = True
        _manual_override = True
        deck.panel = 'card'
    return await publish(deck)


@router.get('/showcase/library')
def library():
    folder = FILE.parent / 'decks'
    result = []
    for file in folder.glob('*.json'):
        try:
            record = json.loads(file.read_text(encoding='utf-8'))
            deck = Deck.model_validate(record['deck'])
            result.append({'id':file.stem, 'title':deck.title, 'saved_at':record['saved_at'],
                           'cards':sum(e.quantity for e in deck.entries)})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(result, key=lambda item:item['saved_at'], reverse=True)

@router.post('/showcase/library/save')
def save_to_library():
    deck = load()
    if not deck.entries:
        raise HTTPException(400, 'Add cards before saving a deck.')
    folder = FILE.parent / 'decks'
    folder.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex
    record = {'saved_at':datetime.now(timezone.utc).isoformat(), 'deck':deck.model_dump()}
    temporary = folder / (key + '.tmp')
    temporary.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
    temporary.replace(folder / (key + '.json'))
    return library()

class RecallRequest(BaseModel):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')

@router.post('/showcase/library/recall')
async def recall(body: RecallRequest):
    global _manual_override
    try:
        record = json.loads((FILE.parent / 'decks' / (body.id + '.json')).read_text(encoding='utf-8'))
        deck = Deck.model_validate(record['deck'])
    except (OSError, ValueError, KeyError):
        raise HTTPException(404, 'That saved deck could not be opened.')
    _manual_override = True
    return await publish(deck)

@router.post('/showcase/display')
async def set_display(body: Display):
    deck = load()
    deck.display = body
    return await publish(deck)

class DrawRequest(BaseModel):
    action: Literal['add', 'undo', 'clear']
    stroke: Stroke | None = None

@router.post('/showcase/draw')
async def draw(body: DrawRequest):
    deck = load()
    if body.action == 'clear':
        deck.strokes = []
    elif body.action == 'undo':
        deck.strokes = deck.strokes[:-1]
    elif body.stroke:
        if len(deck.strokes) >= 100:
            raise HTTPException(400, 'Clear or undo a drawing before adding more.')
        if any(not (0 <= x <= 1 and 0 <= y <= 1) for x,y in body.stroke.points):
            raise HTTPException(400, 'Draw inside the board area.')
        deck.strokes.append(body.stroke)
    else:
        raise HTTPException(400, 'A stroke is required.')
    return await publish(deck)

@router.post('/showcase/charts')
async def set_charts(body: ChartOptions):
    deck = load()
    deck.chart_options = body
    return await publish(deck)


class DrawingPreview(BaseModel):
    stroke: Stroke | None = None

@router.post('/showcase/draw-preview')
async def preview_drawing(body: DrawingPreview):
    from app import runtime
    await runtime.ws_manager.broadcast({'type':'showcase_drawing', 'stroke':body.stroke.model_dump() if body.stroke else None})
    return {'ok':True}
