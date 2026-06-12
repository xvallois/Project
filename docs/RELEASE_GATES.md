# Release gates

`scripts/release.sh vN-name` refuses to tag unless ALL automated gates
pass AND the manual review is confirmed.

## PASS (automated, in order)
1. `scripts/test.sh` — server pytest + frontend tsc/vitest/build + contract verification
2. `scripts/verify_prompts.py` — prompt interface compatibility
3. `scripts/run_eval.py` — evaluation set + gate regressions, 100% required
4. Soak — `tests/soak.md` procedure; baselines: feed <50ms, 0 provenance rejects, restart-survival
5. Performance — frontend bundle ≤150KB gz (recorded in metrics)

## MANUAL (signed checklist → artifacts/release-reviews/<tag>.md)
- **Investigation quality review**: run 3 real investigations; would a
  junior strategist's note of this quality be acceptable? note verdicts.
- **Provenance spot check**: pick 5 random numbers across feed + brief
  UI; trace each ref to its source by hand.
- **Opportunity usefulness review**: for the day's top 10 cards — how
  many were worth a trader's attention? record the ratio; below 5/10
  blocks release pending detector tuning.

The signed file (template below) is committed WITH the release.
