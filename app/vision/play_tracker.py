"""Fair scheduling for every card-shaped object in the play region."""
import cv2
import numpy as np


class PlayTracker:
    def __init__(self):
        self.tracks = []
        self.serial = 0
        self.latest_id = None
        self.absent_since = None
        self.empty_frames = 0

    def update(self, detections, now):
        for track in self.tracks:
            track['current'] = None
        used = set()
        for detection in detections:
            matches = [t for t in self.tracks if t['id'] not in used and
                       np.linalg.norm(np.array(t['center'])-detection.center) < .06]
            track = min(matches, key=lambda t: np.linalg.norm(np.array(t['center'])-detection.center)) if matches else None
            if track is None:
                self.serial += 1
                track = dict(id=self.serial, center=detection.center, count=0, last=now,
                             checked=-1e9, match=None, misses=0, failures=0)
                self.tracks.append(track)
            crop = getattr(detection, 'crop', None)
            if crop is not None and crop.size:
                gray = cv2.cvtColor(cv2.resize(crop, (16,24)), cv2.COLOR_BGR2GRAY).astype(np.float32)
                fingerprint = (gray-gray.mean())/max(15,gray.std())
                old = track.get('fingerprint')
                if old is not None and np.mean(np.abs(fingerprint-old)) > .3:
                    track['checked'] = -1e9
                track['fingerprint'] = fingerprint
            track.update(current=detection, center=detection.center, last=now,
                         count=track['count']+1, misses=0)
            used.add(track['id'])
        for track in self.tracks:
            if track['current'] is None:
                track['misses'] += 1
                if track['misses'] > 2:
                    track['count'] = 0
        self.tracks = [t for t in self.tracks if now-t['last'] < 3]

    def next_check(self, now, stable_frames):
        eligible = [t for t in self.tracks if t['current'] is not None and
                    t['count'] >= stable_frames and now-t['checked'] >= (5 if t['match'] is not None else 3)]
        # Oldest check first. A bad rectangle never monopolizes recognition.
        return min(eligible, key=lambda t: (t['checked'], t['id'])) if eligible else None

    def accept(self, track, match, now):
        other_ids = {t['match'].card_id for t in self.tracks if t is not track
                     and t['current'] is not None and t['match'] is not None}
        previous_id = track.get('identity')
        is_new = (previous_id != match.card_id) and match.card_id not in other_ids
        track.update(match=match, identity=match.card_id, checked=now, failures=0)
        if is_new:
            self.latest_id = match.card_id
            self.absent_since = None
        return is_new

    def removed(self, now, delay, stable_frames):
        if self.latest_id is None and any(t['current'] is not None for t in self.tracks):
            self.absent_since = None
            self.empty_frames = 0
            return False
        visible = any(t['current'] is not None and t['match'] is not None and
                      t['match'].card_id == self.latest_id for t in self.tracks)
        if visible:
            self.absent_since = None
            self.empty_frames = 0
            return False
        self.empty_frames += 1
        if self.absent_since is None:
            self.absent_since = now
        if now-self.absent_since >= delay and self.empty_frames >= stable_frames:
            self.latest_id = None
            return True
        return False
