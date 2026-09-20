"""Choose vision ROIs without mutating the saved match layout."""
from app.config import load_overlay_config

def detection_regions(store, player):
    if load_overlay_config().get('activity_mode') != 'showcase':
        return store.player(player)['regions']
    from app.showcase import load
    if player != 1 or not load().detect_latest:
        return {}
    return {'card_play_region': store.cameras.get('showcase_board_region',
        {'x':0.0,'y':0.0,'width':1.0,'height':1.0})}
