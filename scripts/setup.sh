#!/usr/bin/env bash
# One-time setup: project venv + engine + server deps + frontend deps.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== python (server) =="
[ -x .venv/bin/pip ] || "${VW_PYTHON:-python3}" -m venv .venv
.venv/bin/pip install -e "${VW_ENGINE_PATH:-./engine}" -c constraints.txt
.venv/bin/pip install fastapi "uvicorn[standard]" anthropic httpx pytest jsonschema -c constraints.txt
echo "== node (frontend) =="
cd frontend && npm install
echo "setup complete. see README.md → Running."
