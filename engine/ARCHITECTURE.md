# FX Volatility Trading Assistant — System Architecture (v0.1)

**Status:** Design stage — no code yet. This document is the contract for everything we build.
**Audience:** Desk quants / developers maintaining the system.
**Working name:** `volwatch`

---

## 1. Design Goals & Non-Goals

### Goals
- Continuously ingest the FX vol market (spot, forwards, vol surfaces, rates) from Bloomberg.
- Maintain a clean, versioned local history of every surface ever observed.
- Run a battery of analytics (calibration, arb checks, carry, realized vol) on every refresh.
- Generate ranked, explainable signals with full mathematical definitions.
- Use an LLM research layer to turn signals + context into desk-quality trade write-ups.
- Surface everything in a dashboard a trader actually looks at.

### Non-Goals (explicitly out of scope for v1)
- **Order execution.** This is a *research/monitoring assistant*. No auto-trading. Keeps the regulatory and operational risk profile sane.
- **Tick-level data.** We poll snapshots (1–15 min). FX vol RV trades on hours/days horizons; tick infra is cost without edge here.
- **Multi-user server deployment.** v1 is a modular monolith on one desk machine. Architecture allows promotion to services later.

---

## 2. Top-Level Architecture

```
            ┌──────────────────────────────────────────────────────┐
            │                      SCHEDULER                        │
            │        (APScheduler: snap cycle, EOD cycle)           │
            └───────┬──────────────────────────────────────┬───────┘
                    ▼                                      ▼
        ┌───────────────────┐                  ┌────────────────────┐
        │   DATA LAYER      │                  │  ANALYTICS ENGINE   │
        │  bbg adapter      │── MarketSnapshot │  surface builder    │
        │  validators       │─────────────────▶│  SABR / SSVI        │
        │  persistence      │                  │  arb checks         │
        └───────┬───────────┘                  │  fwd vol / carry    │
                │                              │  realized vol       │
                ▼                              └─────────┬──────────┘
        ┌───────────────────┐                            │ AnalyticsResult
        │  LOCAL STORE      │                            ▼
        │  Parquet + DuckDB │◀───────────────┌────────────────────┐
        │  (history)        │                │   SIGNAL ENGINE     │
        └───────────────────┘                │  signal library     │
                                             │  scoring / z-scores │
                                             └─────────┬──────────┘
                                                       │ ranked SignalSet
                                                       ▼
                                             ┌────────────────────┐
                                             │  AI RESEARCH LAYER  │
                                             │  context assembler  │
                                             │  trade write-ups    │
                                             └─────────┬──────────┘
                                                       ▼
                                             ┌────────────────────┐
                                             │     DASHBOARD       │
                                             │  Streamlit/Plotly   │
                                             └────────────────────┘
```

**Key principle: everything flows through immutable, typed domain objects** (`MarketSnapshot`, `VolSurface`, `CalibratedSurface`, `Signal`, `TradeIdea`). Modules never reach into each other's internals; they consume and emit these objects. This is what makes the system testable and maintainable.

---

## 3. Repository Layout

```
volwatch/
├── pyproject.toml
├── config/
│   ├── settings.yaml          # universe, schedules, storage paths
│   ├── bloomberg.yaml         # ticker templates, field maps, session config
│   ├── signals.yaml           # per-signal params, thresholds, lookbacks
│   └── logging.yaml
├── volwatch/
│   ├── core/                  # domain models, conventions, calendars
│   │   ├── models.py          # MarketSnapshot, VolSurface, Signal, ...
│   │   ├── conventions.py     # delta conventions, ATM defs, daycounts
│   │   └── calendars.py
│   ├── data/
│   │   ├── bloomberg.py       # blpapi adapter (the ONLY module importing blpapi)
│   │   ├── tickers.py         # ticker construction from config templates
│   │   ├── validation.py      # sanity checks before anything is stored
│   │   ├── store.py           # Parquet writer + DuckDB query layer
│   │   └── scheduler.py
│   ├── analytics/
│   │   ├── surface.py         # smile construction, strike/delta transforms
│   │   ├── interpolation.py
│   │   ├── sabr.py
│   │   ├── ssvi.py
│   │   ├── arbitrage.py
│   │   ├── forward_vol.py
│   │   ├── carry.py
│   │   └── realized.py        # CC, Parkinson, Garman-Klass, Yang-Zhang
│   ├── signals/
│   │   ├── base.py            # Signal ABC, registry, scoring framework
│   │   ├── richcheap.py
│   │   ├── relative_value.py
│   │   ├── dislocations.py
│   │   ├── events.py
│   │   ├── correlation.py
│   │   └── skew.py
│   ├── ai/
│   │   ├── context.py         # assembles market context for the LLM
│   │   ├── researcher.py      # Anthropic API client, structured outputs
│   │   └── prompts/
│   ├── dashboard/
│   │   └── app.py             # Streamlit
│   └── ops/
│       ├── logging.py
│       ├── health.py          # data staleness, calibration failures
│       └── alerts.py
└── tests/
    ├── unit/
    └── golden/                # frozen surfaces with known-good calibrations
```

---

## 4. Module Responsibilities & Contracts

### 4.1 `core` — Domain Models & FX Conventions
The hardest, least glamorous, most important module. FX vol quoting conventions are where systems silently rot.

Responsibilities:
- Immutable dataclasses: `VolQuote(pair, tenor, atm, rr25, bf25, rr10, bf10, ts)`, `VolSurface`, `RatePoint`, `MarketSnapshot` (one full sweep of the universe at time *t*).
- **Convention registry per pair**: spot-delta vs forward-delta, premium-adjusted vs unadjusted delta, ATM = delta-neutral-straddle vs ATMF. (Rule of thumb: G10 short-dated = spot delta unadjusted, DNS ATM; EM and >1Y = forward delta, often premium-adjusted. We encode this per pair in config, never hardcode.)
- Broker strangle vs smile strangle for butterflies — v1 treats quoted BF as smile BF (market convention for screen quotes), with a flag for the broker-strangle correction later.
- Tenor arithmetic, expiry/delivery date logic (NY 10am / Tokyo 3pm cuts), holiday calendars.

### 4.2 `data` — Bloomberg Adapter & Persistence

**Adapter (`bloomberg.py`)**
- Uses Desktop API (`blpapi`, localhost:8194, Terminal must be running).
- `//blp/refdata` `ReferenceDataRequest` for snapshots. We **poll**, not subscribe — see tradeoffs §6.
- Hard rule: `blpapi` is imported in exactly one file, behind a `MarketDataProvider` interface. Everything downstream sees domain objects. This lets us mock the entire feed in tests and swap providers.

**Ticker universe** (templates in `bloomberg.yaml`, e.g. for EURUSD):
| Item | Ticker pattern | Field |
|---|---|---|
| Spot | `EURUSD Curncy` | `PX_LAST` / `PX_BID/ASK` |
| Fwd points | `EUR1M Curncy` (or `EURUSD1M BGN Curncy`) | `PX_LAST` |
| ATM vol | `EURUSDV1M BGN Curncy` | `PX_LAST` |
| 25d RR | `EURUSD25R1M BGN Curncy` | `PX_LAST` |
| 25d BF | `EURUSD25B1M BGN Curncy` | `PX_LAST` |
| 10d RR/BF | `EURUSD10R1M / 10B1M BGN Curncy` | `PX_LAST` |
| OIS / depo | per-ccy curve tickers (SOFR, ESTR, ...) | `PX_LAST` |
| Realized inputs | `EURUSD Curncy` | OHLC dailies via `HistoricalDataRequest` |

Tenor grid v1: `ON, 1W, 2W, 1M, 2M, 3M, 6M, 9M, 1Y` across a configurable pair universe (start: EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD, USDCHF, EURJPY, EURGBP, USDMXN, USDBRL... trimmed in config).

We deliberately build surfaces from **ATM/RR/BF quotes ourselves** rather than pulling Bloomberg's pre-built OVDV grid: full control of conventions, and the quote vector is what brokers actually trade against. (We can snap OVDV occasionally as a cross-check.)

**Validation (`validation.py`)** — every quote passes: staleness check, positivity, RR/BF magnitude bounds, jump-vs-last-snap limits, bid≤ask. Bad quotes are flagged and *stored with the flag*, never silently dropped or repaired.

**Persistence (`store.py`)**
- **Parquet files partitioned by `date/pair/data_type`, queried through DuckDB.**
- Append-only: snapshots are immutable facts. EOD job compacts intraday files.
- Schema versioned (`schema_version` column) so we can evolve without migrations breaking history.
- Why not a real database? See §6.

### 4.3 `analytics`
- **Surface builder**: quote vector → 5-point smile per tenor (10P, 25P, ATM, 25C, 10C) in delta space → strike space via the pair's convention (solving the premium-adjusted delta fixed-point where needed).
- **SABR**: per-expiry calibration (β fixed, fit α, ρ, ν). Fast, great smile intuition (ρ ↔ skew/RR, ν ↔ convexity/BF), and its parameters are themselves signal inputs.
- **SSVI**: global-in-time parameterization on total variance; gives calendar consistency and a second opinion on SABR. Disagreement between the two is itself diagnostic.
- **Arbitrage checks**: butterfly arb (call-price convexity in strike / Durrleman condition), calendar arb (total variance monotone in T at fixed moneyness), and quote-level sanity (BF ≥ admissible floor given RR). Output: per-surface arb report. Genuine quoted arbs in liquid FX are almost always stale/bad quotes — but *near-violations* are tradeable dislocations, so the engine reports a continuous "distance to arb" metric, not just a boolean.
- **Forward vol**: σ²_fwd(T₁,T₂) = (σ₂²T₂ − σ₁²T₁)/(T₂−T₁) on the ATM term structure and at fixed moneyness; the FVA grid this implies.
- **Carry**: vol carry per tenor = implied(T) − expected realized over the holding period, plus rolldown along the term structure (what does a 3M vol "become" in a week if the curve doesn't move).
- **Realized vol**: close-close, Parkinson, Garman-Klass, Yang-Zhang estimators over multiple windows; intraday-frequency realized once we have enough stored snaps.

### 4.4 `signals`
A `Signal` ABC with: `compute(analytics_result, history) -> list[SignalInstance]`, where each instance carries `{pair, structure, direction, score, zscore, edge_estimate, failure_modes, math_ref}`. Registry pattern + `signals.yaml` config so adding a signal never touches engine code. Every signal ships with its math, intuition, edge logic, and failure modes documented in its docstring **and** rendered in the dashboard. Initial library (full math comes at build stage):

1. **Implied–realized spread / vol risk premium** (rich-cheap vs own history and vs realized, z-scored).
2. **Cross-pair RV**: vol spreads/ratios between cointegrated-ish pairs (e.g. EURUSD vs GBPUSD 3M), triangle consistency (EURUSD/USDJPY/EURJPY implied correlation vs realized correlation).
3. **Term-structure dislocations**: forward vol vs spot vol anomalies, kinks vs smooth fit residuals.
4. **Event vol**: overnight/event-date implied move vs historical realized event moves (CPI, NFP, central banks) — requires an event calendar feed.
5. **Skew mispricing**: RR z-scores vs history, RR vs realized spot-vol correlation (is the skew paying for a beta that exists?), SABR ρ rich/cheap.
6. **Convexity**: BF vs realized kurtosis / vol-of-vol; SABR ν rich/cheap.
7. **Surface-fit residuals**: individual quotes far from the smooth SSVI fit = candidate stale/dislocated quotes.

### 4.5 `ai` — Research Layer
- `context.py` assembles a structured packet: top-N signals, surface deltas vs yesterday/last week, arb report, realized-vs-implied table, upcoming events.
- `researcher.py` calls the Anthropic API with structured-output prompts to produce: trade idea (structure, strikes, tenors, sizing logic), thesis ("why does this opportunity exist — who is the flow on the other side"), risk analysis (greeks profile, scenario P&L, what kills the trade), and a confidence/caveat section.
- **Hard boundary: the LLM never invents numbers.** It receives computed analytics and reasons over them; every quantitative claim in a write-up must trace to a field in the context packet. Write-ups are stored with their full input context for audit.

### 4.6 `dashboard` — Streamlit
Tabs: **Surfaces** (3D + smile/term slices, vs T-1/T-5 diffs), **Signals** (ranked table, per-signal drill-down with the math), **Trade Ideas** (AI write-ups), **Carry & RV monitor**, **Risk/health** (data staleness, calibration RMSE, arb flags). Reads only from the store + latest results — the dashboard owns no logic.

### 4.7 `ops`
Structured JSON logging (`logging.yaml`), heartbeat/staleness monitors, calibration-failure alerts, and a daily health summary. A trading system that fails silently is worse than no system.

---

## 5. Data & Storage Architecture

- **Hot path**: latest `MarketSnapshot` + `AnalyticsResult` kept in memory and mirrored to a `latest/` directory for the dashboard.
- **History**: `data/parquet/{data_type}/date=YYYY-MM-DD/pair=EURUSD/*.parquet`. DuckDB queries straight over the partition tree — zero-admin, columnar, fast time-series scans, trivially portable/backed-up.
- **Retention**: raw snaps forever (they're tiny — a full G10 vol sweep is a few KB), plus derived daily EOD "official" surfaces.
- **Lineage**: every derived artifact stores the snapshot id it came from and the code version (`git_sha` column).

## 6. Key Tradeoffs (decisions + rationale)

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Feed mode | Polled refdata snaps (1–15 min) | `//blp/mktdata` subscriptions | Vol RV signals live on hours/days; polling is simpler, respects data limits, easier to make deterministic/testable. Revisit if we ever do event-second trading. |
| Surface source | Build from ATM/RR/BF quotes | Bloomberg OVDV grid | Convention control + the quote vector is the tradeable object. OVDV kept as cross-check. |
| Storage | Parquet + DuckDB | TimescaleDB/kdb | Single-desk local: zero ops burden, easy backup, analyst-friendly. A DB adds a server to babysit for no query we can't already do. |
| Calibration | SABR per-tenor **and** SSVI global | Pick one | They disagree in informative ways; SABR params are signals, SSVI gives no-arb structure. Cost is one extra module. |
| Dashboard | Streamlit | Dash/React | 10× faster iteration; this is an internal tool. If we outgrow it, the dashboard owns no logic so swapping is cheap. |
| Process model | Modular monolith, single scheduler | Microservices/queues | One desk machine, one team. Clean module contracts give us the seams to split later if needed. |
| Execution | None (research assistant) | Auto-quoting/trading | Keeps v1 in the "decision support" risk class. Trader stays in the loop. |
| Rates | OIS curves + imply from fwd points cross-check | Full multi-curve framework | For vol analytics, simple depo/OIS discounting is adequate at our tenors; full curve framework is a project of its own. |

## 7. Build Roadmap (iterative stages)

| Stage | Deliverable | Definition of done |
|---|---|---|
| 0 | Repo scaffold: config system (pydantic-settings + YAML), logging, domain models | Models round-trip to Parquet; `pytest` green |
| 1 | Bloomberg adapter + mock provider + validation + store | Live snap of 3 pairs lands in Parquet; full pipeline runs on mock data without a Terminal |
| 2 | Surface construction + conventions + interpolation | Delta↔strike transforms match hand-calcs & golden files |
| 3 | SABR + SSVI calibration + arb engine | RMSE < tolerance on golden surfaces; arb flags fire on constructed arb cases |
| 4 | Forward vol, carry, realized vol | Numbers reconcile vs manual Bloomberg checks |
| 5 | Signal engine + first 4 signals, z-score history | Signals computed end-to-end on stored history |
| 6 | AI research layer | Write-ups generated, numerically traceable to context |
| 7 | Dashboard | Trader-usable; all tabs live |
| 8 | Hardening: backtest harness for signals, alerting, ops | Signal hit-rate reports; unattended daily run |

Each stage ships with: objective, code, explanation, unit tests, and an improvements list — per the working agreement.

## 8. Testing Philosophy
- **Unit**: conventions and transforms (delta↔strike, premium-adjusted fixed point) against hand calculations — these bugs are silent and expensive.
- **Golden files**: frozen real surfaces with known-good SABR/SSVI params and analytics; any code change that moves them must be deliberate.
- **Mock provider**: entire pipeline runs Terminal-free in CI.
- **Property tests**: arb checker must flag synthetically-arbed surfaces; calibrator must recover parameters from surfaces it generated (round-trip).

## 9. Open Questions for the Desk (need your input)
1. Pair universe: G10 only, or include EM (changes convention handling priority — premium-adjusted deltas move up the schedule)?
2. Snap frequency: 5 min vs 15 min intraday? (Affects Bloomberg data consumption.)
3. Event calendar source: Bloomberg `ECO` via API, or a maintained CSV to start?
4. Do you want positions/your book ingested eventually (so the AI layer can frame ideas relative to existing risk), or keep it book-agnostic?
