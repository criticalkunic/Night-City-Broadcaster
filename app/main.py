"""FastAPI entrypoint.

Pages:
  /operator - scorekeeper / manual control (authoritative for dice)
  /overlay  - stream settings
  /broadcast/live - OBS Browser Source (reads state only)
  /setup    - camera calibration
  /debug    - vision debug (detection + recognition)
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import runtime
from app.api import cameras as cameras_api
from app.api import broadcast as broadcast_api
from app.api import cards as cards_api
from app.api import state as state_api
from app.config import load_overlay_config, CAPTURES_DIR, CARD_IMAGES_DIR, STATIC_DIR, env_vision_source

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("app.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    import threading

    from app.api.cameras import _delayed_scan, apply_latest_card_match, apply_legend_finding

    log.info("SERVER_START cards=%s", len(runtime.card_db.cards))
    loop = asyncio.get_running_loop()

    # Recognition index (ORB features over every card image) takes a few
    # seconds; build it off the event loop so the server is up immediately.
    if artwork_setup.ready:
        threading.Thread(target=runtime.recognizer.build, name="recognizer-index", daemon=True).start()

    def on_recognized(player: int, match) -> None:
        """Detection thread -> game state -> WebSocket (on the event loop)."""
        event = apply_latest_card_match(player, match)
        if event is not None:
            asyncio.run_coroutine_threadsafe(
                runtime.ws_manager.broadcast(runtime.snapshot_payload(event)), loop)

    def on_card_removed(player: int) -> None:
        if load_overlay_config().get("activity_mode") == "showcase":
            from app.showcase import observe
            event = observe(None) if player == 1 else None
        else:
            event = runtime.state_manager.remove_detected_card(player)
        if event is not None:
            asyncio.run_coroutine_threadsafe(
                runtime.ws_manager.broadcast(runtime.snapshot_payload(event)), loop)

    def on_legend(player: int, slot: int, face_up: bool, match) -> None:
        actions = apply_legend_finding(player, slot, face_up, match)
        if actions:
            log.info("LEGEND_LIVE actions=%s", actions)
            asyncio.run_coroutine_threadsafe(
                runtime.ws_manager.broadcast(runtime.snapshot_payload()), loop)

    def on_play_region_empty():
        if load_overlay_config().get("activity_mode") == "showcase":
            return
        if runtime.state_manager.observe_empty_play_region():
            asyncio.run_coroutine_threadsafe(runtime.ws_manager.broadcast(runtime.snapshot_payload()), loop)

    runtime.vision_service.on_play_region_empty = on_play_region_empty
    runtime.vision_service.on_card_removed = on_card_removed
    runtime.vision_service.on_recognized = on_recognized
    runtime.vision_service.on_legend = on_legend
    env_source = env_vision_source()
    if env_source is not None and artwork_setup.ready:
        # VISION_SOURCE env var set: start capture immediately (dev workflow),
        # including the stream-start table scan the /start endpoint schedules.
        runtime.vision_service.start(env_source)
        asyncio.get_running_loop().create_task(_delayed_scan())
    yield
    runtime.vision_service.on_play_region_empty = None
    runtime.vision_service.on_card_removed = None
    runtime.vision_service.on_recognized = None
    runtime.vision_service.on_legend = None
    await phone_server.stop()
    runtime.virtual_camera.stop()
    cameras_api.board_feeds.stop()
    runtime.vision_service.stop()
    log.info("SERVER_STOP")


from app.first_run import ArtworkSetup, ArtworkGate
from app.game.art_download import art_download
artwork_setup = ArtworkSetup(runtime.card_db, CARD_IMAGES_DIR, runtime.recognizer, art_download)
app = FastAPI(title="Night City Broadcaster", lifespan=lifespan)
app.add_middleware(ArtworkGate, setup=artwork_setup)

@app.get('/first-run', include_in_schema=False)
def first_run_page():
    return FileResponse(STATIC_DIR / 'first-run' / 'index.html')

@app.get('/api/first-run/status')
def first_run_status():
    return artwork_setup.status()

@app.post('/api/first-run/start')
def first_run_start():
    artwork_setup.start()
    return artwork_setup.status()



@app.middleware("http")
async def no_cache_static(request, call_next):
    """Pages and static assets must never be served stale: OBS's browser and
    Chrome cache heuristically, so an overlay/operator edit would otherwise
    not show up until the cache expires. Everything is local, so no-cache
    costs nothing."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/") or path in _PAGES or path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response

from app.showcase import router as showcase_router
app.include_router(showcase_router, prefix="/api")

app.include_router(state_api.router, prefix="/api")
app.include_router(cards_api.router, prefix="/api")
app.include_router(cameras_api.router, prefix="/api")
app.include_router(broadcast_api.router, prefix="/api")

@app.get('/static/assets/card-back.webp')
def legend_card_back():
    from app.game.card_back import card_back_path
    return FileResponse(card_back_path(CARD_IMAGES_DIR), media_type='image/webp')


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
CARD_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/cards/images", StaticFiles(directory=CARD_IMAGES_DIR), name="card-images")
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/captures", StaticFiles(directory=CAPTURES_DIR), name="captures")

_PAGES = {
    "/operator": STATIC_DIR / "operator" / "index.html",
    "/overlay": STATIC_DIR / "overlay-settings" / "index.html",
    "/broadcast/live": STATIC_DIR / "shared" / "active-overlay.html",
    "/setup": STATIC_DIR / "setup" / "index.html",
    "/debug": STATIC_DIR / "debug" / "index.html",
}


@app.get("/broadcast", include_in_schema=False)
@app.get("/overlay/live", include_in_schema=False)
@app.get("/overlay/board", include_in_schema=False)
@app.get("/overlay/feed/play", include_in_schema=False)
@app.get("/overlay/feed/eddies", include_in_schema=False)
async def legacy_overlay(request: Request):
    suffix = "?" + request.url.query if request.url.query else ""
    return RedirectResponse("/broadcast/live" + suffix, status_code=307)


def _page_route(path: str):
    file_path = _PAGES[path]

    async def serve() -> FileResponse:
        return FileResponse(file_path)

    return serve


for _path in _PAGES:
    app.get(_path, include_in_schema=False)(_page_route(_path))


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(_PAGES["/operator"])


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await runtime.ws_manager.connect(websocket)
    try:
        await websocket.send_json(runtime.snapshot_payload())
        while True:
            # Clients are read-only over WS; incoming messages are ignored
            # (kept open so pings/disconnects are detected).
            await websocket.receive_text()
    except WebSocketDisconnect:
        await runtime.ws_manager.disconnect(websocket)


from app.phone import phone_server, qr_image

@app.get('/api/phone')
def phone_status():
    return phone_server.status()

@app.post('/api/phone/start')
async def phone_start():
    return await phone_server.start()

@app.post('/api/phone/stop')
async def phone_stop():
    await phone_server.stop()
    return phone_server.status()

@app.get('/api/phone/qr')
def phone_qr(url: str):
    from fastapi.responses import Response
    if url not in phone_server.status()['urls']:
        return Response(status_code=400)
    return Response(qr_image(url), media_type='image/svg+xml')
