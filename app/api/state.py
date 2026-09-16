"""REST endpoints for game state. Every mutation broadcasts a fresh snapshot."""
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import runtime
from app.config import load_overlay_config, save_overlay_config
from app.game.state_manager import StateError

router = APIRouter()


class MoveRequest(BaseModel):
    location: str


class RollRequest(BaseModel):
    value: int


class LatestCardRequest(BaseModel):
    player: int = Field(ge=1, le=2)
    card_id: str
    source: Literal["manual", "vision"] = "manual"
    confidence: Optional[float] = None


class LegendRequest(BaseModel):
    # card_id: set/replace the slot's card ("" clears it). revealed: flip state.
    card_id: Optional[str] = None
    revealed: Optional[bool] = None


class CredRequest(BaseModel):
    value: int = Field(ge=0, le=99)


class NamesRequest(BaseModel):
    player1_name: str = "Player 1"
    player2_name: str = "Player 2"


class StartMatchRequest(BaseModel):
    player1_name: Optional[str] = None
    player2_name: Optional[str] = None


class OverlayConfigRequest(BaseModel):
    config: dict


async def _commit(action):
    """Run a state mutation, translate validation errors, broadcast the result."""
    try:
        event = action()
    except StateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    payload = runtime.snapshot_payload(event)
    await runtime.ws_manager.broadcast(payload)
    return payload


@router.get("/state")
def get_state():
    return runtime.snapshot_payload()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "ws_clients": runtime.ws_manager.count,
        "cards_loaded": len(runtime.card_db.cards),
    }


@router.post("/dice/{die_id}/move")
async def move_die(die_id: str, body: MoveRequest):
    return await _commit(lambda: runtime.state_manager.move_die(die_id, body.location))


@router.post("/dice/{die_id}/roll")
async def roll_die(die_id: str, body: RollRequest):
    return await _commit(lambda: runtime.state_manager.roll_die(die_id, body.value))


@router.post("/card/latest")
async def set_latest_card(body: LatestCardRequest):
    card = runtime.card_db.get(body.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Unknown card: {body.card_id}")
    return await _commit(
        lambda: runtime.state_manager.set_latest_card(
            player=body.player,
            card_id=card["id"],
            name=card.get("name", ""),
            subtitle=card.get("subtitle", ""),
            image=card.get("image", ""),
            source=body.source,
            confidence=body.confidence,
        )
    )


class LegendSwapRequest(BaseModel):
    a: int
    b: int


@router.post("/legends/{player}/swap")
async def swap_legends(player: int, body: LegendSwapRequest):
    """Rearrange a player's legends (operator drag-and-drop / keyboard move)."""
    return await _commit(lambda: runtime.state_manager.swap_legends(player, body.a, body.b))


@router.post("/legends/{player}/{slot}")
async def set_legend(player: int, slot: int, body: LegendRequest):
    if body.card_id is None and body.revealed is None:
        raise HTTPException(status_code=400, detail="Provide card_id and/or revealed")
    payload = None
    if body.card_id is not None:
        if body.card_id == "":
            payload = await _commit(lambda: runtime.state_manager.set_legend(player, slot, None))
        else:
            card = runtime.card_db.get(body.card_id)
            if card is None:
                raise HTTPException(status_code=404, detail=f"Unknown card: {body.card_id}")
            payload = await _commit(
                lambda: runtime.state_manager.set_legend(
                    player, slot, card["id"],
                    name=card.get("name", ""),
                    subtitle=card.get("subtitle", ""),
                    image=card.get("image", ""),
                )
            )
    if body.revealed is not None:
        payload = await _commit(
            lambda: runtime.state_manager.reveal_legend(player, slot, body.revealed)
        )
    return payload


@router.post("/cred/{player}")
async def set_cred(player: int, body: CredRequest):
    return await _commit(lambda: runtime.state_manager.set_street_cred(player, body.value))


@router.post("/match/names")
async def set_names(body: NamesRequest):
    return await _commit(
        lambda: runtime.state_manager.set_player_names(body.player1_name, body.player2_name)
    )


@router.post("/match/start")
async def start_match(body: StartMatchRequest):
    return await _commit(
        lambda: runtime.state_manager.start_match(body.player1_name, body.player2_name)
    )


@router.post("/match/swap")
async def swap_sides():
    return await _commit(runtime.state_manager.swap_sides)


@router.post("/undo")
async def undo():
    return await _commit(runtime.state_manager.undo)


@router.post("/redo")
async def redo():
    return await _commit(runtime.state_manager.redo)


@router.post("/reset")
async def reset():
    return await _commit(runtime.state_manager.reset_match)


@router.get("/config")
def get_config():
    return load_overlay_config()


@router.post("/config")
async def set_config(body: OverlayConfigRequest):
    merged = save_overlay_config(body.config)
    await runtime.ws_manager.broadcast({**runtime.snapshot_payload(), "type": "config_updated", "config": merged})
    return merged


class GigRequest(BaseModel):
    value: Optional[int] = None


@router.post("/solo/gigs/{die_id}")
async def update_gig(die_id: str, body: GigRequest):
    return await _commit(lambda: runtime.state_manager.set_gig(die_id, body.value))


@router.post("/solo/card/clear")
async def clear_latest():
    return await _commit(runtime.state_manager.clear_latest_card)


class SoloLegendRequest(BaseModel):
    card_id: str


@router.post("/solo/legends/{slot}")
async def assign_solo_legend(slot: int, body: SoloLegendRequest):
    card = runtime.card_db.get(body.card_id)
    if card is None or card.get("card_type") != "Legend":
        raise HTTPException(status_code=400, detail="Choose a legend card")
    return await _commit(lambda: runtime.state_manager.set_legend(
        1, slot, card["id"], name=card.get("name", ""),
        subtitle=card.get("subtitle", ""), image=card.get("image", ""),
        revealed=False,
    ))


@router.post("/solo/match/new")
async def new_solo_match():
    payload = await _commit(lambda: runtime.state_manager.reset_match(start=True))
    if runtime.vision_service.detection:
        runtime.vision_service.detection.request_play_reset()
    return payload


@router.post('/solo/play/arm')
async def arm_play_detection():
    """Explicitly accept subsequent observations of cards already on the table."""
    runtime.state_manager.observe_empty_play_region()
    if runtime.vision_service.detection:
        runtime.vision_service.detection.request_play_reset()
    payload = runtime.snapshot_payload()
    await runtime.ws_manager.broadcast(payload)
    return payload


@router.post('/solo/card/undo')
async def undo_card_play():
    return await _commit(runtime.state_manager.undo_card_play)
