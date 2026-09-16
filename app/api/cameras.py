"""Vision endpoints: capture control, calibration, JPEG snapshots, MJPEG streams."""
import asyncio
import logging
import time
from datetime import datetime
from typing import Literal, Optional

import cv2
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app import runtime
from app.config import CAPTURES_DIR
from app.game.models import GameEvent
from app.game.state_manager import StateError
from app.vision.frame_processor import VIEWS
from app.vision.recognizer import Match
from app.vision.scan import scan_player

log = logging.getLogger("app.api.vision")

router = APIRouter(prefix="/vision")


class SourceModel(BaseModel):
    type: Literal["camera", "video", "stream"] = "camera"
    index: int = 0
    path: str = ""
    capture_mode: Literal["auto", "mjpeg1080", "mjpeg720", "native"] = "auto"
    exposure_mode: Literal["keep", "auto", "motion"] = "keep"


class StartRequest(BaseModel):
    source: Optional[SourceModel] = None
    # Run the table scan (face-up legends + card in play) once frames flow.
    scan_on_start: bool = True


class CalibrationRequest(BaseModel):
    cameras: Optional[dict] = None
    regions: Optional[dict] = None


class SaveFrameRequest(BaseModel):
    view: str = "raw"


class SaveCropRequest(BaseModel):
    player: int = 1


def _check_view(view: str) -> None:
    if view not in VIEWS:
        raise HTTPException(status_code=404, detail=f"Unknown view: {view}. Valid: {', '.join(VIEWS)}")


@router.get("/status")
def status():
    return {**runtime.vision_service.status(), "broadcast_feeds": board_feeds.status()}


@router.post("/start")
async def start(body: StartRequest | None = None):
    source = body.source.model_dump() if body and body.source else None
    try:
        status = runtime.vision_service.start(source)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if body is None or body.scan_on_start:
        asyncio.get_running_loop().create_task(_delayed_scan())
    return status


async def _delayed_scan():
    """Give capture a moment to warm up, then scan the table once."""
    await asyncio.sleep(2.5)
    if not runtime.vision_service.running:
        return
    try:
        result = await _apply_scan()
        log.info("SCAN_ON_START actions=%s", result["actions"])
    except Exception as exc:
        log.error("SCAN_ON_START_FAILED error=%s", exc)


def _confident(match: Optional[Match]) -> bool:
    if match is None:
        return False
    min_conf = float(runtime.vision_service.recognition_config()["min_confidence"])
    return match.confidence >= min_conf


def apply_latest_card_match(player: int, match: Match) -> Optional[GameEvent]:
    """Vision identified the card in play: make it the player's latest card.

    No-op when that card is already the latest (repeat detections of the same
    card must not spam events). Thread-safe: called from the detection thread
    for live recognition and from the scan for the one-shot pass.
    """
    state = runtime.state_manager.get_state()
    current = state.latest_cards[str(player)]
    if current is not None and current.card_id == match.card_id:
        return runtime.state_manager.update_latest_artwork(player, match.card_id, match.matched_image)
    card = runtime.card_db.get(match.card_id) or {}
    return runtime.state_manager.set_latest_card(
        player=player,
        card_id=match.card_id,
        name=card.get("name", match.name),
        subtitle=card.get("subtitle", match.subtitle),
        image=card.get("image", match.image),
        source="vision",
        confidence=match.confidence,
        matched_image=match.matched_image,
    )


def apply_legend_match(player: int, slot: int, match: Match) -> list[str]:
    previous = runtime.state_manager.get_state().legends[str(player)][slot]
    card = runtime.card_db.get(match.card_id) or {}
    event = runtime.state_manager.observe_legend(
        player, slot, match.card_id, name=card.get("name", match.name),
        subtitle=card.get("subtitle", match.subtitle), image=card.get("image", match.image),
        upside_down=match.rotated, matched_image=match.matched_image,
    )
    if not event:
        return []
    actions = []
    if previous.card_id != match.card_id:
        actions.append(f"P{player} legend {slot + 1} identified: {match.name} ({match.confidence:.0%})")
    if not previous.revealed or previous.card_id != match.card_id:
        actions.append(f"P{player} legend {slot + 1} revealed ({match.name})")
    return actions or [event.description]


def apply_legend_finding(player: int, slot: int, face_up: bool, match: Optional[Match]) -> list[str]:
    """Map one settled legend-slot observation onto game state.

    Face-up + confident match: assign (if different) and reveal. Unrecognized
    observations leave assigned cards and flip state unchanged. Face-down:
    hide only when `legend_auto_hide` is enabled (off by default — a hand over
    the slot must never un-reveal a legend on stream).
    """
    actions: list[str] = []
    legend = runtime.state_manager.get_state().legends[str(player)][slot]
    if face_up:
        if _confident(match):
            actions.extend(apply_legend_match(player, slot, match))
    elif legend.revealed and runtime.vision_service.recognition_config().get("legend_auto_hide"):
        try:
            runtime.state_manager.reveal_legend(player, slot, False)
            actions.append(f"P{player} legend {slot + 1} hidden (face-down on table)")
        except StateError:
            pass
    return actions


async def _apply_scan() -> dict:
    """Run the table scan and map findings onto game state (all undoable)."""
    service = runtime.vision_service
    actions: list[str] = []
    findings: dict = {}
    for player in (1,):
        result = scan_player(service, player)
        findings[str(player)] = {
            "legends": result.get("legends"),
            "card_bbox": result.get("card_bbox"),
            "error": result.get("error"),
        }
        if not result.get("ok"):
            continue

        # Every legend slot is identified independent of brightness/back color.
        # Only confident identities change assigned cards or flip state.
        legend_crops = result.get("legend_crops") or []
        legend_matches: list[Optional[dict]] = []
        identities = {}
        for i, finding in enumerate(result.get("legends", [])):
            if i >= 3:
                legend_matches.append(None)
                continue
            crops = legend_crops[i] if i < len(legend_crops) else []
            match = service.recognize_crops(crops, card_type="Legend")
            legend_matches.append(match.as_dict() if match else None)
            if match and (match.card_id not in identities or match.confidence > identities[match.card_id][1].confidence):
                identities[match.card_id] = (i, match)
        # A single frame cannot contain the same physical legend in two slots.
        for i, match in identities.values():
            actions.extend(apply_legend_finding(player, i, True, match))
        findings[str(player)]["legend_matches"] = legend_matches

        # A table scan observes the existing board; it is not a new play.
        # Latest-card changes come from fresh live detections or manual selection.

    payload = runtime.snapshot_payload()
    await runtime.ws_manager.broadcast(payload)
    return {"actions": actions, "findings": findings}


@router.post("/scan")
async def scan():
    if not runtime.vision_service.running:
        raise HTTPException(status_code=400, detail="Vision is not running")
    return await _apply_scan()


@router.post("/stop")
def stop():
    return runtime.vision_service.stop()


@router.post("/pause")
def pause():
    return runtime.vision_service.pause()


@router.post("/resume")
def resume():
    return runtime.vision_service.resume()


@router.get("/frame/{view}.jpg")
def frame(view: str, rois: bool = False):
    _check_view(view)
    return Response(content=runtime.vision_service.jpeg(view, rois=rois), media_type="image/jpeg")


@router.get("/stream/{view}")
def stream(view: str, rois: bool = False, fps: float = Query(default=8, gt=0, le=30)):
    _check_view(view)
    boundary = "cpbframe"

    def generate():
        interval = 1.0 / float(fps)
        # Runs in the threadpool (sync generator); ends when the client leaves.
        while True:
            data = runtime.vision_service.jpeg(view, rois=rois)
            yield (
                f"--{boundary}\r\nContent-Type: image/jpeg\r\n"
                f"Content-Length: {len(data)}\r\n\r\n"
            ).encode() + data + b"\r\n"
            time.sleep(interval)

    return StreamingResponse(
        generate(), media_type=f"multipart/x-mixed-replace; boundary={boundary}"
    )


@router.get("/detection")
def detection():
    result = runtime.vision_service.detection_results()
    result["awaiting_first_play"] = runtime.state_manager.get_state().awaiting_first_play
    return result


@router.post("/recognize/{player}")
async def recognize(player: int, apply: bool = True):
    """Identify the current detection crop on demand (debug page / operator).

    apply=true (default) sets the latest card when the match is confident.
    """
    if player not in (1, 2):
        raise HTTPException(status_code=404, detail="Player must be 1 or 2")
    service = runtime.vision_service
    if not service.running:
        raise HTTPException(status_code=400, detail="Vision is not running")
    if service.recognizer is None or not service.recognizer.ready:
        raise HTTPException(status_code=503, detail="Card recognizer index not ready")
    if service.detection is None or service.detection.crop(player) is None:
        raise HTTPException(status_code=400, detail=f"No card crop for player {player}")
    match = service.recognize_player(player)
    if match is None:
        raise HTTPException(status_code=400, detail=f"No card candidates for player {player}")
    applied = False
    if apply and _confident(match):
        event = apply_latest_card_match(player, match)
        applied = event is not None
        if applied:
            await runtime.ws_manager.broadcast(runtime.snapshot_payload(event))
    return {
        "match": match.as_dict() if match else None,
        "confident": _confident(match),
        "applied": applied,
    }


@router.get("/detection/crop/{player}.jpg")
def detection_crop(player: int):
    if player not in (1, 2):
        raise HTTPException(status_code=404, detail="Player must be 1 or 2")
    return Response(content=runtime.vision_service.crop_jpeg(player), media_type="image/jpeg")


@router.get("/detection/debug/{player}.jpg")
def detection_debug(player: int):
    if player not in (1, 2):
        raise HTTPException(status_code=404, detail="Player must be 1 or 2")
    return Response(content=runtime.vision_service.detection_debug_jpeg(player),
                    media_type="image/jpeg")


@router.post("/save_crop")
def save_crop(body: SaveCropRequest):
    if body.player not in (1, 2):
        raise HTTPException(status_code=400, detail="Player must be 1 or 2")
    try:
        path = runtime.vision_service.save_crop(body.player)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"saved": str(path)}


@router.get("/calibration")
def get_calibration():
    return {
        "cameras": runtime.calibration_store.cameras,
        "regions": runtime.calibration_store.regions,
    }


@router.post("/calibration")
def set_calibration(body: CalibrationRequest):
    store = runtime.calibration_store
    if body.cameras is not None:
        store.save_cameras(body.cameras)
    if body.regions is not None:
        store.save_regions(body.regions)
    return {"cameras": store.cameras, "regions": store.regions}


@router.post("/save_frame")
def save_frame(body: SaveFrameRequest):
    _check_view(body.view)
    try:
        path = runtime.vision_service.save_frame(body.view)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"saved": str(path)}


@router.get("/legend-slots/{player}/{slot}.jpg")
def legend_slot_image(player: int, slot: int):
    if player != 1 or slot not in (0, 1, 2):
        raise HTTPException(status_code=404, detail="Unknown legend slot")
    return Response(runtime.vision_service.legend_debug_jpeg(player, slot),
                    media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/legend-region/{player}.jpg")
def legend_region_image(player: int):
    if player != 1:
        raise HTTPException(status_code=404, detail="Unknown player")
    return Response(runtime.vision_service.legend_debug_jpeg(player),
                    media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/area/{area}.jpg")
def board_area_image(area: str):
    """Independent, correctly oriented native camera crops for OBS panels."""
    import numpy as np
    from app.vision.perspective import rect_to_pixels
    if area in ("raw", "p1_crop", "p1_corrected"):
        return Response(runtime.vision_service.jpeg(area), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    keys = {"play": "card_play_region", "eddies": "eddie_region", "gigs": "gig_region", "fixer": "fixer_region"}
    if area not in keys:
        raise HTTPException(status_code=404, detail="Unknown board area")
    service = runtime.vision_service
    frame = service._raw_frame()
    region = service.store.player(1)["regions"].get(keys[area])
    if frame is None or not region:
        image = service._placeholder("Camera unavailable" if region else "Calibrate " + area)
    else:
        corrected_w, corrected_h = service.store.corrected_size
        x, y, w, h = rect_to_pixels(region, corrected_w, corrected_h)
        quad = np.float32([[x,y],[x+w,y],[x+w,y+h],[x,y+h]])
        raw_quad = service.corrected_to_raw(frame.shape, 1, quad)
        native_w = max(float(np.linalg.norm(raw_quad[1]-raw_quad[0])), 1)
        native_h = native_w*h/max(w, 1)
        scale = min(1.0, 1280/native_w, 1080/max(native_h, 1))
        out_w = max(1, int(native_w*scale))
        out_h = max(1, int(native_h*scale))
        destination = np.float32([[0,0],[out_w-1,0],[out_w-1,out_h-1],[0,out_h-1]])
        image = cv2.warpPerspective(frame, cv2.getPerspectiveTransform(raw_quad, destination), (out_w,out_h))
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(status_code=500, detail="Could not encode area")
    return Response(encoded.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


BOARD_AREAS = ('play', 'eddies', 'gigs', 'fixer', 'raw', 'p1_crop', 'p1_corrected')


def _broadcast_fps():
    return max(1, min(60, getattr(runtime.vision_service.capture, 'native_fps', 30)))


from app.broadcast.feeds import SharedFeeds
board_feeds = SharedFeeds(lambda area: board_area_image(area).body, _broadcast_fps)


@router.get('/area-stream/{area}')
def board_area_stream(area: str):
    if area not in BOARD_AREAS:
        raise HTTPException(404, 'Unknown board area')

    async def frames():
        entry = board_feeds.attach(area)
        deadline = time.monotonic()
        try:
            while True:
                data = entry['data']
                if data is None:
                    await asyncio.sleep(.005)
                    deadline = time.monotonic()
                    continue
                yield (b'--boardframe\r\nContent-Type: image/jpeg\r\nContent-Length: '+
                       str(len(data)).encode()+b'\r\n\r\n'+data+b'\r\n')
                interval = 1/_broadcast_fps()
                deadline += interval
                now = time.monotonic()
                if deadline < now-interval:
                    deadline = now
                await asyncio.sleep(max(0, deadline-now))
        finally:
            board_feeds.detach(area, entry)

    return StreamingResponse(frames(), media_type='multipart/x-mixed-replace; boundary=boardframe',
                             headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


@router.get('/sources')
def sources():
    from app.vision.sources import camera_sources
    return {'devices': camera_sources(runtime.virtual_camera)}


from fastapi import WebSocket, WebSocketDisconnect


@router.websocket('/area-socket/{area}')
async def board_area_socket(websocket: WebSocket, area: str):
    if area not in BOARD_AREAS:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    entry = board_feeds.attach(area)
    due = time.monotonic()
    try:
        while True:
            # One decoded image acknowledgement per frame: no browser backlog.
            message = await asyncio.wait_for(websocket.receive_text(), 30)
            if message != 'next':
                await websocket.close(code=1008)
                break
            await asyncio.sleep(max(0, due-time.monotonic()))
            while entry['data'] is None:
                await asyncio.sleep(.01)
            await websocket.send_bytes(entry['data'])
            due = time.monotonic()+1/_broadcast_fps()
    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        await websocket.close(code=1000)
    finally:
        board_feeds.detach(area, entry)


class ArtworkReferenceRequest(BaseModel):
    card_id: str
    capture: str


def _reference_capture(name):
    from pathlib import Path
    if Path(name).name != name or not name.startswith("p1-") or not name.endswith(".png"):
        raise HTTPException(status_code=400, detail="Choose a saved card crop")
    root = (runtime.vision_service.captures_dir / "crops").resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Saved crop unavailable")
    return path


@router.get("/artwork/capture/{name}")
def artwork_capture(name: str):
    from fastapi.responses import FileResponse
    return FileResponse(_reference_capture(name), media_type="image/png")


@router.post("/artwork/learn")
def learn_artwork(body: ArtworkReferenceRequest):
    import hashlib
    card = runtime.card_db.get(body.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Unknown card")
    path = _reference_capture(body.capture)
    image = cv2.imread(str(path))
    if image is None or min(image.shape[:2]) < 60:
        raise HTTPException(status_code=400, detail="Capture a clear, complete card first")
    recognizer = runtime.recognizer
    folder = recognizer.images_dir / "recognition" / card['id']
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (hashlib.sha256(path.read_bytes()).hexdigest()[:20] + '.png')
    if not target.exists():
        if not cv2.imwrite(str(target), image):
            raise HTTPException(status_code=500, detail="Could not save artwork reference")
        recognizer.build()
    return {"learned": card['name'], "message": "Artwork reference saved. Recognition now uses it; overlay artwork stays unchanged."}
