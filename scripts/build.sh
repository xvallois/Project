#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend" && npx tsc -b && npm run build
