# Architecture (summary)

```
┌────────────────────────────── frontend (React/TS) ──────────────────────────┐
│ TopBar(workspaces) │ Rail │ Dockview panels: OPPS·ASST·VHEAT·SMIL·RCHP·SIGS │
│ command grammar (core/grammar) · link groups · keyboard layer · budget bar  │
└───────────────▲───────────────────────────────▲─────────────────────────────┘
        REST    │            WS topics: feed / health / brief (seq+resync)
┌───────────────┴───────────────────────────────┴─────────────────────────────┐
│ server (FastAPI sidecar)                                                    │
│  engine loop ── volwatch (in-process): pipeline→validate→store→signals→packet│
│  detectors (Tier-1) ─→ PROVENANCE VERIFIER ─→ SQLite lifecycle ─→ WS hub    │
│  analyst: evidence pack → provider(claude|stub) → NUMERIC GATE → brief      │
│  budget (hard, tiered, reserve) · telemetry funnel · unified blotter        │
└──────────────────────────────────────────────────────────────────────────────┘
         data/: Parquet history (engine truth) + workstation.db (decisions)
```

Decisions live in `docs/adr/` (one file per locked decision). Full design
contracts: `assets/design/` (v1.0, v1.1) with HTML mockups in
`assets/mockups/`. Interface contracts: `contracts/`.

Trust model: the deterministic engine is the source of truth; the Analyst
interprets and is structurally prevented (gates, schema, budget) from
originating market facts. See `contracts/provenance.md`.
