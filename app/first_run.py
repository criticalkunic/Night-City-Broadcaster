"""Required artwork setup; blocks both the desktop UI and direct service access."""
import threading
import json
from scripts import import_cards
from app.game.card_back import has_card_back, ensure_card_back
from pathlib import Path
import cv2
from fastapi.responses import JSONResponse, RedirectResponse


class ArtworkSetup:
    def __init__(self, database, images, recognizer, downloader):
        self.database, self.images, self.recognizer, self.downloader = database, Path(images), recognizer, downloader
        self.pending = self.images.parent / '.artwork-setup-pending'
        self.lock = threading.Lock()
        self.running = False
        self.error = None
        self.ready = not self.pending.exists() and self.complete()
        if not self.ready:
            self.pending.parent.mkdir(parents=True, exist_ok=True)
            self.pending.touch()

    def complete(self):
        return has_card_back(self.images) and bool(self.database.cards) and all(
            card.get('image', '').startswith('/cards/images/') and
            cv2.imread(str(self.images / card['image'].removeprefix('/cards/images/'))) is not None
            for card in self.database.cards)

    def status(self):
        status = self.downloader.status()
        return {**status, 'ready': self.ready, 'running': self.running,
                'error': self.error, 'total': len(self.database.cards)}

    def start(self):
        with self.lock:
            if self.ready or self.running:
                return
            self.running = True
            self.error = None
            self.downloader.update(completed=0, downloaded=0, errors=[], message='Connecting to artwork source…')
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        try:
            self.downloader.update(message='Fetching the current card catalog…')
            cards = import_cards.transform_items(import_cards.fetch_netdeck_items())
            if not cards:
                raise RuntimeError('The website returned no cards. Retry to continue.')
            # Commit a complete catalog only after every page has been fetched.
            clean = [{k: v for k, v in card.items() if not k.startswith('_')} for card in cards]
            path = self.database.path
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.json.download')
            temporary.write_text(json.dumps(clean, ensure_ascii=False, indent=2))
            temporary.replace(path)
            self.database.reload()
            self.downloader.update(total=len(clean), message='Downloading artwork…')
            self.downloader.run(list(self.database.cards), self.recognizer, online={card['id']: card for card in cards})
            errors = self.downloader.status()['errors']
            if errors:
                raise RuntimeError('Some artwork could not be downloaded. Retry to continue.')
            self.downloader.update(message='Downloading legend card back…')
            ensure_card_back(self.images)
            if not self.complete():
                raise RuntimeError('Some required card images are missing or unreadable. Retry to continue.')
            self.recognizer.build()
            if not self.recognizer.ready:
                raise RuntimeError('Recognition could not be prepared. Retry to continue.')
            self.pending.unlink(missing_ok=True)
            self.ready = True
        except Exception as error:
            self.error = str(error)
        finally:
            self.running = False


class ArtworkGate:
    def __init__(self, app, setup):
        self.app, self.setup = app, setup

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        allowed = path in ('/first-run', '/api/first-run/status', '/api/first-run/start', '/api/desktop-ready') or path.startswith('/static/first-run/')
        if not self.setup.ready and not allowed:
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1013})
                return
            if scope['type'] == 'http':
                response = JSONResponse({'detail': 'Artwork setup required'}, status_code=503) if path.startswith('/api/') else RedirectResponse('/first-run', status_code=307)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
