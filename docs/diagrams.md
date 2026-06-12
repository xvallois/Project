# Component & flow diagrams

## Investigation flow (flagship)
```
OPPS card ──I──▶ POST /api/investigate
                  │ budget_spend(tier)            ──refused──▶ typed refusal → UI
                  ▼
            build_pack(card, co-signals, health, LEDGER)
                  ▼
            provider.complete()  (capped loop ≤2)
                  ▼
            gate_brief(): sections + numeric citations
              ok/degraded ──▶ briefs table ──▶ WS topic "brief" ──▶ ASST panel
              rejected    ──▶ telemetry analyst_rejected (nothing rendered)
```

## Card lifecycle (server-authoritative)
```
detect ─▶ verify(provenance) ─▶ apply_cycle
   new ─▶ seen ─▶ watching ─▶ acted(sticky)
    │                │
    └── dismissed(12h cooldown; band escalation overrides)
    └── missing×2 ─▶ invalidated (debounced)
every transition ─▶ events table (the funnel dataset)
```
