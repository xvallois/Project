# volwatch workstation

A real-time **decision intelligence system** for OTC FX volatility
trading: deterministic opportunity engine + structured AI research layer.
Not a dashboard, not a chatbot — a structured decision environment:

    Opportunity Feed → Investigate → Research Brief → Blotter → Outcome

## Repository layout
| Path | What |
|---|---|
| `frontend/` | React 18 + TS shell: Dockview docking, command grammar, feed, Analyst panel |
| `engine/` | Vendored volwatch analytics engine (essential subset; see `engine/README.md`) |
| `server/` | FastAPI sidecar importing the volwatch engine in-process; detectors, provenance gate, SQLite ledger, Analyst orchestrator |
| `contracts/` | First-class interface contracts (schemas + protocol + provenance rules) |
| `prompts/` | Versioned Analyst prompts (loaded at runtime) |
| `docs/` | Architecture, ADRs, deployment, environment |
| `assets/` | Design contracts (v1.0/v1.1) and HTML mockups |
| `scripts/` | setup / dev / build / test / release |
| `data/` | Runtime state (gitignored): parquet history + SQLite ledger |

## Quick start
```bash
./scripts/setup.sh      # engine is vendored at ./engine (VW_ENGINE_PATH overrides)
./scripts/dev.sh        # sidecar :8787 (mock provider) + vite :5173
```
On the desk: `VW_PROVIDER=bbg` (Bloomberg DAPI) or `bql` (BQuant), and
`ANTHROPIC_API_KEY=… VW_ANALYST=claude` for the live Analyst.

## Environment variables
| Var | Default | Meaning |
|---|---|---|
| `VW_CONFIG` | engine settings.yaml | engine config path (CWD set to its repo root) |
| `VW_DATA` | `./data` | parquet + SQLite location |
| `VW_PROVIDER` | `mock` | `mock` \| `bbg` \| `bql` |
| `VW_SNAP_S` | `20` | seconds between snaps (desk: 300–1800) |
| `VW_CYCLE_EVERY` | `3` | full analytic cycle every N snaps |
| `VW_SEED_DAYS` | `120` | mock-history seed on first boot (mock only) |
| `VW_ANALYST` | `auto` | `auto` \| `claude` \| `stub` \| `disabled` |
| `ANTHROPIC_API_KEY` | — | enables the live Analyst |
| `VW_CORS_ORIGINS` | localhost:5173 dev origins | comma-separated origins allowed to call the sidecar (set on the desk; never `*`) |
| `VW_MODEL_TRIAGE/INVESTIGATE/DEEP` | haiku/sonnet/opus | per-tier model override |

## Invariants (enforced, see contracts/)
1. **Provenance**: no number reaches the UI without a resolvable source ref.
2. **The Analyst never creates**: it interprets engine opportunities; its
   prose passes a numeric citation gate; bands are the engine's alone.
3. **Hard budget**: 100u/day, 20% carryover cap, 12u triage reserve; the
   deterministic path runs at zero budget.
4. **One blotter**: a single decision ledger, `linked_opportunity_id`
   closing the chain — the dataset the Analyst learns from.

## Tests
`./scripts/test.sh` — server pytest (34), frontend vitest (25) + tsc +
build, then contract verification. CI mirrors this per push/PR.

## Branch model
`main` (tagged releases) ← `release/*` ← `develop` ← `feature/*`;
`experiment/*` for spikes (never merged to main directly).
Commits: `feat: / fix: / refactor: / test: / docs: / perf:`.
