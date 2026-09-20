"""Singletons shared by API routers and the WebSocket endpoint."""
from app.config import load_overlay_config, CAMERAS_FILE, CAPTURES_DIR, CARD_IMAGES_DIR, CARDS_FILE, REGIONS_FILE
from app.game.card_db import CardDatabase
from app.game.events import ConnectionManager
from app.game.state_manager import StateManager
from app.vision.calibration import CalibrationStore
from app.vision.frame_processor import VisionService
from app.vision.recognizer import CardRecognizer

state_manager = StateManager()
ws_manager = ConnectionManager()
card_db = CardDatabase(CARDS_FILE)
calibration_store = CalibrationStore(CAMERAS_FILE, REGIONS_FILE)
recognizer = CardRecognizer(card_db, CARD_IMAGES_DIR)
vision_service = VisionService(calibration_store, CAPTURES_DIR, recognizer=recognizer)


def snapshot_payload(event=None) -> dict:
    """Full-state broadcast payload. Clients render exclusively from this."""
    state = state_manager.get_state().model_dump()
    if load_overlay_config().get("show_matched_art", False):
        cards = [*state["latest_cards"].values(), state["last_played_card"],
                 *state["card_play_history"],
                 *(card for slots in state["legends"].values() for card in slots)]
        for card in cards:
            if card and card.get("matched_image"):
                card["image"] = card["matched_image"]
    from app.showcase import snapshot
    return {
        "activity_mode": load_overlay_config().get("activity_mode", "play"),
        "showcase": snapshot(),
        "type": event.type if event is not None else "state_snapshot",
        "event": event.model_dump() if event is not None else None,
        "state": state,
        "history": state_manager.history_info(),
    }

from app.broadcast.virtual_camera import VirtualCamera
virtual_camera = VirtualCamera()

from app.vision.sources import service_source

def validate_input_source(source):
    if service_source(source, virtual_camera):
        raise ValueError("Choose an external camera or stream, not this service's output.")

vision_service.validate_source = validate_input_source
