import asyncio
from fastapi import WebSocketDisconnect
from app.api import cameras


def test_socket_sends_only_requested_frames_and_detaches(monkeypatch):
    class Feeds:
        detached=False
        def attach(self,area):return {'data':b'jpeg'}
        def detach(self,area,entry):self.detached=True
    class Socket:
        sent=[]
        requests=0
        async def accept(self):pass
        async def receive_text(self):
            assert len(self.sent)==self.requests
            if self.requests==2:raise WebSocketDisconnect()
            self.requests+=1
            return 'next'
        async def send_bytes(self,data):self.sent.append(data)
    feeds=Feeds();socket=Socket()
    monkeypatch.setattr(cameras,'board_feeds',feeds)
    monkeypatch.setattr(cameras,'_broadcast_fps',lambda:30)
    asyncio.run(cameras.board_area_socket(socket,'raw'))
    assert socket.sent==[b'jpeg',b'jpeg']
    assert feeds.detached
