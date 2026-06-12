# ADR 0002 — FastAPI sidecar imports the engine in-process
**Status** accepted (Phase 1) · **Decision** the sidecar `import volwatch`
directly; zero IPC inside analytics; one asyncio loop drives snaps/cycles;
analytics run in worker threads off the serve path.
**Why** the engine is Python and latency-sensitive composition (packet →
detectors → verifier) is simplest and fastest in one process. Engine
config paths resolve from its repo root (chdir at startup).
