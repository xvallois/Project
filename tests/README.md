# tests/

Unit/contract suites are COLOCATED with their code:
- `server/tests/` — pytest (provenance, lifecycle, budget, analyst gate,
  live-engine integration): 34 tests
- `frontend/src/**/*.test.ts` — vitest (grammar, budget, feed,
  persistence): 25 tests

This directory holds cross-cutting procedures:
- `soak.md` — the accelerated trading-day validation used for Phase 1.
  Run it before any release tag.
