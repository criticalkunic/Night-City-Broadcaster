"""Generate a synthetic two-player table video for camera-free development.

    python scripts/make_test_video.py            # writes tests/sample_match.avi
    python scripts/make_test_video.py out.avi 10 # custom path + seconds

Left half: Player 1 table (green felt) with a white "card" sliding into the
card-play area. Right half: Player 2 table (blue felt) with a static card.
Run the server against it with:

    VISION_SOURCE=video VISION_VIDEO=tests/sample_match.avi ./start.sh
"""
import sys
from pathlib import Path

import cv2
import numpy as np

WIDTH, HEIGHT, FPS = 1280, 720, 30


def make(path: Path, seconds: int = 8) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (WIDTH, HEIGHT)
    )
    if not writer.isOpened():
        raise RuntimeError("Could not open VideoWriter (MJPG .avi)")
    total = seconds * FPS
    half = WIDTH // 2
    for i in range(total):
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        frame[:, :half] = (40, 70, 35)    # P1: green felt (BGR)
        frame[:, half:] = (70, 45, 30)    # P2: blue felt
        cv2.line(frame, (half, 0), (half, HEIGHT), (10, 10, 10), 4)

        # P1: card slides in, pauses, slides out (tests M3 detection later).
        t = (i % (FPS * 4)) / (FPS * 4)
        slide = min(1.0, t * 2) if t < 0.75 else max(0.0, (1 - t) * 4)
        cx = int(half * 0.35 + slide * half * 0.15)
        cy = int(HEIGHT * 0.4)
        cv2.rectangle(frame, (cx, cy), (cx + 90, cy + 126), (235, 235, 235), -1)
        cv2.rectangle(frame, (cx + 8, cy + 8), (cx + 82, cy + 60), (60, 160, 220), -1)
        cv2.putText(frame, "P1", (cx + 25, cy + 105), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (30, 30, 30), 2, cv2.LINE_AA)

        # P2: static card.
        px, py = half + int(half * 0.4), int(HEIGHT * 0.35)
        cv2.rectangle(frame, (px, py), (px + 90, py + 126), (225, 225, 225), -1)
        cv2.putText(frame, "P2", (px + 25, py + 105), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (30, 30, 30), 2, cv2.LINE_AA)

        # Dice-ish blobs in each fixer area.
        for j, color in enumerate([(60, 210, 195), (94, 77, 255)]):
            base = j * half
            for k in range(3):
                cv2.circle(frame, (base + 80 + k * 45, HEIGHT - 80), 16, color, -1)

        cv2.putText(frame, f"frame {i}", (12, 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (200, 200, 200), 1, cv2.LINE_AA)
        writer.write(frame)
    writer.release()
    print(f"wrote {path} ({total} frames, {WIDTH}x{HEIGHT} @ {FPS}fps)")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "tests" / "sample_match.avi"
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    out.parent.mkdir(parents=True, exist_ok=True)
    make(out, seconds)
