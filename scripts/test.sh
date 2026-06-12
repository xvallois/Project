#!/usr/bin/env bash
# The pre-commit gate: all suites + contract verification.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== server tests =="; python3 -m pytest server/tests -q
echo "== frontend tests =="; (cd frontend && npx tsc -b && npx vitest run)
echo "== contracts =="; python3 scripts/verify_contracts.py
