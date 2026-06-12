# artifacts/ — decisions, not screenshots

Real captured outputs, one example per behavior the system guarantees.
Refresh on each release tag (capture procedure: tests/soak.md step 3 +
`/api/investigate` + `/api/postmortem`).

| Dir | What it proves |
|---|---|
| `cards/` | analyst-shaped deterministic cards (signal + percentile families), provenance refs on every number |
| `briefs/` | a real investigation brief: 7 sections, typed statements, citations |
| `rejected/` | the gate working: fabricated numbers + missing section → status=rejected, nothing rendered |
| `invalidations/` | closed-without-action lifecycle output (the learning loop) |
| `postmortems/` | post-mortem brief drafted from a closed ledger entry |
| `release-reviews/` | signed manual gate checklists per release (see docs/RELEASE_GATES.md) |
