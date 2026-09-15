#!/usr/bin/env bash
# Start Night City Broadcaster.
#
# Usage:
#   ./start.sh                 # local access at 127.0.0.1:8766
#   HOST=0.0.0.0 ./start.sh    # allow access from a trusted LAN
#   PORT=9000 ./start.sh
#   VISION_SOURCE=video VISION_VIDEO=tests/sample_match.avi ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8766}"

if [ ! -x .venv/bin/python ]; then
  echo "[start] creating virtualenv..."
  python3 -m venv .venv
fi

# Install/refresh deps only when requirements.txt changed since last install.
STAMP=.venv/.requirements-stamp
if [ ! -f "$STAMP" ] || [ requirements.txt -nt "$STAMP" ]; then
  echo "[start] installing dependencies..."
  .venv/bin/pip install -q -r requirements.txt
  touch "$STAMP"
fi

echo "[start] serving on http://${HOST}:${PORT}"
echo "[start]   operator: http://localhost:${PORT}/operator"
echo "[start]   overlay:  http://localhost:${PORT}/overlay   (settings and copy link)"
echo "[start]   OBS:      http://localhost:${PORT}/broadcast/live"
echo "[start]   setup:    http://localhost:${PORT}/setup"
echo "[start]   debug:    http://localhost:${PORT}/debug"
exec .venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
