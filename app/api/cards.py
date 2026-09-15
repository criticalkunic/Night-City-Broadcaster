"""Card lookup and on-demand artwork downloads."""
from fastapi import APIRouter, HTTPException

from app import runtime

router = APIRouter()


@router.get("/cards/search")
def search_cards(q: str = "", limit: int = 20, type: str = ""):
    """Card autocomplete. `type=Legend` restricts to legend cards (used while
    assigning a legend slot; the latest-card search stays unrestricted since a
    legend can be the most recently played card)."""
    return {"results": runtime.card_db.search(q, limit=min(limit, 50), card_type=type or None)}


@router.get("/cards/artwork/status")
def artwork_status():
    from app.game.art_download import art_download
    return art_download.status()


@router.post("/cards/artwork/download")
def download_artwork():
    from app.game.art_download import art_download
    art_download.start(runtime.card_db, runtime.recognizer)
    return art_download.status()


@router.get("/cards/{card_id}")
def get_card(card_id: str):
    card = runtime.card_db.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Unknown card: {card_id}")
    return card
