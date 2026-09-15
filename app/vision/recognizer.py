"""Milestone 4: identify a normalized card crop against the local card DB.

CPU-only, no training. Two stages per query:

  1. Shortlist, from two sources:
     - descriptor voting: every ORB descriptor of the crop is matched against
       the pooled descriptors of ALL cards (one brute-force Hamming knn), and
       each card collects one vote per query descriptor it is close to. This
       is rotation invariant and works on partial crops (detection often only
       finds the bright art panel of a dark card on a dark mat) and on sloppy
       borders — cases where a whole-card thumbnail is useless.
     - colour thumbnail similarity (0° and 180°: the opponent's cards face the
       camera upside down), which is what tells the orientation.
  2. Verify: ORB + Lowe ratio test + RANSAC homography per shortlisted card,
     at two scales (300x420 and 150x210 — camera crops are only ~100-200 px
     tall, so the coarse scale is where real matches show up). Confidence
     combines the inlier count, the margin over the runner-up card, and the
     thumbnail similarity.

The index is built once from app/cards/images at startup (or lazily on first
use) and never touches the network. Card data comes from CardDatabase only.
"""
import logging
import threading
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from app.vision.card_detector import CROP_SIZE

log = logging.getLogger("app.vision.recognizer")

THUMB_SIZE = (24, 34)   # w, h — coarse enough to survive blur and misalignment
ORB_FEATURES = 600
ORB_SCALES = ((300, 420), (150, 210))  # (w, h) levels features are computed at
VOTE_SCALE = (150, 210)                 # DB descriptors pooled for voting
VOTE_K = 6                              # neighbours per query descriptor
VOTE_MAX_DISTANCE = 64                  # Hamming; beyond this a neighbour is noise
THUMB_SHORTLIST = 6                     # thumbnail candidates merged into the shortlist
DEFAULT_RECOGNITION = {
    "shortlist": 20,           # thumbnail candidates verified with ORB
    "min_inliers": 16,         # RANSAC inliers for a confident ORB match
    "min_confidence": 0.45,    # below this the match is reported but not applied
    "ratio_test": 0.78,
    "candidates": 3,           # detection quads tried per stable episode (live)
    "try_splits": True,        # also try halves of the best quad (merged blobs)
}


@dataclass
class Match:
    card_id: str
    name: str
    subtitle: str
    image: str
    confidence: float
    inliers: int
    thumb_score: float
    rotated: bool
    card_type: str = ""
    runner_up_inliers: int = 0
    votes: int = 0
    source: str = ""           # which crop produced it (live: "quad0", "split-top", ...)

    def as_dict(self) -> dict:
        return {
            "card_id": self.card_id,
            "name": self.name,
            "subtitle": self.subtitle,
            "image": self.image,
            "confidence": round(self.confidence, 3),
            "inliers": self.inliers,
            "thumb_score": round(self.thumb_score, 3),
            "rotated": self.rotated,
            "card_type": self.card_type,
            "runner_up_inliers": self.runner_up_inliers,
            "votes": self.votes,
            "source": self.source,
        }


@dataclass
class _Entry:
    card: dict
    thumb: np.ndarray          # flattened float32, normalized
    features: dict             # scale (w, h) -> (keypoints, descriptors)
    sift: tuple = (None, None)


def _thumb_vector(image: np.ndarray) -> np.ndarray:
    """Illumination-normalized colour thumbnail as a unit vector."""
    small = cv2.resize(image, THUMB_SIZE, interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab[:, :, 0] = cv2.normalize(lab[:, :, 0], None, 0, 255, cv2.NORM_MINMAX)
    vec = lab.reshape(-1)
    vec -= vec.mean()
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def _prepare(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[1] > image.shape[0]:
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    return cv2.resize(image, CROP_SIZE, interpolation=cv2.INTER_AREA)


def legend_sleeve_like(crop):
    """Reject near-solid sleeve interiors, regardless of hue; legends only."""
    h, w = crop.shape[:2]
    inner = crop[int(h*.12):int(h*.88), int(w*.12):int(w*.88)]
    if not inner.size:
        return True
    small = cv2.resize(inner, (80, 112), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 100)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    # Hue consistency plus very little detail catches colored sleeves under shadows.
    hues = hsv[:, :, 0][hsv[:, :, 1] > 70]
    dominant_hue = np.bincount(hues // 10, minlength=18).max() / max(1, hues.size) if hues.size else 0
    return bool(gray.std() < 7 or (hues.size > .8 * gray.size and dominant_hue > .92 and (edges > 0).mean() < .025))


class CardRecognizer:
    def __init__(self, card_db, images_dir, config: Optional[dict] = None):
        self.card_db = card_db
        self.images_dir = images_dir
        self.config = {**DEFAULT_RECOGNITION, **(config or {})}
        self._orb = cv2.ORB_create(nfeatures=ORB_FEATURES, scaleFactor=1.2, nlevels=8)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self._sift = cv2.SIFT_create(nfeatures=500, contrastThreshold=.02)
        self._sift_matcher = cv2.BFMatcher(cv2.NORM_L2)
        self._entries: list[_Entry] = []
        self._thumbs: Optional[np.ndarray] = None   # (N, D)
        self._vote_desc: Optional[np.ndarray] = None  # pooled DB descriptors (M, 32)
        self._vote_owner: Optional[np.ndarray] = None  # (M,) entry index per descriptor
        self._lock = threading.Lock()
        self._scene_index = None
        self._scene_owners = None
        self._built = False

    # --------------------------------------------------------------- index

    @property
    def ready(self) -> bool:
        return self._built and bool(self._entries)

    def build(self) -> int:
        """(Re)build the index from the card DB. Returns cards indexed."""
        with self._lock:
            entries: list[_Entry] = []
            for card in self.card_db.cards:
                image_path = card.get("image", "")
                if not image_path.startswith("/cards/images/"):
                    continue
                local = self.images_dir / image_path.removeprefix("/cards/images/")
                # Confirmed alternate art and camera references share the canonical
                # identity; the overlay still uses the clean database artwork.
                references = sorted((self.images_dir / "recognition" / card["id"]).glob("*.png"))
                for reference in [local, *references]:
                    image = cv2.imread(str(reference), cv2.IMREAD_COLOR)
                    if image is None:
                        log.warning("RECOGNIZER_IMAGE_UNREADABLE card=%s path=%s", card.get("id"), reference)
                        continue
                    prepared = _prepare(image)
                    entries.append(_Entry(card=card, thumb=_thumb_vector(prepared),
                                          features=self._features(prepared), sift=self._sift_features(prepared)))
            self._entries = entries
            self._thumbs = np.stack([e.thumb for e in entries]) if entries else None
            pooled = [(i, e.features[VOTE_SCALE][1]) for i, e in enumerate(entries)
                      if e.features[VOTE_SCALE][1] is not None]
            if pooled:
                self._vote_desc = np.vstack([d for _, d in pooled])
                self._vote_owner = np.concatenate([np.full(len(d), i, dtype=np.int32) for i, d in pooled])
            else:
                self._vote_desc = self._vote_owner = None
            sift_pool = [(i, e.sift[1]) for i, e in enumerate(entries) if e.sift[1] is not None]
            if sift_pool:
                self._scene_index = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=48))
                self._scene_index.add([np.vstack([d for _, d in sift_pool]).astype(np.float32)])
                self._scene_index.train()
                self._scene_owners = np.concatenate([np.full(len(d), i, np.int32) for i, d in sift_pool])
            self._built = True
            log.info("RECOGNIZER_INDEX_BUILT cards=%s", len(entries))
            return len(entries)

    def _ensure_built(self) -> None:
        if not self._built:
            self.build()

    def _features(self, prepared: np.ndarray) -> dict:
        """ORB keypoints + descriptors of a CROP_SIZE image at every scale."""
        out = {}
        for size in ORB_SCALES:
            image = prepared if size == CROP_SIZE else cv2.resize(prepared, size, interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
            out[size] = self._orb.detectAndCompute(gray, None)
        return out

    def locate(self, scene):
        """Find card artwork geometrically when glare hides its outer border.

        Database features vote for cards, then a homography must explain a
        distributed group of matches. Returns scene-coordinate quadrilaterals.
        """
        with self._lock:
            scene_index, owners, entries = self._scene_index, self._scene_owners, self._entries
        if not entries or scene_index is None:
            return []
        gray = cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY)
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        kp, desc = cv2.SIFT_create(nfeatures=1800, contrastThreshold=.015).detectAndCompute(gray, None)
        if desc is None:
            return []
        pairs = scene_index.knnMatch(desc, k=8)
        votes = np.zeros(len(entries), np.int32)
        for pair in pairs:
            if not pair:
                continue
            best = pair[0]
            owner = owners[best.trainIdx]
            identity = entries[owner].card['id']
            rival = next((m for m in pair[1:] if entries[owners[m.trainIdx]].card['id'] != identity), None)
            # Same-card printings share features; they must not defeat the ratio
            # test by competing against one another as if they were different cards.
            if (rival is not None and best.distance < .75*rival.distance) or (rival is None and best.distance < 120):
                votes[owner] += 1
        found = []
        height, width = scene.shape[:2]
        for index in np.argsort(-votes)[:10]:
            if votes[index] < 5:
                continue
            entry = entries[index]
            target_kp, target_desc = entry.sift
            matches = self._sift_matcher.knnMatch(target_desc, desc, k=2)
            good = [m[0] for m in matches if len(m)==2 and m[0].distance < .75*m[1].distance]
            if len(good) < 12:
                continue
            src = np.float32([target_kp[m.queryIdx].pt for m in good])
            dst = np.float32([kp[m.trainIdx].pt for m in good])
            matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, 3)
            if matrix is None or mask is None or mask.sum() < 10 or float(mask.mean()) < .4:
                continue
            supported = src[mask.ravel()>0]
            if np.ptp(supported[:, 0]) < 75 or np.ptp(supported[:, 1]) < 105:
                continue
            corners = np.float32([[0,0],[299,0],[299,419],[0,419]])
            quad = cv2.perspectiveTransform(corners[None], matrix)[0]
            if not np.isfinite(quad).all() or not cv2.isContourConvex(quad):
                continue
            area = cv2.contourArea(quad)
            if not .003*width*height < area < .6*width*height:
                continue
            if quad[:,0].min() < -3 or quad[:,1].min() < -3 or quad[:,0].max() > width+3 or quad[:,1].max() > height+3:
                continue
            sides = np.linalg.norm(np.roll(quad,-1,axis=0)-quad,axis=1)
            if sides.min()<15 or sides.max()/sides.min()>3:
                continue
            if any(np.linalg.norm(quad.mean(axis=0)-q.mean(axis=0)) < .3*np.sqrt(area) for q in found):
                continue
            found.append(quad)
        return found

    def _sift_features(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        return self._sift.detectAndCompute(gray, None)

    # ------------------------------------------------------------ matching

    def recognize(self, crop: np.ndarray, card_type: Optional[str] = None,
                  config: Optional[dict] = None) -> Optional[Match]:
        """Best match for a normalized crop, or None if the index is empty.

        card_type restricts candidates (e.g. "Legend" for legend slots).
        The caller decides what to do with low-confidence matches.
        """
        self._ensure_built()
        if crop is None or crop.size == 0 or self._thumbs is None:
            return None
        cfg = {**self.config, **(config or {})}
        with self._lock:
            entries, thumbs = self._entries, self._thumbs
            vote_snapshot = (len(entries), self._vote_desc, self._vote_owner)
        if card_type:
            wanted = card_type.lower()
            idx = [i for i, e in enumerate(entries) if (e.card.get("card_type") or "").lower() == wanted]
            if not idx:
                idx = list(range(len(entries)))
        else:
            idx = list(range(len(entries)))
        sub_thumbs = thumbs[idx]

        prepared = _prepare(crop)
        if card_type and card_type.lower() == "legend":
            cfg = {**cfg, "legend_geometry": True}
            if legend_sleeve_like(prepared):
                return None
        rotated180 = cv2.rotate(prepared, cv2.ROTATE_180)
        query_feats = self._features(prepared)

        # Stage 1a: descriptor voting over the whole DB (rotation invariant).
        votes = self._votes(query_feats, vote_snapshot)
        if card_type:
            mask = np.zeros(len(entries), dtype=bool)
            mask[idx] = True
            votes = np.where(mask, votes, -1)
        vote_order = [int(i) for i in np.argsort(-votes)[: int(cfg["shortlist"])] if votes[i] > 0]

        # Stage 1b: colour thumbnails, both orientations (also decides "rotated").
        sims0 = sub_thumbs @ _thumb_vector(prepared)
        sims180 = sub_thumbs @ _thumb_vector(rotated180)
        sim_best = np.maximum(sims0, sims180)
        sim_by_entry = {idx[j]: (float(sim_best[j]), bool(sims180[j] > sims0[j])) for j in range(len(idx))}
        thumb_order = [idx[int(j)] for j in np.argsort(-sim_best)[:THUMB_SHORTLIST]]

        shortlist: list[int] = []
        for entry_index in vote_order + thumb_order:
            if entry_index not in shortlist:
                shortlist.append(entry_index)
        if not shortlist:
            return None

        # Stage 2: ORB + RANSAC per shortlisted card, best over scales.
        # ORB is rotation invariant, so one query orientation is enough.
        ranked: list[tuple[int, int, float]] = []   # (inliers, votes, sim) per entry
        per_entry: dict[int, tuple[int, int, float]] = {}
        orientations = {}
        for entry_index in shortlist:
            entry = entries[entry_index]
            inliers, orientation = max(
                (self._geometry(query_feats[size], entry.features[size], {**cfg, "feature_area": size[0]*size[1]})
                 for size in ORB_SCALES), key=lambda result: result[0]
            )
            orientations[entry_index] = orientation
            per_entry[entry_index] = (inliers, int(max(votes[entry_index], 0)), sim_by_entry[entry_index][0])
        order = sorted(per_entry.items(), key=lambda kv: (kv[1][0], kv[1][1], kv[1][2]), reverse=True)
        # SIFT tolerates scale and illumination changes that defeat ORB in
        # low-resolution webcam crops. Use it only for uncertain ORB results.
        top_inliers = order[0][1][0]
        runner = next((scores[0] for index, scores in order[1:]
                       if entries[index].card['id'] != entries[order[0][0]].card['id']), 0)
        if self._confidence(top_inliers, runner, order[0][1][2], cfg) < float(cfg['min_confidence']):
            query_sift = self._sift_features(prepared)
            for entry_index in shortlist:
                count, orientation = self._geometry(query_sift, entries[entry_index].sift, cfg, self._sift_matcher)
                old = per_entry[entry_index]
                if count > old[0]:
                    orientations[entry_index] = orientation
                per_entry[entry_index] = (max(old[0], count), old[1], old[2])
            order = sorted(per_entry.items(), key=lambda kv: (kv[1][0], kv[1][1], kv[1][2]), reverse=True)
        best_index, (inliers, n_votes, sim) = order[0]
        # Another printing of this same card is evidence, not a rival identity.
        best_id = entries[best_index].card["id"]
        runner_up = next((scores[0] for index, scores in order
                          if entries[index].card["id"] != best_id), 0)
        card = entries[best_index].card
        orientation = orientations.get(best_index)
        confidence = self._confidence(inliers, runner_up, sim, cfg)
        # A legend's physical orientation needs geometry, never a palette guess.
        if cfg.get("legend_geometry") and orientation is None:
            confidence = min(confidence, .39)
        best = Match(
            card_id=card["id"], name=card.get("name", ""),
            subtitle=card.get("subtitle", ""), image=card.get("image", ""),
            confidence=confidence,
            inliers=inliers, thumb_score=sim, rotated=bool(orientation) if cfg.get("legend_geometry") else sim_by_entry[best_index][1],
            card_type=card.get("card_type", ""), runner_up_inliers=runner_up, votes=n_votes,
        )
        log.info("RECOGNIZE card=%s conf=%.2f inliers=%s/%s votes=%s thumb=%.2f rotated=%s type=%s",
                 best.card_id, best.confidence, best.inliers, runner_up, n_votes, best.thumb_score,
                 best.rotated, card_type or "any")
        return best

    def _votes(self, query_feats: dict, snapshot=None) -> np.ndarray:
        """One vote per (query descriptor, card) pair within Hamming range."""
        if snapshot is None:
            with self._lock:
                snapshot = (len(self._entries), self._vote_desc, self._vote_owner)
        count, descriptors, owners = snapshot
        votes = np.zeros(count, dtype=np.int32)
        if descriptors is None:
            return votes
        descs = [f[1] for f in query_feats.values() if f[1] is not None]
        if not descs:
            return votes
        query = np.vstack(descs)
        matches = self._matcher.knnMatch(query, descriptors, k=VOTE_K)
        for neighbours in matches:
            seen: set[int] = set()
            for m in neighbours:
                if m.distance > VOTE_MAX_DISTANCE:
                    break
                owner = int(owners[m.trainIdx])
                if owner not in seen:
                    seen.add(owner)
                    votes[owner] += 1
        return votes

    def recognize_many(self, crops: list, card_type: Optional[str] = None,
                       config: Optional[dict] = None, stop_at: Optional[float] = None) -> Optional[Match]:
        """Recognize several candidate crops (label, image) in order; return the
        most confident match, tagged with the label of the crop that produced
        it. Stops early once a crop reaches `stop_at` confidence (the first
        crop is the best detection quad; the split halves are fallbacks)."""
        best: Optional[Match] = None
        for label, crop in crops:
            if crop is None or crop.size == 0:
                continue
            match = self.recognize(crop, card_type=card_type, config=config)
            if match is None:
                continue
            match.source = label
            if best is None or (match.confidence, match.inliers) > (best.confidence, best.inliers):
                best = match
            if stop_at is not None and best.confidence >= stop_at:
                break
        return best

    def _inliers(self, query: tuple, target: tuple, cfg: dict, matcher=None) -> int:
        return self._geometry(query, target, cfg, matcher)[0]

    def _geometry(self, query: tuple, target: tuple, cfg: dict, matcher=None):
        (q_kp, q_desc), (t_kp, t_desc) = query, target
        if q_desc is None or t_desc is None or len(q_kp) < 8 or len(t_kp) < 8:
            return 0, None
        pairs = (matcher or self._matcher).knnMatch(q_desc, t_desc, k=2)
        ratio = float(cfg["ratio_test"])
        good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < ratio * p[1].distance]
        if len(good) < 8:
            return 0, None
        src = np.float32([q_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([t_kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, 6.0)
        if matrix is None or mask is None:
            return 0, None
        if cfg.get("legend_geometry"):
            kept = mask.ravel().astype(bool)
            selected = [m for m, keep in zip(good, kept) if keep]
            if len({m.trainIdx for m in selected}) < 8:
                return 0, None
            # Repeated sleeve motifs / borders must not pass on a tiny shared patch.
            for points, keypoints in ((src[kept], q_kp), (dst[kept], t_kp)):
                all_points = np.float32([k.pt for k in keypoints])
                full_area = cv2.contourArea(cv2.convexHull(all_points))
                area = cv2.contourArea(cv2.convexHull(points))
                if full_area <= 0 or area / full_area < .18 or area < .10 * cfg.get("feature_area", CROP_SIZE[0]*CROP_SIZE[1]):
                    return 0, None
        if int(mask.sum()) < 8:
            return int(mask.sum()), None
        # Map a vertical segment through the same homography used for identity.
        supported = src[mask.ravel().astype(bool)].reshape(-1, 2)
        center = supported.mean(axis=0)
        axis = np.float32([center - [0, 5], center + [0, 5]])
        mapped = cv2.perspectiveTransform(axis[None], matrix)[0]
        dx, dy = mapped[1] - mapped[0]
        orientation = bool(dy < 0) if np.isfinite(mapped).all() and abs(dy) > abs(dx) else None
        return int(mask.sum()), orientation

    @staticmethod
    def _confidence(inliers: int, runner_up: int, thumb_sim: float, cfg: dict) -> float:
        """0..1. Geometric inliers dominate; a runner-up card with more than
        60% of the best card's inliers means the crop looks like several
        cards' shared layout (frame, text panel, dice...) rather than one
        card's art, and that is never confident. Thumbnail similarity fills
        in a little for low-texture crops."""
        min_inliers = max(1, int(cfg["min_inliers"]))
        orb_part = min(1.0, inliers / (2.0 * min_inliers))       # 1.0 at 2x min_inliers
        thumb_part = max(0.0, min(1.0, (thumb_sim - 0.3) / 0.6))  # 0.3 -> 0, 0.9 -> 1
        if inliers < min_inliers:
            # Not enough geometry: cap well below the default threshold.
            return round(0.25 * orb_part + 0.15 * thumb_part, 3)
        ratio = runner_up / inliers
        if ratio > 0.6:
            return round(0.4 * orb_part, 3)                         # ambiguous, max 0.4
        margin = 1.0 - ratio / 0.6                                  # 1.0 when unopposed
        return round(0.6 * orb_part + 0.25 * margin + 0.15 * thumb_part, 3)
