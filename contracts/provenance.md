# Provenance rules — v2 (non-negotiable since Phase 1)

**Rule: no number may appear in any UI element unless traceable to a
source.** Enforced structurally in `server/provenance.py` (cards) and
`server/analyst/schema.py` (analyst prose).

## Ref schemes
| Scheme | Example | Resolved against |
|---|---|---|
| `packet.<path[idx]>` | `packet.signals[3].score` | live cycle ResearchPacket |
| `store://vol/<pair>/<tenor>/<field>` | `store://vol/EURJPY/3M/rr25` | Parquet/DuckDB series presence |
| `derived:<fn>(refs…)` | `derived:percentile(store://…)` | every input ref must resolve |
| `ledger:card(<id>)` / `ledger:funnel(<type>)` | — | SQLite decision ledger |
| `prior:<name>` | `prior:skew_richcheap` | declared placeholder; rendered as such, never a market number |

## Card gate (server/provenance.py)
Every numeric-bearing item in evidence/supporting/contradictions/
similar_history must carry a resolvable ref; ONE failure rejects the
WHOLE card before it leaves the server (telemetry `card_rejected`).

## Analyst prose gate (server/analyst/schema.py)
Statements carry `cites: [E…]` into the evidence pack. Every numeric
token in analyst text must appear in a cited item's value — quoting at
LOWER precision passes ("2.3" citing "2.31"); inventing precision fails.
Violations drop the statement; >3 drops or an empty Finding rejects the
brief. Missing any of the 7 sections rejects outright.
