# Accelerated soak procedure (pre-release)
1. `VW_SNAP_S=4 VW_CYCLE_EVERY=2 uvicorn server.app:app --port 8787`
2. Let ~15 cycles accumulate. Assert: `/api/health` rejected_cards == 0.
3. Exercise the funnel via REST: watching, dismissed(+reason), blotter
   open→acted→close(+pnl). Assert telemetry funnel counts each event.
4. Measure: GET /api/feed < 50ms, /api/health < 10ms.
5. `kill -9` the sidecar; restart; assert funnel + sticky statuses
   survived (SQLite WAL).
Phase 1 baseline: feed 11.8ms · health 1.9ms · 0 provenance rejects.
