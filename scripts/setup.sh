#!/usr/bin/env bash
# One-time setup: engine + server deps + frontend deps.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== python (server) =="
pip install -e "${VW_ENGINE_PATH:-./engine}" -c constraints.txt
pip install fastapi "uvicorn[standard]" anthropic httpx pytest jsonschema -c constraints.txt
echo "== node (frontend) =="
cd frontend && npm install
echo "setup complete. see README.md → Running."
