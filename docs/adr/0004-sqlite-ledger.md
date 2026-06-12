# ADR 0004 — SQLite for decisions, Parquet for market data
**Status** accepted (Phase 1) · **Decision** stdlib sqlite3 (WAL) for
cards/events/blotter/briefs/budget; market history stays in the engine's
Parquet/DuckDB store. No Postgres.
**Why** single-desk write volume is trivial; the ledger must survive
restarts and be trivially backed up; Parquet remains the analytical truth.
