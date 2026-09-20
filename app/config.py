"""Central paths and configuration for the broadcast assistant."""
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("app.config")

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
STATIC_DIR = APP_DIR / "static"
CARDS_FILE = APP_DIR / "cards" / "cards.json"
CARD_IMAGES_DIR = APP_DIR / "cards" / "images"
CONFIG_DIR = BASE_DIR / "config"
OVERLAY_CONFIG_FILE = CONFIG_DIR / "overlay.json"
CAMERAS_FILE = CONFIG_DIR / "cameras.json"
REGIONS_FILE = CONFIG_DIR / "regions.json"
CAPTURES_DIR = BASE_DIR / "captures"

# Installed applications keep mutable data outside the bundled resources.
if os.environ.get("NCB_DATA_DIR"):
    import shutil
    data_dir = Path(os.environ["NCB_DATA_DIR"])
    for source, destination in [(CONFIG_DIR, data_dir / "config"), (APP_DIR / "cards", data_dir / "cards")]:
        destination.mkdir(parents=True, exist_ok=True)
        for item in source.rglob("*"):
            target = destination / item.relative_to(source)
            if item.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
    CONFIG_DIR = data_dir / "config"
    OVERLAY_CONFIG_FILE = CONFIG_DIR / "overlay.json"
    CAMERAS_FILE = CONFIG_DIR / "cameras.json"
    REGIONS_FILE = CONFIG_DIR / "regions.json"
    CARDS_FILE = data_dir / "cards" / "cards.json"
    CARD_IMAGES_DIR = data_dir / "cards" / "images"
    CAPTURES_DIR = data_dir / "captures"

HOST = "127.0.0.1"
PORT = 8765


def env_vision_source() -> dict | None:
    """Optional env override for the capture source.

    VISION_SOURCE=video VISION_VIDEO=tests/sample_match.avi   -> file playback
    VISION_SOURCE=camera VISION_CAMERA=/dev/video2 (or index) -> camera
    """
    mode = os.environ.get("VISION_SOURCE")
    if not mode:
        return None
    if mode == "video":
        return {"type": "video", "path": os.environ.get("VISION_VIDEO", "")}
    if mode == "camera":
        device = os.environ.get("VISION_CAMERA", "0")
        if device.isdigit():
            return {"type": "camera", "index": int(device), "path": ""}
        return {"type": "camera", "index": 0, "path": device}
    log.error("VISION_SOURCE invalid value=%r (use 'camera' or 'video')", mode)
    return None

DEFAULT_OVERLAY_CONFIG = {
    "camera_guide_seen": False,
    "activity_mode": "play",
    # Card removal is confirmed by vision before clearing the latest artwork.
    "overlay_style": "compact",
    "overlay_theme": "cyberpunk",
    "minimal_position": "bottom-right",
    "show_card_art": True,
    "broadcast_corrected": False,
    "show_matched_art": False,
    "show_dice": False,
    "show_legends": True,
    "show_roll_values": True,
    "hide_empty_captured_gigs": True,
    "overlay_scale": 100,
    "board_dice_mode": "tracked",
    "board_show_eddies": True,
    "board_show_fixer": True,
    "board_show_latest": True,
    "board_focus": "balanced",
}


def load_overlay_config() -> dict:
    if OVERLAY_CONFIG_FILE.exists():
        try:
            data = json.loads(OVERLAY_CONFIG_FILE.read_text())
            merged = {**DEFAULT_OVERLAY_CONFIG, **data}
            merged["show_roll_values"] = True
            return merged
        except (json.JSONDecodeError, OSError) as exc:
            log.error("overlay config unreadable path=%s error=%s", OVERLAY_CONFIG_FILE, exc)
    return dict(DEFAULT_OVERLAY_CONFIG)


def save_overlay_config(config: dict) -> dict:
    merged = {**load_overlay_config(), **config}
    merged["show_roll_values"] = True
    try:
        merged["overlay_scale"] = max(25, min(150, int(merged["overlay_scale"])))
    except (ValueError, TypeError, OverflowError):
        merged["overlay_scale"] = 100
    if merged.get("activity_mode") not in ("play", "showcase"):
        merged["activity_mode"] = "play"
    if merged.get("overlay_style") not in ("compact", "board"):
        merged["overlay_style"] = "compact"
    if merged.get("overlay_theme") not in ("cyberpunk", "arasaka", "edgerunners"):
        merged["overlay_theme"] = "cyberpunk"
    if merged.get("minimal_position") not in ("bottom-right", "bottom-left", "top-right", "top-left"):
        merged["minimal_position"] = "bottom-right"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    OVERLAY_CONFIG_FILE.write_text(json.dumps(merged, indent=2))
    log.info("overlay config saved path=%s", OVERLAY_CONFIG_FILE)
    return merged
