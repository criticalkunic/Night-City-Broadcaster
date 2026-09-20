"""LAN-only match controls served separately from the private desktop API."""
import asyncio
from contextlib import nullcontext
import ipaddress
import io
import socket

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from app import runtime
from app.api import state, cards
from app.config import STATIC_DIR


def lan_addresses():
    import psutil
    preferred = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('192.0.2.1', 9))  # Route lookup only; sends no traffic.
            preferred = sock.getsockname()[0]
    except OSError:
        pass
    result = []
    stats = psutil.net_if_stats()
    for name, entries in psutil.net_if_addrs().items():
        if not stats.get(name) or not stats[name].isup:
            continue
        if name.lower() == 'lo' or name.lower().startswith(('loopback', 'docker', 'veth', 'virbr', 'br-', 'tun', 'tap', 'wg', 'tailscale')) or any(word in name.lower() for word in ('vmware', 'virtual', 'vpn', 'vethernet')):
            continue
        for entry in entries:
            if entry.family == socket.AF_INET:
                addr = ipaddress.ip_address(entry.address)
                if not addr.is_loopback and not addr.is_link_local and addr.is_private:
                    result.append(entry.address)
    return sorted(set(result), key=lambda addr: (addr != preferred, addr))


phone_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

@phone_app.middleware('http')
async def local_requests(request: Request, call_next):
    # Reject cross-site writes and DNS-rebinding hostnames; no authentication or pairing.
    host = request.url.hostname
    peer = ipaddress.ip_address(request.client.host) if request.client else None
    if peer is None or not peer.is_private or host not in lan_addresses() + ['127.0.0.1', 'localhost']:
        return JSONResponse({'detail': 'Use the local address shown on your PC.'}, status_code=403)
    if request.method != 'GET':
        origin = request.headers.get('origin')
        if (origin and origin != str(request.base_url).rstrip('/')) or not request.headers.get('content-type', '').startswith('application/json'):
            return JSONResponse({'detail': 'Open controls from the QR code.'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    return response

# Explicit allowlist: no camera, filesystem, config-write, or maintenance routes.
READS = {'/state'}
WRITES = {'/solo/gigs/{die_id}', '/card/latest', '/solo/card/clear',
          '/solo/card/undo', '/solo/legends/{slot}', '/legends/{player}/{slot}',
          '/undo', '/redo', '/solo/match/new'}
for route in state.router.routes:
    if route.path in READS | WRITES:
        phone_app.add_api_route('/api' + route.path, route.endpoint, methods=list(route.methods))
phone_app.add_api_route('/api/cards/search', cards.search_cards, methods=['GET'])

from app.showcase import get_showcase, present, set_display, draw, set_charts
phone_app.add_api_route('/api/showcase/charts', set_charts, methods=['POST'])
phone_app.add_api_route('/api/showcase/display', set_display, methods=['POST'])
phone_app.add_api_route('/api/showcase/draw', draw, methods=['POST'])
phone_app.add_api_route('/api/showcase', get_showcase, methods=['GET'])
phone_app.add_api_route('/api/showcase/present', present, methods=['POST'])

@phone_app.get('/')
def index():
    return FileResponse(STATIC_DIR / 'phone' / 'index.html')

ASSETS = {'showcase/display-controls.js', 'showcase/drawing.js', 'showcase/metrics.js', 'showcase/metrics.css', 'showcase/controls.js', 'showcase/controls.css', 'phone/phone.js', 'phone/phone.css', 'operator/gigs.js', 'operator/gigs.css', 'board/dice.js'}
@phone_app.get('/static/{asset:path}')
def asset(asset: str):
    if asset not in ASSETS:
        return Response(status_code=404)
    return FileResponse(STATIC_DIR / asset)

@phone_app.websocket('/ws')
async def updates(ws: WebSocket):
    host = ws.url.hostname
    origin = ws.headers.get('origin')
    peer = ipaddress.ip_address(ws.client.host) if ws.client else None
    if peer is None or not peer.is_private or host not in lan_addresses() + ['127.0.0.1', 'localhost'] or origin != 'http://' + ws.headers.get('host', ''):
        await ws.close(code=1008)
        return
    await runtime.ws_manager.connect(ws)
    try:
        await ws.send_json(runtime.snapshot_payload())
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await runtime.ws_manager.disconnect(ws)


class PhoneServer:
    def __init__(self):
        self.server = self.task = None
        self.port = None

    async def start(self):
        if self.task and not self.task.done():
            return self.status()
        import uvicorn
        class Server(uvicorn.Server):
            def capture_signals(self):
                return nullcontext()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('0.0.0.0', 0))
        sock.listen(128)
        self.port = sock.getsockname()[1]
        self.server = Server(uvicorn.Config(phone_app, log_level='warning', lifespan='off', proxy_headers=False))
        self.task = asyncio.create_task(self.server.serve(sockets=[sock]))
        for _ in range(100):
            if self.server.started:
                return self.status()
            if self.task.done():
                await self.task
                break
            await asyncio.sleep(.02)
        raise RuntimeError('Phone controls could not start.')

    def status(self):
        active = bool(self.server and self.server.started and self.task and not self.task.done())
        return {'active': active, 'urls': [f'http://{a}:{self.port}/' for a in lan_addresses()] if active else []}

    async def stop(self):
        if self.server:
            self.server.should_exit = True
            self.server.force_exit = True
        if self.task:
            await self.task
        self.server = self.task = None

phone_server = PhoneServer()


def qr_image(url):
    import qrcode
    import qrcode.image.svg
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=4)
    stream = io.BytesIO()
    image.save(stream)
    return stream.getvalue()
