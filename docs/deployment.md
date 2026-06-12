# Deployment (desk)

1. Checkout this repo — the engine is vendored at `engine/`.
2. `./scripts/setup.sh` (set `VW_ENGINE_PATH` only to use an external
   engine checkout instead of the vendored one)
3. Configure env (see README table). Desk profile:
   `VW_PROVIDER=bbg VW_SNAP_S=300 VW_CYCLE_EVERY=6 VW_DATA=D:/vw-data`
   `ANTHROPIC_API_KEY=… VW_ANALYST=claude`
   `VW_CORS_ORIGINS=<origin serving frontend/dist>` — REQUIRED on the
   desk: the sidecar only allows localhost:5173 dev origins by default
   and never falls back to `*`; browser calls from any other origin are
   refused until this is set (e.g. `https://desk-host:8443`).
4. Run sidecar as a service: `uvicorn server.app:app --port 8787`
   (single worker — the engine loop owns state; do NOT scale workers).
5. Serve `frontend/dist` statically or run the Tauri shell (Phase 5);
   point it at the sidecar with `VITE_API`.
6. Back up `VW_DATA/workstation.db` daily (institutional memory).
7. First live-key task: tune the analyst gate drop-threshold against real
   model output; watch `analyst_rejected` telemetry.

Bloomberg note: `bbg` requires Desktop API entitlements on the host;
`bql` runs only inside BQuant. The mock provider exercises identical code
paths for UAT. Bring-up smoke checklist: `docs/bbg-bql-smoke.md`.

Dependency pinning: Python installs are constrained by `constraints.txt`
(the exact versions the v4.0.0 gates passed on) in setup.sh and CI;
update pins deliberately, re-running the full gate chain. The frontend
is locked by `package-lock.json` (`npm ci` in CI).
