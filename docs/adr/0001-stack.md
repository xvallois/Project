# ADR 0001 — Frontend/desktop stack
**Status** accepted (Phase 0) · **Decision** React 18 + TS, Dockview 1.16
(docking), Zustand (+TanStack Query later), ECharts for charts, Tauri v2
Windows-first for the desktop shell (Phase 5). Tailwind/shadcn deferred to
when dialog primitives multiply; bespoke token CSS until then.
**Why** Bloomberg-class density needs a real docking engine; ECharts
handles dense financial drawing without licence risk; Tauri gives
multi-window + small footprint over Electron.
