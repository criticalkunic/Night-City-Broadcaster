"""Card recognizer tests on a synthetic card DB (no network, no real card art)."""
import json
import random

import cv2
import numpy as np
import pytest

from app.game.card_db import CardDatabase
from app.vision.recognizer import CardRecognizer, Match

random.seed(7)
np.random.seed(7)


def synth_card(seed: int, size=(300, 420)) -> np.ndarray:
    """Textured, colourful fake card: random blobs + shapes + text so ORB has
    distinctive features and thumbnails differ in colour layout."""
    rng = np.random.default_rng(seed)
    w, h = size
    img = np.full((h, w, 3), rng.integers(30, 120, size=3), dtype=np.uint8)
    for _ in range(40):
        color = tuple(int(c) for c in rng.integers(0, 255, size=3))
        cx, cy = int(rng.integers(0, w)), int(rng.integers(0, h))
        r = int(rng.integers(8, 60))
        if rng.random() < 0.5:
            cv2.circle(img, (cx, cy), r, color, -1)
        else:
            cv2.rectangle(img, (cx - r, cy - r), (cx + r, cy + r), color, -1)
    for i in range(6):
        cv2.putText(img, f"CARD {seed} L{i}", (10, 60 + i * 55), cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, (255, 255, 255), 2)
    cv2.rectangle(img, (4, 4), (w - 5, h - 5), (230, 200, 40), 6)
    return img


@pytest.fixture(scope="module")
def synth_db(tmp_path_factory):
    root = tmp_path_factory.mktemp("cards")
    images = root / "images"
    images.mkdir()
    cards = []
    for i in range(12):
        name = f"card-{i:02d}"
        cv2.imwrite(str(images / f"{name}.png"), synth_card(i))
        cards.append({
            "id": name, "name": f"Card {i}", "subtitle": f"Sub {i}",
            "image": f"/cards/images/{name}.png",
            "card_type": "Legend" if i < 4 else "Unit",
        })
    (root / "cards.json").write_text(json.dumps(cards))
    return CardDatabase(root / "cards.json"), images


@pytest.fixture(scope="module")
def recognizer(synth_db):
    db, images = synth_db
    rec = CardRecognizer(db, images)
    assert rec.build() == 12
    assert rec.ready
    return rec


def degrade(img: np.ndarray, rotate: bool = False, seed: int = 0) -> np.ndarray:
    """Camera-like degradation: perspective jitter, downscale, blur, exposure."""
    rng = np.random.default_rng(seed)
    h, w = img.shape[:2]
    j = lambda: float(rng.uniform(-18, 18))
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[j(), j()], [w + j(), j()], [w + j(), h + j()], [j(), h + j()]])
    out = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h),
                              borderValue=(40, 60, 35))
    out = cv2.resize(cv2.resize(out, (w // 3, h // 3)), (w, h))
    out = cv2.GaussianBlur(out, (5, 5), 0)
    out = cv2.convertScaleAbs(out, alpha=0.85, beta=15)
    return cv2.rotate(out, cv2.ROTATE_180) if rotate else out


def test_recognizes_clean_and_degraded(recognizer, synth_db):
    db, _ = synth_db
    for card in db.cards:
        img = synth_card(int(card["id"].split("-")[1]))
        match = recognizer.recognize(img)
        assert match is not None and match.card_id == card["id"]
        assert match.confidence >= recognizer.config["min_confidence"]
        assert match.rotated is False

        match = recognizer.recognize(degrade(img, seed=3))
        assert match.card_id == card["id"], card["id"]
        assert match.confidence >= recognizer.config["min_confidence"]


def test_recognizes_upside_down(recognizer):
    match = recognizer.recognize(degrade(synth_card(5), rotate=True, seed=1))
    assert match.card_id == "card-05"
    assert match.rotated is True
    assert match.confidence >= recognizer.config["min_confidence"]


def test_landscape_crop_is_normalized(recognizer):
    landscape = cv2.rotate(synth_card(7), cv2.ROTATE_90_COUNTERCLOCKWISE)
    match = recognizer.recognize(landscape)
    assert match.card_id == "card-07"


def test_card_type_filter(recognizer):
    # Querying a Unit while restricted to Legends must still return a Legend,
    # and a Legend query restricted to Legends returns itself.
    match = recognizer.recognize(synth_card(9), card_type="Legend")
    assert match.card_type == "Legend"
    match = recognizer.recognize(synth_card(2), card_type="Legend")
    assert match.card_id == "card-02"


def test_blank_crop_is_low_confidence(recognizer):
    blank = np.full((420, 300, 3), (60, 60, 60), dtype=np.uint8)
    match = recognizer.recognize(blank)
    assert match is not None  # best effort is still reported...
    assert match.confidence < recognizer.config["min_confidence"]  # ...but not confident
    assert match.inliers < recognizer.config["min_inliers"]


def test_empty_index_returns_none(tmp_path):
    (tmp_path / "cards.json").write_text("[]")
    rec = CardRecognizer(CardDatabase(tmp_path / "cards.json"), tmp_path)
    assert rec.build() == 0
    assert rec.ready is False
    assert rec.recognize(synth_card(1)) is None


def test_match_as_dict_roundtrip():
    match = Match(card_id="x", name="X", subtitle="", image="/i.png", confidence=0.87,
                  inliers=20, thumb_score=0.7, rotated=True, card_type="Unit")
    data = match.as_dict()
    assert data["card_id"] == "x" and data["confidence"] == 0.87 and data["rotated"] is True


def test_recognize_many_picks_best_crop(recognizer):
    """Merged-blob scenario: the whole crop is two cards, the halves are single
    cards. The most confident (a clean half) wins and is tagged with its label."""
    a, b = synth_card(3), synth_card(8)
    stacked = np.vstack([cv2.resize(a, (300, 210)), cv2.resize(b, (300, 210))])
    crops = [("quad0", stacked), ("split-top", cv2.resize(a, (300, 420))), ("split-bottom", b)]
    match = recognizer.recognize_many(crops)
    assert match.card_id in ("card-03", "card-08")
    assert match.source in ("split-top", "split-bottom")
    assert match.confidence >= recognizer.config["min_confidence"]


def test_confidence_needs_margin():
    cfg = {"min_inliers": 16}
    strong = CardRecognizer._confidence(48, 10, 0.6, cfg)
    ambiguous = CardRecognizer._confidence(18, 16, 0.6, cfg)
    weak = CardRecognizer._confidence(8, 6, 0.9, cfg)
    assert strong > 0.8
    assert ambiguous < 0.45
    assert weak < 0.45


def test_alternate_reference_shares_identity_without_ambiguity(tmp_path):
    images = tmp_path / "images"
    references = images / "recognition" / "jackie"
    references.mkdir(parents=True)
    standard, alternate = synth_card(1), synth_card(6)
    cv2.imwrite(str(images / "jackie.png"), standard)
    cv2.imwrite(str(references / "alternate.png"), alternate)
    # Duplicate references must not reduce the winning card's confidence.
    cv2.imwrite(str(references / "duplicate.png"), alternate)
    (tmp_path / "cards.json").write_text(json.dumps([
        {"id": "jackie", "name": "Jackie", "image": "/cards/images/jackie.png", "card_type": "Legend"}
    ]))
    recognizer = CardRecognizer(CardDatabase(tmp_path / "cards.json"), images)
    assert recognizer.build() == 3
    for image in (standard, degrade(alternate, seed=3)):
        match = recognizer.recognize(image, card_type="Legend")
        assert match.card_id == "jackie"
        assert match.confidence >= 0.45
        assert match.image == "/cards/images/jackie.png"
        assert match.runner_up_inliers == 0

@pytest.mark.parametrize('color', [(0, 0, 240), (0, 230, 230), (30, 30, 30)])
def test_legends_reject_solid_sleeves(recognizer, color):
    crop = np.full((420, 300, 3), color, np.uint8)
    assert recognizer.recognize(crop, card_type='Legend') is None
    # Played-card path still reports a guess for debugging, not a sleeve veto.
    assert recognizer.recognize(crop) is not None


def test_legends_reject_repeated_sleeve_pattern(recognizer):
    crop = np.zeros((420, 300, 3), np.uint8)
    for y in range(0, 420, 24):
        for x in range(0, 300, 24):
            cv2.circle(crop, (x+12,y+12), 8, (0,220,220), -1)
    match = recognizer.recognize(crop, card_type='Legend')
    assert match is None or match.confidence < .45


def test_confirmed_alt_art_reference_recognizes_new_art(tmp_path):
    images = tmp_path/'images'
    folder = images/'recognition'/'alt-card'
    folder.mkdir(parents=True)
    cv2.imwrite(str(images/'base.png'), synth_card(61))
    cards = [{'id':'alt-card', 'name':'Alt Card', 'image':'/cards/images/base.png', 'card_type':'Unit'}]
    (tmp_path/'cards.json').write_text(json.dumps(cards))
    db = CardDatabase(tmp_path/'cards.json')
    rec = CardRecognizer(db, images)
    rec.build()
    sample = synth_card(982)
    cv2.imwrite(str(folder/'confirmed.png'), sample)
    assert rec.build() == 2
    match = rec.recognize(cv2.resize(sample, (180,252)))
    assert match.card_id == 'alt-card' and match.confidence >= .45
    assert match.image == '/cards/images/base.png'

@pytest.mark.parametrize('upside_down', [False, True])
def test_legend_orientation_uses_geometry_when_color_votes_for_opposite(recognizer, monkeypatch, upside_down):
    import app.vision.recognizer as module
    original = module._thumb_vector
    # Simulate misleading alternate-art colors: thumbnail evidence favors 180°.
    monkeypatch.setattr(module, '_thumb_vector', lambda image: original(cv2.rotate(image, cv2.ROTATE_180)))
    sample = synth_card(0)
    if upside_down:
        sample = cv2.rotate(sample, cv2.ROTATE_180)
    match = recognizer.recognize(sample, card_type='Legend')
    assert match.card_id == 'card-00' and match.confidence >= .45
    assert match.rotated is upside_down
