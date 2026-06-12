# Desk-live bring-up (read-only)

One page, no theory. The workstation is read-only by design: it detects,
briefs, and records — there is no execution automation anywhere.

## One-time setup (desk host)
    git clone <repo> && cd <repo>
    ./scripts/setup.sh
    pip install blpapi --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/   # bbg only

## The morning command
    VW_PROVIDER=bbg VW_ANALYST=claude ANTHROPIC_API_KEY=sk-... \
    VW_SNAP_S=300 VW_CYCLE_EVERY=6 VW_DATA=./desk-data \
    ./scripts/dev.sh
Then open http://localhost:5173. That's it — dev.sh runs the sidecar
(:8787) and the frontend (:5173) together; Ctrl-C stops both.

Variants:
- No key yet: drop `VW_ANALYST=claude ANTHROPIC_API_KEY=…` — analyst
  runs as the labeled stub, everything else identical.
- No Terminal yet: `VW_PROVIDER=mock` — same code path, synthetic data.
- BQuant: `VW_PROVIDER=bql` (only works inside BQuant).

## Environment variables (the ones that matter)
| Var | Desk value | Note |
|---|---|---|
| `VW_PROVIDER` | `bbg` (or `bql`, `mock`) | Terminal must be running for bbg |
| `VW_ANALYST` | `claude` | falls back to stub without a key |
| `ANTHROPIC_API_KEY` | your key | enables live Claude briefs |
| `VW_CONFIG` | leave default | `engine/config/settings.yaml`, vendored |
| `VW_CORS_ORIGINS` | leave default for localhost:5173 | set ONLY if the frontend is served from another origin |
| `VW_DATA` | `./desk-data` | parquet history + `workstation.db` (back this up) |
| `VW_SNAP_S` / `VW_CYCLE_EVERY` | `300` / `6` | 5-min snaps, cycle every 30 min |

## Day-one expectation (important)
With a fresh `VW_DATA` on live bbg data the feed will be QUIET — z-scored
signals refuse to fire with <20 days of history and surface percentiles
need history too (by design; mock seeds itself, live data cannot). You
will see live health, surfaces and smiles immediately; opportunities
arrive as history accumulates. To accelerate: leave the sidecar running
daily (it persists every snap into `VW_DATA`), and verify tickers per
`docs/bbg-bql-smoke.md` on day one so the accumulating history is clean.

## 60-second sanity check after boot
    curl -s localhost:8787/api/health | python3 -m json.tool | head
- `provider` says what you asked for; `analyst` says `claude` (not stub).
- per-pair `engine_health` populated; `rejected_cards` stays 0.
- ATMs vs terminal within a tick (see smoke checklist §3).
