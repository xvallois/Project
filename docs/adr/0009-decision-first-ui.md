# ADR 0009 — Decision-first UI
**Status** locked by product owner (pre-Phase 3) · **Decision** no feature
may optimize engagement; every feature must optimize
`signal → investigation → decision`. Every chart/surface must answer, in
its PR description, the question: *"what decision becomes easier after
seeing this?"* Allowed surfaces: percentile heatmap, smile comparison,
rich/cheap decomposition, term evolution, historical overlays,
opportunity drilldown. Disallowed: decorative visualization, rotating 3D,
dashboard filler. Surfaces integrate with Investigate→Feed→Blotter; none
exist independently (no chart without a path into a card, a brief, or a
ledger entry).
**Why** at this maturity, workflow quality compounds; engagement features
corrode judgement. This principle is architectural: reviewers reject
violations regardless of polish.

## Amendment (pre-v3 release)
A visualization exists only if it changes `notice → understanding →
action`. Charts are not dashboards; charts are **evidence navigation** —
each must navigate INTO a card, a brief, or a ledger entry. Two
quantitative guards now enforce this: (1) the anti-overfit gate
(`scripts/usefulness.py`): action rate may not rise while usefulness
falls; (2) `analyst_abstain_rate` is tracked with a healthy band of
15–40% — an analyst that always has something to say has a contract that
is too permissive; abstention is discipline.
