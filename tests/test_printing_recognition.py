from pathlib import Path
import cv2
from app.config import CARDS_FILE, CARD_IMAGES_DIR
from app.game.card_db import CardDatabase
from app.vision.card_detector import rectify_quad
from app.vision.recognizer import CardRecognizer


def test_kiroshi_is_located_and_identified_on_busy_mat():
    rec = CardRecognizer(CardDatabase(CARDS_FILE), CARD_IMAGES_DIR)
    rec.build()
    board = cv2.imread(str(Path(__file__).parent/'fixtures'/'kiroshi-board.png'))
    quads = rec.locate(board)
    matches = [rec.recognize(rectify_quad(board, quad)) for quad in quads]
    assert any(m and m.card_id == 'cb-kiroshi-optics' and m.confidence >= .45 for m in matches)
