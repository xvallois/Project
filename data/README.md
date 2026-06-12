# data/

Runtime state only — **gitignored by design**.

| Path | Contents |
|---|---|
| `data/parquet-root/` | engine vol/spot/forward history (Parquet, DuckDB-queried) |
| `data/latest/` | latest-snapshot JSON mirror |
| `data/workstation.db` | SQLite: cards, events (telemetry), blotter, briefs, budget |

The SQLite file is the institutional memory (decision ledger + analyst
briefs). Back it up on the desk; it is the dataset the Analyst learns from.
