from types import SimpleNamespace

import asyncio
from pathlib import Path
from starlette.requests import Request

from app.main import app, _PAGES
from app.vision.sources import service_source


def test_broadcast_route_and_legacy_links():
    routes = {route.path: route for route in app.routes if hasattr(route, 'path')}
    response = asyncio.run(routes['/broadcast/live'].endpoint())
    assert 'active-overlay.js' in Path(response.path).read_text()
    for path in ('/broadcast', '/overlay/live', '/overlay/board', '/overlay/feed/play', '/overlay/feed/eddies'):
        request = Request({'type': 'http', 'path': path, 'query_string': b'renderer=test',
                           'headers': [], 'scheme': 'http', 'server': ('localhost', 8766)})
        response = asyncio.run(routes[path].endpoint(request))
        assert response.status_code == 307
        assert response.headers['location'] == '/broadcast/live?renderer=test'
    assert 'Stream settings' in _PAGES['/overlay'].read_text()
    assert '/broadcast/live' in _PAGES['/operator'].read_text()


def test_broadcast_output_cannot_be_its_own_camera():
    output = SimpleNamespace(owned_devices=[], device=None)
    for path in ('/broadcast', '/broadcast/live', '/overlay/live'):
        assert service_source({'path': 'http://127.0.0.1:8766'+path}, output)
    assert not service_source({'path': 'https://example.com/video'}, output)
