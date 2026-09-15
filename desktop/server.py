"""Bundled desktop backend entrypoint."""
import os
import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    from fastapi.responses import PlainTextResponse
    from app.main import app
    import uvicorn

    @app.get('/api/desktop-ready', include_in_schema=False)
    def desktop_ready():
        return PlainTextResponse(os.environ.get('NCB_SESSION_TOKEN', ''))

    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('NCB_PORT', '8766')), log_level='info')
