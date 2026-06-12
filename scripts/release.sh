#!/usr/bin/env bash
# Release gate: automated PASS chain + manual review confirmation.
set -euo pipefail
TAG="${1:?usage: release.sh vN-name [--review artifacts/release-reviews/<tag>.md]}"
REVIEW="${3:-artifacts/release-reviews/${TAG}.md}"
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] && PATH="$PWD/.venv/bin:$PATH"
echo "== gate 1/5: tests + contracts =="; ./scripts/test.sh
echo "== gate 2/5: prompt compatibility =="; python3 scripts/verify_prompts.py
echo "== gate 3/7: evaluation set (incl. counterexamples) =="; python3 scripts/run_eval.py
echo "== gate 4/7: decision-session replay =="
for S in review/decision_session/*.json; do
  [ -e "$S" ] && python3 scripts/replay_session.py "$S"; done
echo "== gate 5/7: usefulness + anti-overfit =="
read -p "  manual usefulness (useful/10 from review, e.g. 0.7): " MU
python3 scripts/usefulness.py --manual "$MU" --release "$TAG"
echo "== gate 6/7: soak =="; echo "  run tests/soak.md and record below"
read -p "  soak baselines met (feed<50ms, 0 rejects, restart ok)? [y/N] " S
[ "$S" = "y" ] || { echo "soak gate failed"; exit 1; }
echo "== gate 7/7: performance =="
GZ=$(cd frontend && npm run build 2>/dev/null | grep -o '[0-9.]* kB' | tail -1 | cut -d' ' -f1)
echo "  bundle ${GZ}kB gz (budget 150)"; python3 -c "exit(0 if float('${GZ:-999}')<=150 else 1)"
echo "== manual gates =="
[ -f "$REVIEW" ] || { echo "missing signed review: $REVIEW (copy TEMPLATE.md)"; exit 1; }
grep -q "Sign-off" "$REVIEW" && grep -qv "<name>" "$REVIEW" || { echo "review not signed"; exit 1; }
git add "$REVIEW"; git commit -m "docs(release): signed review for $TAG" || true
git tag -a "$TAG" -m "release $TAG (gates: tests+contracts+prompts+eval+soak+perf+manual)"
echo "tagged $TAG — push with: git push origin main --tags"
