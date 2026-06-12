# Changelog

## Unreleased — feature/decision-surfaces
- Server decision-surface endpoints over real store history, all
  provenance-carrying: /api/heat, /api/smile (with T-5 overlay),
  /api/term (today/T-1/T-5 vintages), /api/driver (card drilldown).
- Live panels replace mock VHEAT/SMIL when the engine is connected;
  new TERM panel; ENGINE chips on every surface.
- Surfaces route INTO the flow: heat cells with live opportunities get
  the amber ring and click-select the card in OPPS + fan out the smile;
  expanded cards render the DRIVER series with the detection marker.
- Governance (on develop): ARCH_FREEZE_v2, ADR-0009 decision-first UI,
  versioned prompts (v1 + current) with compatibility gate, evaluation
  harness (3/3) with real frozen packs + gate regressions, artifacts/
  with captured decisions, 5-gate release script + signed manual review.

## v2-analyst — 2026-06-11
- Analyst layer: evidence-pack assembly (card + co-signals + engine health
  + decision ledger), capped analysis loop, 7-section ResearchBrief.
- Numeric citation gate: uncited numbers drop statements; missing sections
  or gutted Finding rejects briefs; precision-aware quoting.
- Server-side hard budget (SQLite): 1/3/10u tiers, 20% carryover cap,
  12u triage reserve; typed refusals; zero-budget leaves engine untouched.
- Institutional memory: ledger episodes + funnel stats feed both analyst
  packs and deterministic similar-history (ledger: provenance scheme).
- Trust separation in UI: ANALYST vs ENGINE chips, citation hovers,
  provider badge (claude/stub), degraded/rejected states.
- Prompts externalized to prompts/ as versioned contracts.
- Tests: 34 server + 25 frontend.

## v1-deterministic-feed — 2026-06-11
- FastAPI sidecar importing the engine in-process; snap/cycle loop.
- Server detectors over real analytics; analyst-shaped cards.
- Structural provenance verifier (packet/store/derived/prior refs);
  poisoned cards rejected before serving.
- SQLite: cards lifecycle (cooldown, escalation override, disappearance
  debounce), telemetry funnel, unified blotter.
- WS topic protocol (snapshot/delta/seq + client resync).
- Feed hygiene: drift clustering, entry/hold hysteresis, midrank
  percentile (tie bug fix). Soak: 11.8ms feed reads, 0 provenance rejects.

## v0-shell — 2026-06-11
- React/TS shell: Dockview docking, link groups, 5 workspace modes with
  layout persistence, command grammar (order-flexible), palette.
- Deterministic mock feed with bands, dismissal picklist, invalidation.
- Hard budget engine (client) + energy bar; unified blotter schema.
- 25 contract tests; 100.8KB gz.
