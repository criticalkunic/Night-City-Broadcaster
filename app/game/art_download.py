"""On-demand artwork repair for the existing local catalog."""
import threading
from datetime import datetime, timezone

import cv2
import numpy as np

from scripts import import_cards, import_printings


class ArtDownload:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = dict(running=False, completed=0, total=0, downloaded=0,
                          errors=[], message='Artwork downloads are manual.', finished_at=None)

    def status(self):
        with self.lock:
            return {**self.state, 'errors': list(self.state['errors'])}

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def start(self, database, recognizer):
        with self.lock:
            if self.state['running']:
                return False
            self.state.update(running=True, completed=0, total=len(database.cards),
                              downloaded=0, errors=[], message='Checking online artwork…')
        threading.Thread(target=self.run, args=(list(database.cards), recognizer), daemon=True).start()
        return True

    def run(self, cards, recognizer, online=None):
        downloaded, errors = 0, []
        try:
            if online is None:
                online = {c['id']: c for c in import_cards.transform_items(import_cards.fetch_netdeck_items())}
            for index, card in enumerate(cards):
                self.update(message='Checking '+card['name'])
                try:
                    image_path = card.get('image', '')
                    if image_path.startswith('/cards/images/'):
                        target = import_cards.IMAGES_DIR / image_path.removeprefix('/cards/images/')
                        if not target.exists() or cv2.imread(str(target)) is None:
                            url = online.get(card['id'], {}).get('_image_url')
                            if not url:
                                raise ValueError('No downloadable image available')
                            data = import_cards._get(url)
                            if cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) is None:
                                raise ValueError('Source returned an invalid image')
                            target.parent.mkdir(parents=True, exist_ok=True)
                            temporary = target.with_suffix(target.suffix+'.download')
                            temporary.write_bytes(data)
                            temporary.replace(target)
                            downloaded += 1
                    result = import_printings.import_card_printings(card)
                    downloaded += result.get('added', 0)
                    if result.get('error'):
                        errors.append(card['name']+': '+result['error'])
                except Exception as error:
                    errors.append(card['name']+': '+str(error))
                self.update(completed=index+1, downloaded=downloaded, errors=list(errors))
        except Exception as error:
            errors.append(str(error))
        finally:
            if downloaded:
                self.update(message='Refreshing recognition artwork…')
                try:
                    recognizer.build()
                except Exception as error:
                    errors.append('Recognition refresh: '+str(error))
            self.update(running=False, downloaded=downloaded, errors=errors,
                        message='Finished with errors; retry to download remaining art.' if errors else 'Artwork is up to date for the local catalog.',
                        finished_at=datetime.now(timezone.utc).isoformat())


art_download = ArtDownload()
