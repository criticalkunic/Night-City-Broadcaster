"""Download the legend back into user data, never into the application bundle."""
from pathlib import Path
import cv2
import numpy as np
from scripts import import_cards

# Complete card-back scan from the retailer's public card gallery.
CARD_BACK_URL = 'https://beyondtcg.co.uk/cdn/shop/files/B098_back.webp?width=900'


def card_back_path(images):
    return Path(images).parent / 'assets' / 'card-back.webp'


def has_card_back(images):
    path = card_back_path(images)
    return path.is_file() and cv2.imread(str(path)) is not None


def ensure_card_back(images):
    if has_card_back(images):
        return
    raw = import_cards._get(CARD_BACK_URL)
    frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError('Legend card-back download is not a readable image')
    # Remove the scan's white surround using the yellow card boundary.
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([18, 100, 100]), np.array([42, 255, 255]))
    points = cv2.findNonZero(mask)
    if points is None:
        raise ValueError('Legend card-back source has changed: yellow card not found')
    x, y, w, h = cv2.boundingRect(points)
    if not .60 < w / h < .80 or h < 200:
        raise ValueError('Legend card-back source has an unexpected shape')
    ok, encoded = cv2.imencode('.webp', frame[y:y+h, x:x+w])
    if not ok:
        raise ValueError('Could not save legend card back')
    target = card_back_path(images)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.download')
    temporary.write_bytes(encoded.tobytes())
    temporary.replace(target)
