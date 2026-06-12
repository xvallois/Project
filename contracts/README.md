# Contracts

The interfaces that MUST NOT drift silently. Any change here requires:
a CHANGELOG entry, a version bump in the file header, green
`scripts/verify_contracts.py`, and reviewer sign-off.

| File | Governs |
|---|---|
| `opportunity-card.schema.json` | Card shape: feed REST/WS payloads, SQLite `cards.payload` |
| `research-brief.schema.json` | Analyst output: the 7 sections, statement typing, citations |
| `evidence-pack.schema.json` | What the Analyst is allowed to see (its world boundary) |
| `ws-protocol.md` | Topic envelope, seq/resync semantics |
| `provenance.md` | Ref schemes + verifier rules (the non-negotiable) |
| `blotter.schema.json` | The unified decision ledger row |
