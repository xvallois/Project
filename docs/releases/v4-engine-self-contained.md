# Release v4.0.0 — engine-self-contained

**Branch** `release/v4-engine-self-contained` · **Tag** `v4.0.0` ·
**Date** 2026-06-12 · **Base** `develop` @ `ce011c4`

The workstation becomes self-contained: the volwatch analytics engine
is vendored at `engine/` and a fresh clone brings up the full app with
`./scripts/setup.sh && ./scripts/dev.sh` — no side-by-side engine
checkout, no environment variables required.

## Architecture changes

None. ADR-0002 (sidecar imports the engine in-process) is unchanged in
substance; only the engine's *location* moved from an external
`VW_ENGINE_PATH` checkout to `engine/` in this repository. No new
features; all wiring changes are path resolution and packaging.

## Engine vendoring

Vendored from the engine's stage-10 source (verbatim, no code edits):

- `engine/volwatch/` — `config`, `core` (models, conventions,
  calendars), `analytics` (surface, SABR, SSVI, fit, arbitrage, carry,
  realized, forward vol, Black), `signals` (engine + 5 signals),
  `data` (Parquet/DuckDB store, snap pipeline, mock/bbg/bql providers,
  snapshot assembly, validation, tickers, events), `ai/context`
- `engine/config/` — settings, signals, events, bloomberg, logging
- `engine/tests/unit/` — engine stages 0–5 (118 tests)

Deliberately NOT vendored (unused by the workstation): Streamlit
dashboard, CLI runners (`run_cycle`/`run_daemon`/`run_snap`), backtest
harness, ops (alerts/health/logging), Bloomberg bring-up tooling, and
`ai/researcher.py` (superseded by `server/analyst/`).

## Dependency changes

- `engine/pyproject.toml` now declares previously undeclared hard
  imports: **scipy**, **python-dateutil**, **duckdb**; plus an explicit
  `[tool.setuptools.packages.find] include = ["volwatch*"]` so a flat
  checkout installs cleanly.
- `scripts/setup.sh`: `VW_ENGINE_PATH` defaults to `./engine`
  (override still honoured for an external engine checkout).
- CI: the server job installs `./engine`, runs the engine suite, and
  server tests are a hard gate again (the `|| true` escape hatch is
  removed). `scripts/test.sh` gates on the engine suite too.

## Migration notes

- Fresh installs: `git clone … && ./scripts/setup.sh && ./scripts/dev.sh`.
  Nothing else.
- Existing checkouts that exported `VW_ENGINE_PATH`/`VW_CONFIG`: unset
  them (or leave them — explicit env still wins). The `VW_CONFIG`
  default moved from a hardcoded dev path to
  `<repo>/engine/config/settings.yaml`, resolved relative to the code.
- Engine config edits (universe, signals, events) now live in
  `engine/config/` and are version-controlled with the app.

## Known limitations

- `bbg`/`blpapi` and `bql` providers are vendored but unexercised here
  (require desk entitlements / BQuant); mock provider exercises the
  identical pipeline/store/signal path.
- Engine tests for excluded modules (stages 6–10: researcher,
  dashboard, hardening/backtest, bring-up, performance kernels) are not
  in this repo; they remain in the engine's own history.
- `numba` speed kernels are not installed by default (`[speed]` extra);
  numpy/math fallbacks are the tested reference.
- Manual release-review gates (investigation quality, provenance spot
  check, usefulness ratio — `docs/RELEASE_GATES.md`) are pending
  sign-off; `main` is intentionally untouched until that review lands
  in `artifacts/release-reviews/`.

## Validation results (fresh clone of this branch, clean venv)

| Gate | Result |
|---|---|
| Fresh clone validation | PASS — cloned from remote into clean dir |
| `setup.sh` clean environment | PASS — engine editable install, all deps from pyproject, npm 103 pkgs |
| `dev.sh` bring-up | PASS — vite up in <1s; sidecar seeded 120d mock history, first cycle complete |
| Engine tests | PASS — 118/118 |
| Server tests | PASS — 42/42 |
| Frontend tests | PASS — tsc clean, vitest 25/25 |
| Contract verification | PASS — 3/3 schemas |
| Prompt verification | PASS — contract elements present, live-prompt investigation ok |
| Evaluation suite | PASS — 7/7 incl. counterexamples + fabricated-numbers regression |
| Replay validation | PASS — v3-day session: 61 cards, 3 investigations re-run, same decisions hold |
| Performance budget | PASS — bundle 106.04 kB gz (budget 150) |

Live probes during bring-up: provider=mock, analyst=stub, 9/9 pairs
calibrated (SSVI no-arb true), feed populated (31 cards, provenance
refs on all), `/api/investigate` round-trip returned a stub-labeled
brief through the gate (0 statements dropped), brief persisted to the
ledger. Zero provenance rejects, zero errors in logs, no absolute-path
references outside the clone.
