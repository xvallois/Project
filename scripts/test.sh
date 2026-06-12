#!/usr/bin/env bash
# The pre-commit gate: all suites + contract verification.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] && PATH="$PWD/.venv/bin:$PATH"
echo "== engine tests =="; (cd engine && python3 -m pytest tests -q)
echo "== server tests =="; python3 -m pytest server/tests -q
echo "== frontend tests =="; (cd frontend && npx tsc -b && npx vitest run)
echo "== contracts =="; python3 scripts/verify_contracts.py
