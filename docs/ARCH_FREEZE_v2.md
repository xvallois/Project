# Architecture Freeze — v2 (post v2-analyst)

Phase 3+ may EXTEND but must not BREAK anything below. A breaking change
requires: (1) an ADR, (2) a migration path, (3) a version bump in the
artifact's header, (4) CHANGELOG entry, (5) green `scripts/test.sh`.

## Locked contracts (contracts/)
| Artifact | Version | Breaking change examples |
|---|---|---|
| `opportunity-card.schema.json` | v2 | removing/renaming required keys; new band values; provenance pattern change |
| `research-brief.schema.json` | v1 | section rename/removal; new `kind` values; untyped statements |
| `evidence-pack.schema.json` | v1 | eid format; tag vocabulary; removing the pack-as-boundary rule |
| `blotter.schema.json` | v1 | splitting the unified ledger; kind/status vocab changes |
| `ws-protocol.md` | v1 | envelope shape; seq semantics; topic removal (ADDING topics is non-breaking) |
| `provenance.md` | v2 | weakening any resolution rule; new schemes are extensions and need verifier support + tests |

## Locked prompt interface (prompts/)
`prompts/current/` (symlink → vN) is the runtime interface. The CONTRACT
is: strict-JSON output, the 7 sections, `cites:[E…]` citation protocol,
no-invented-numbers instruction. Prompt text may evolve per version;
removing any contract element is breaking. CI runs
`scripts/verify_prompts.py` (presence of contract elements + a stub
investigation through the live prompts must yield ok/degraded).

## Locked behavioral guarantees
1. **Provenance**: card gate (one unresolvable ref rejects the card) and
   analyst numeric-citation gate (precision-aware) — `server/provenance.py`,
   `server/analyst/schema.py`. Tested by `test_phase1.py::TestProvenance`,
   `test_phase2.py::TestNumericGate`.
2. **Analyst never creates**: input = evidence pack only; output never
   touches band/status; triage writes `analyst_rank/_note` alongside.
3. **Budget**: 100u/day, 20% carryover cap, 12u triage reserve, typed
   refusals; zero budget never degrades deterministic workflows.
4. **Feed lifecycle**: dedup id `type|pair|structure`; 12h dismissal
   cooldown overridden by band escalation; 2-cycle disappearance
   debounce; sticky acted/watching; dq flags never ACTIONABLE.
5. **Investigation flow** (flagship, unchanged shape):
   card → budget → build_pack → provider (loop ≤2) → gate → persist →
   WS `brief`. New surfaces may FEED this flow; none may bypass the gate.

## Versioning procedure
Schema headers carry `title: <Name> vN`. Bump N only with migration notes
in `docs/migrations/` and a dual-read window where feasible.
