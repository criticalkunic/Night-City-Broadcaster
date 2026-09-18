import asyncio
import httpx
from app import runtime
from app.game.state_manager import StateManager
from app.phone import phone_app, PhoneServer, qr_image


def test_phone_controls_and_private_routes(monkeypatch):
    monkeypatch.setattr(runtime, 'state_manager', StateManager())
    async def check():
        transport = httpx.ASGITransport(app=phone_app, client=('127.0.0.1', 1234))
        async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1:9999') as client:
            assert (await client.get('/')).status_code == 200
            for path in ['/setup', '/debug', '/api/config', '/api/vision/status', '/api/cards/artwork/status', '/static/setup/setup.js', '/api/desktop-ready']:
                assert (await client.get(path)).status_code == 404
            response = await client.post('/api/solo/gigs/p1-d6', json={'value': 4})
            assert response.status_code == 200
            assert response.json()['state']['dice']['p1-d6']['last_roll'] == 4
            assert (await client.post('/api/undo', json={})).status_code == 200
            assert (await client.get('/api/cards/search?q=Adam')).status_code == 200
            assert (await client.post('/api/solo/gigs/p1-d6',json={'value':99})).status_code == 400
            assert (await client.post('/api/undo',json={},headers={'Origin':'https://unrelated.example'})).status_code == 403
            assert (await client.post('/api/undo',data={})).status_code == 403
            assert (await client.get('/',headers={'Host':'unrelated.example'})).status_code == 403
    asyncio.run(check())


def test_live_phone_server_sync_and_stop(monkeypatch):
    monkeypatch.setattr(runtime, 'state_manager', StateManager())
    async def check():
        import websockets
        server=PhoneServer()
        try:
            await server.start()
            port=server.port
            await server.start()
            assert server.port == port
            origin=f'http://127.0.0.1:{port}'
            async with websockets.connect(f'ws://127.0.0.1:{port}/ws',origin=origin) as ws:
                import json
                assert json.loads(await ws.recv())['type']=='state_snapshot'
                async with httpx.AsyncClient(base_url=origin) as client:
                    response=await client.post('/api/solo/gigs/p2-d8',json={'value':7})
                    assert response.status_code==200
                update=json.loads(await asyncio.wait_for(ws.recv(),2))
                assert update['state']['dice']['p2-d8']['last_roll']==7
        finally:
            await server.stop()
        assert not server.status()['active']
    asyncio.run(check())


def test_qr_is_local_svg():
    assert b'<svg' in qr_image('http://192.168.1.2:9000/')
