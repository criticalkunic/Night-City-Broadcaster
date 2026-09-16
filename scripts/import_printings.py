"""Import official printing artwork as recognition references, preserving canonical cards.
Run: python scripts/import_printings.py
"""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np

try:
    from .import_cards import CARDS_FILE, IMAGES_DIR, NETDECK_API, _get
except ImportError:  # Direct CLI invocation
    from import_cards import CARDS_FILE, IMAGES_DIR, NETDECK_API, _get


def art_signature(image):
    normalized = cv2.resize(image, (120, 168), interpolation=cv2.INTER_AREA)
    return normalized[25:105, 12:108].astype(np.float32)


def same_art(a, b):
    # Ignore set numbers / foil stamps; retain genuinely different illustrations.
    return float(np.abs(a-b).mean()) < 5.0


def import_card_printings(card):
    slug = card.get('url', '').rstrip('/').rsplit('/', 1)[-1]
    if not slug:
        return {'card_id': card['id'], 'error': 'Missing official card URL'}
    detail = json.loads(_get(NETDECK_API+'/'+quote(slug, safe='')))
    folder = IMAGES_DIR/'recognition'/card['id']
    known = []
    canonical = IMAGES_DIR/card['image'].removeprefix('/cards/images/')
    for path in [canonical, *sorted(folder.glob('*.png'))]:
        image = cv2.imread(str(path))
        if image is not None:
            known.append(art_signature(image))
    added, checked = 0, 0
    records = []
    for printing in detail.get('printings') or []:
        url = printing.get('image_url') or printing.get('source_image_url')
        if not url:
            continue
        checked += 1
        key = hashlib.sha256(str(printing['id']).encode()).hexdigest()[:20]
        target = folder/('official-'+key+'.png')
        record = {'printing_id': printing['id'], 'set': printing.get('set'), 'number': printing.get('collector_number')}
        if target.exists() and cv2.imread(str(target)) is not None:
            record['reference'] = target.name
            records.append(record)
            continue
        image = cv2.imdecode(np.frombuffer(_get(url), np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Unreadable artwork for '+card['id'])
        signature = art_signature(image)
        if any(same_art(signature, previous) for previous in known):
            record['reused_artwork'] = True
        else:
            folder.mkdir(parents=True, exist_ok=True)
            image = cv2.resize(image, (300, 420), interpolation=cv2.INTER_AREA)
            if not cv2.imwrite(str(target), image):
                raise ValueError('Could not save '+str(target))
            known.append(signature)
            record['reference'] = target.name
            added += 1
        records.append(record)
    return {'card_id': card['id'], 'checked': checked, 'added': added, 'printings': records}


def main():
    cards = json.loads(CARDS_FILE.read_text(encoding="utf-8"))
    def run(card):
        try:
            return import_card_printings(card)
        except Exception as error:
            return {'card_id': card['id'], 'error': type(error).__name__}
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(run, cards):
            results.append(result)
            print(result['card_id'], 'ERROR '+result['error'] if 'error' in result else f"{result['checked']} printings, {result['added']} new artworks", flush=True)
    manifest = IMAGES_DIR/'recognition'/'official-printings.json'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(results, indent=2))
    print('TOTAL',sum(r.get('checked',0) for r in results),'printings;',sum(r.get('added',0) for r in results),'new artworks;',sum('error' in r for r in results),'errors')
    return int(any('error' in r for r in results))

if __name__ == '__main__':
    raise SystemExit(main())
