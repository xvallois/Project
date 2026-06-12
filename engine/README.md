# engine/ — vendored volwatch analytics engine

The essential subset of the volwatch engine (stage 10), vendored so the
sidecar's in-process `import volwatch` (ADR-0002) works from this repo
alone. Installed by `scripts/setup.sh` via `pip install -e ./engine`;
the sidecar resolves `VW_CONFIG` to `engine/config/settings.yaml` by
default and chdirs here so `config/signals.yaml` / `config/events.csv`
resolve.

## Vendored (the sidecar's import closure)
- `volwatch/config.py` — YAML + pydantic settings
- `volwatch/core/` — domain models, FX conventions, calendars
- `volwatch/analytics/` — surface, SABR, SSVI, fit, arbitrage, carry,
  realized, forward vol, Black
- `volwatch/signals/` — engine + signal library (5 signals)
- `volwatch/ai/context.py` — evidence-packet assembly
- `config/` — settings, signals, events, bloomberg, logging
- `tests/unit/` — engine stages 0–5

## NOT vendored (not needed by the workstation)
Streamlit dashboard, CLI runners (`run_cycle/run_daemon/run_snap`),
backtest harness, ops (alerts/health/logging), bring-up tooling, and
`ai/researcher.py` (the workstation has its own Analyst in
`server/analyst/`).

## Known gap — `volwatch/data/` pending
The stage-10 archive this was vendored from was missing the
`volwatch/data/` package (store, pipeline, providers, validation,
tickers, events). Until it is dropped in here, `volwatch.signals`,
`volwatch.ai.context`, and the sidecar cannot import, and the stage-1/5
tests fail on import. Everything else is in place; add
`engine/volwatch/data/` and the app is whole.
