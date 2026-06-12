#!/usr/bin/env bash
# One-time setup: engine + server deps + frontend deps.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== python (server) =="
pip install -e "${VW_ENGINE_PATH:?set VW_ENGINE_PATH to the volwatch engine checkout}"
pip install fastapi "uvicorn[standard]" anthropic httpx pytest jsonschema
echo "== node (frontend) =="
cd frontend && npm install
echo "setup complete. see README.md → Running."
