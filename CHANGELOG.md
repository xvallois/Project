# Changelog

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
