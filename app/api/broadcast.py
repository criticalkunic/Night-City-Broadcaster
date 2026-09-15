"""Local virtual-camera lifecycle and measured output health."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Literal
from app import runtime

router = APIRouter(prefix='/broadcast')

class StartOutput(BaseModel):
    device: str
    layout: Literal['board', 'play', 'eddies'] = 'board'

@router.get('/status')
def status():
    result = runtime.virtual_camera.status()
    result['capture'] = runtime.vision_service.status()
    return result

@router.post('/start')
def start(body: StartOutput, request: Request):
    if not runtime.vision_service.running:
        raise HTTPException(409, 'Start the webcam in Camera setup first.')
    source = runtime.vision_service.capture.source
    input_device = source.get('path') or '/dev/video'+str(source.get('index',0))
    if source.get('type') != 'video' and body.device == input_device:
        raise HTTPException(400, 'The output device cannot also be the webcam input.')
    port = request.url.port or 80
    try:
        return runtime.virtual_camera.start(body.device, body.layout, f'http://127.0.0.1:{port}',
                                            runtime.vision_service.status()['native_fps'])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@router.post('/stop')
def stop():
    return runtime.virtual_camera.stop()


@router.post('/renderer-ready')
def renderer_ready(token: str):
    # No lifecycle lock: start holds it while waiting for this browser handshake.
    output = runtime.virtual_camera
    if not output.token or token != output.token:
        raise HTTPException(403, 'Unknown renderer')
    output.ready.set()
    return {'ready': True}
