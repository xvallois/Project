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
