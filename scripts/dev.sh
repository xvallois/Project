#!/usr/bin/env bash
# Dev loop: sidecar (mock provider, fast cadence) + vite, side by side.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] && PATH="$PWD/.venv/bin:$PATH"
export VW_DATA="${VW_DATA:-./data}" VW_SNAP_S="${VW_SNAP_S:-20}" VW_CYCLE_EVERY="${VW_CYCLE_EVERY:-3}"
python3 -m uvicorn server.app:app --port 8787 --reload &
SIDE=$!; trap "kill $SIDE" EXIT
cd frontend && npm run dev
