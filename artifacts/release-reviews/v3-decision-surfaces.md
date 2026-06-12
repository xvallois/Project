# Release review — v3-decision-surfaces (PRE-FILLED, awaiting trader sign-off)
Reviewer: <name> · Date: <date> · Prompt version: v1 · Provider: stub (Claude on desk)
## Automated context (agent pre-review)
- Day replay: PASS (review/decision_session/v3-day.json)
- Two behavioral bugs found & fixed BY the replay gate: persistence→band,
  numpy band saturation (see v3_day_replay/timeline.md)
- abstain_rate 0.40 (top of healthy band — watch after live-Claude tuning)
## Investigation quality (3 samples) — TRADER TO VERDICT
| Card | Verdict | Notes |
|---|---|---|
| see investigations/01-investigate-acted.json | | |
| see investigations/02-investigate-watch.json | | |
| see investigations/03-abstention.json | | abstention — is the reason sound? |
## Provenance spot check (5 numbers) — TRADER TO TRACE
| Number | Surface | Ref | Resolved by hand? |
|---|---|---|---|
## Opportunity usefulness (top 10) — TRADER TO SCORE
Useful: _/10 · Blockers: <none|list>
## Sign-off
<unsigned — release.sh will refuse to tag until signed>
