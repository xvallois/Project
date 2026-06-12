#!/usr/bin/env bash
# Tag a release from main after the full gate passes.
set -euo pipefail
TAG="${1:?usage: release.sh vN-name}"
cd "$(dirname "$0")/.."
./scripts/test.sh
git tag -a "$TAG" -m "release $TAG"
echo "tagged $TAG — push with: git push origin main --tags"
