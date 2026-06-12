# volwatch Workstation — Frontend & Platform Architecture (v1.0)

**Status:** Design contract. No production code until this is agreed.
**Scope:** Transform the existing volwatch Python engine (data, analytics,
signals, research, backtest — all built and tested) into a desktop trading
workstation. The engine is the source of truth; this document is about
everything between the engine and the trader's eyes and hands.

---

## 1. Requirements Analysis

### The user
One professional FX options trader (later: a small desk), 6–10 hours/day in
the app, 2–4 monitors, keyboard-driven, zero tolerance for latency or
ambiguity about data freshness. The app competes for screen real estate with
a Bloomberg Terminal — it must justify every pixel.

### Jobs to be done, ranked
1. **Monitor**: is anything dislocated right now? (signals, surfaces, carry)
2. **Investigate**: why is it dislocated? (smile/term drill-down, history,
   model views, write-ups, assistant)
3. **Decide & record**: express the trade, log it, watch it (blotter,
   positions, risk)
4. **Trust**: is the data good? (health, staleness, validation, arb flags)

### Hard constraints derived from the engine
- Market data cadence is **5-minute snaps + 30-minute analytic cycles** —
  this is NOT a tick-streaming app. Realtime design optimizes for
  *event freshness and zero-cost idle*, not throughput.
- All analytics already exist in Python. The frontend renders; it must
  **never recompute** (one source of truth — the lesson already encoded in
  the Streamlit dashboard's data/app split, kept and promoted).
- The ResearchPacket is the audit artifact; the UI must preserve numeric
  traceability end-to-end (a number on screen is a packet/store field).

### Non-goals (v1)
- Order routing / OMS integration (blotter is a desk record, not execution).
- Mobile. Multi-tenant auth. Theming beyond dark/light.

---

## 2. Stack Decision Record

Format: decision → alternatives → why → what would change the call.

### 2.1 Frontend: React 18 + TypeScript — **ACCEPT**
- *Alternatives:* Solid (faster fine-grained reactivity), Svelte 5.
- *Why React:* the three ecosystem pillars this app lives on — docking
  (Dockview), data grids (AG Grid), charts (ECharts wrappers) — are
  first-class in React and second-class elsewhere. Raw framework speed is
  not our bottleneck; chart canvases and grid virtualization are, and those
  are framework-independent.
- *Reversal trigger:* none realistic for this product.

### 2.2 Styling: Tailwind + shadcn/ui — **ACCEPT, with a token layer**
- shadcn gives owned-source primitives (menus, dialogs, popovers, `cmdk`
  command palette) with no design lock-in. But its default spacing/type
  scale is consumer-app airy. We define a **density token layer**
  (§7) and restyle primitives against it — shadcn is scaffolding, not the
  design.
- *Alternative considered:* hand-rolled CSS modules — more control, slower;
  rejected for velocity.

### 2.3 Docking: **Dockview** (MIT) — the most important library choice
- *Alternatives:* FlexLayout (Caplin), Golden Layout v2, rc-dock.
- *Why Dockview:* VS Code-grade docking model; **serializable layouts**
  (saved workspaces become a JSON document); floating groups and popout
  windows (pairs with Tauri multi-window for multi-monitor); active
  maintenance; headless styling (takes our tokens).
- *Why not Golden Layout:* maintenance risk. *Why not FlexLayout:* weaker
  popout story.
- *Reversal trigger:* if popout-to-native-window proves unreliable on
  WebView2, FlexLayout is the fallback; the panel contract (§4.2) is
  deliberately docking-library-agnostic.

### 2.4 Grids: **AG Grid Community** for blotter & signal monitor
- *Alternative:* TanStack Table + TanStack Virtual (headless, lighter).
- *Why AG Grid where it matters:* transaction-based row updates with cell
  flash (the canonical "blotter blink"), column state persistence, range
  selection, clipboard — re-implementing these on TanStack is weeks of
  undifferentiated work. TanStack Table remains the choice for simple
  read-only tables (carry, health) where AG Grid is overkill.
- *Cost note:* Community edition (MIT) covers v1 entirely. Enterprise
  (pivoting, row grouping, Excel export) is a per-developer license —
  **decision needed from you** only if/when grouping the blotter by
  strategy becomes a requirement.

### 2.5 Desktop: **Tauri v2** — ACCEPT, with eyes open
- *Alternative:* Electron (the institutional incumbent — OpenFin, most
  vendor terminals).
- *Why Tauri:* 10–20× smaller binary, far lower idle memory (matters when
  living next to a Bloomberg Terminal), Rust core, first-class
  **multi-window** in v2 (each monitor gets a native window hosting a dock
  root), sidecar process management (§3.1).
- *Honest tradeoffs:* (a) system webviews differ — WebView2 (Chromium) on
  Windows, WKWebView on macOS; we test on the actual desk OS (assume
  Windows) and treat macOS as best-effort; (b) smaller ecosystem of
  finance-specific glue than Electron.
- *Reversal trigger:* a hard WKWebView/WebView2 rendering bug in ECharts-GL
  surfaces → Electron port is contained (the web app is 95% of the code and
  doesn't change).

### 2.6 Backend: **FastAPI as a Tauri sidecar** — ACCEPT
The decisive insight: volwatch is Python, so the API layer should be **the
same process** that imports the engine — no serialization boundary inside
the analytics path. FastAPI wraps the existing `ParquetStore`,
`SignalEngine`, artifacts, and backtest directly. Tauri spawns/supervises
it as a sidecar (bundled binary via PyInstaller), owns its lifecycle, and
the UI talks to `localhost`.

### 2.7 Database: **SQLite now, not PostgreSQL** — CHALLENGED
- Market data **stays in Parquet/DuckDB** — already built, columnar,
  perfect for time-series scans. Don't move it; a Postgres migration would
  be a regression.
- What needs OLTP is small and single-writer: blotter entries, positions,
  workspaces, panel settings, notification history, assistant threads.
  For a single-desk **desktop** app, Postgres means a server to install,
  start, back up, and secure — pure operational drag.
- **SQLite via SQLAlchemy** (WAL mode) covers it; the ORM boundary makes
  Postgres a connection-string change if this ever becomes a multi-user
  server deployment. That future trigger is real but not v1.

### 2.8 Realtime: **One WebSocket, topic pub/sub, snapshot+delta** — ACCEPT
Protocol in §3.3. SSE was considered (simpler) and rejected: the assistant
needs bidirectional streaming and panels need dynamic subscribe/unsubscribe.

### 2.9 Charts: **ECharts (+ echarts-gl)** — CHALLENGED vs your list
- *TradingView:* the full Charting Library is license-gated and built for
  OHLC price action — wrong tool for vol surfaces/smiles. (The free
  `lightweight-charts` is kept ONLY for the spot-history mini-chart.)
- *Highcharts:* commercial license with no capability we need over ECharts.
- *Why ECharts:* Apache-2.0, canvas rendering at 60fps for our densities,
  `surface3D` via echarts-gl for the vol surface, excellent dataset/series
  update model for delta patching. One charting grammar across every panel
  = one skill for maintainers.

### 2.10 State: **Zustand + TanStack Query** — recommended (you didn't specify)
- TanStack Query owns request/cache/refetch for REST reads.
- Zustand stores (one per domain: market, signals, blotter, ui) receive WS
  deltas; panels subscribe with fine-grained selectors so a EURUSD tick
  re-renders only EURUSD-linked panels.
- Redux rejected: ceremony without benefit at this scale.

### 2.11 AI: **Claude API, server-side, streaming** — ACCEPT
Key never touches the renderer. FastAPI endpoint streams tokens over the
WS assistant topic. The existing `ResearchPacket` + per-panel context
chips (§5.6) form the prompt payload — the numeric-traceability contract
from the engine carries over: the assistant must cite packet fields, and
the UI renders those citations as hoverable provenance.

---

## 3. System Architecture

### 3.1 Process model
```
┌────────────────────────────── Desktop ─────────────────────────────┐
│  Tauri shell (Rust)                                                │
│   ├─ Window 1..N (one per monitor) ── WebView ── React app         │
│   ├─ sidecar supervisor ──────────┐                                │
│   └─ native: tray, global hotkeys │                                │
│                                   ▼                                │
│  FastAPI sidecar (Python, localhost only)                          │
│   ├─ imports volwatch.* directly (store, engine, ai, backtest)     │
│   ├─ REST: /api/...      (reads, commands)                         │
│   ├─ WS:   /ws           (topics, deltas, assistant stream)        │
│   ├─ scheduler (existing run_daemon jobs, in-process)              │
│   └─ SQLite (blotter, positions, workspaces, notifications)        │
│                                   │                                │
│  Parquet/DuckDB store (existing, unchanged)                        │
└────────────────────────────────────────────────────────────────────┘
```
One process boundary total (WebView ↔ sidecar over localhost). The engine
runs inside the API process — zero IPC inside analytics.

### 3.2 REST surface (read = cheap, command = explicit)
```
GET  /api/cycle/latest            → packet + signals + writeups (artifacts)
GET  /api/market/quotes           → latest vol/spot/forward frames
GET  /api/market/history          ?pair&tenor&field&from → daily series
GET  /api/surface/{pair}          → calibrated smiles, SABR/SSVI params, arb
GET  /api/carry/{pair}            /api/fwdvol/{pair}
GET  /api/health                  → staleness, rmse, flags, alerts
POST /api/backtest                → async job, progress over WS
CRUD /api/blotter /api/positions /api/workspaces /api/notifications
POST /api/assistant/threads/{id}/messages  → streamed over WS
```

### 3.3 WebSocket protocol
One connection per window. JSON envelope:
```json
{"topic":"signals","type":"delta","seq":4182,"ts":"...","data":{...}}
```
- **Topics:** `cycle` (new artifacts ready), `market.{pair}`, `signals`,
  `health`, `notifications`, `blotter`, `assistant.{thread}`,
  `job.{backtest_id}`.
- **Snapshot+delta:** on subscribe, server sends `type:"snapshot"` with
  current state + `seq`; deltas increment `seq`; a gap triggers client
  resubscribe (idempotent). Reconnect = resubscribe all + resync — no
  client-side guessing.
- **Coalescing:** server batches deltas per topic at ≤10Hz; client applies
  inside `requestAnimationFrame`. At our cadence this is over-engineering
  that costs nothing and removes the ceiling.
- **Freshness is UI-critical:** every panel header shows the age of its
  data, fed by topic `ts` — staleness is rendered, never assumed.

---

## 4. UI Architecture

### 4.1 Shell anatomy
```
┌──────────────────────────────────────────────────────────────────────┐
│ TOP BAR   [≡] MORNING│RV HUNT│EXEC +   ⌘K command line   NY LDN TYO 🔔│
├──┬───────────────────────────────────────────────────────────────────┤
│R │                                                                   │
│A │                     DOCK AREA (Dockview)                          │
│I │            panels, tabs, splits, floating groups                  │
│L │                                                                   │
├──┴───────────────────────────────────────────────────────────────────┤
│ STATUS  feed ● 12s ago │ cycle 09:30 ✓ │ 3 alerts │ ws 4ms │ v1.0    │
└──────────────────────────────────────────────────────────────────────┘
```
- **Top bar:** workspace tabs (Ctrl+1..9), the command line (§4.4), world
  clocks, notification bell with unread badge.
- **Rail:** icon launcher for panel types; drag to dock or click to open
  in active group.
- **Status bar:** the trust strip — feed freshness, last cycle, alert
  count, WS latency. Always visible, never scrolls away.

### 4.2 The panel contract (the load-bearing abstraction)
Every panel is a module implementing:
```ts
interface PanelModule {
  id: PanelKind            // "smile" | "surface" | "signals" | ...
  mnemonic: string         // "SMIL", "VSUR", "SIGS", ...
  component: React.FC<PanelProps>
  params: ZodSchema        // pair, tenor, ... — serialized into workspaces
  subscribe(params): Topic[]   // WS topics this panel needs
  contextChip(params, state): ContextChip  // what it offers the assistant
}
```
Consequences: workspaces serialize as `{dockviewLayout, panelParams[]}`;
the docking library is swappable; the assistant can ingest any panel's
current view; subscriptions are managed centrally (open panels = active
topics, closed = unsubscribed).

### 4.3 Panel linking — link groups (signature interaction #1)
Bloomberg-style colored link groups **A / B / C / D**. Each panel header
carries a link chip; panels sharing a color share a *context* (pair, and
optionally tenor). Change pair in any A-linked panel → every A panel
follows. Unlinked panels are pinned. This is the single highest-leverage
workflow feature for a vol trader comparing pairs: one workspace, two link
groups, instant side-by-side.

### 4.4 The command line (signature interaction #2)
`⌘K` or just start typing. Grammar: `MNEMONIC [PAIR] [TENOR] [args]`.
- `SMIL EURJPY 3M` → opens/focuses a smile panel on EURJPY 3M
- `SIGS >2` → signal monitor filtered to |z| > 2
- `BLOT NEW` → new blotter ticket    `ASST why is 6m9m kinked` → assistant
- Plain text falls through to fuzzy search (pairs, panels, commands,
  recent ideas).
Mnemonics print in every panel header — the UI teaches its own language.
This is how the app earns "lives next to a Terminal" credibility:
navigation at typing speed, mouse optional.

### 4.5 Workspaces & multi-monitor
- Named workspaces (tabs): serialized layout + params + link-group state,
  persisted via API (SQLite), switchable Ctrl+1..9.
- Multi-monitor: **one Tauri window per monitor**, each hosting a dock
  root; a workspace addresses the window set. Panels move between windows
  via Dockview popout → adopted as native window. Layouts saved per
  monitor-fingerprint so docking a laptop restores sanely.

### 4.6 Keyboard map (excerpt — full map ships in-app under `KEYS`)
`⌘K` command line · `Ctrl+1..9` workspaces · `Ctrl+\` split ·
`Ctrl+W` close panel · `Alt+A/B/C` cycle link group of focused panel ·
`F` freshness inspector · `N` notifications · `.` repeat last command.

### 4.7 Notification center
Alerts (from the existing ops/health pipeline) + signal firings + cycle
completions land as toasts (severity-styled, auto-dismiss except CRIT) and
persist in a right drawer with filters; every notification deep-links to
the relevant panel state (`calendar arb USDJPY` → opens SURF USDJPY with
the violating tenors highlighted).

---

## 5. Screens & Default Workspaces

### 5.1 "MORNING" (default)
```
┌─────────────┬──────────────────────────┬───────────────┐
│ SIGS        │ VSUR  [A] EURUSD         │ IDEA          │
│ signal      │ 3D surface / heatmap     │ trade write-  │
│ monitor     ├──────────────────────────┤ ups, ranked   │
│ (all pairs) │ TERM [A]  │ SMIL [A] 3M  │               │
├─────────────┴───────────┴──────────────┴───────────────┤
│ HLTH  staleness · rmse · arb margins · validation      │
└─────────────────────────────────────────────────────────┘
```
Flow: scan SIGS → click row → A-group repoints surface/term/smile →
read IDEA write-up → `ASST` for the why → `BLOT NEW` if acting.

### 5.2 "RV HUNT"
Two link groups side-by-side: `[A] pair 1` vs `[B] pair 2` — TERM+SMIL
columns each, CARRY comparison strip below, fwd-vol ladders. Built for the
cross-pair and triangle work the signal library generates.

### 5.3 "EXEC / RISK"
BLOT (full-width grid) over POSN (vega by pair×tenor ladder, aggregated
greeks) + NOTF drawer pinned open. Dense, no charts, pure numbers.

### 5.6 Research assistant panel (ASST)
Chat column with **context chips**: every open panel offers its current
view as an attachable chip (`[SMIL EURJPY 3M]`, `[SIGS top 5]`,
`[packet 09:30]`). Chips serialize the exact data the panel renders —
the assistant reasons over what the trader sees, and its numeric claims
carry hoverable provenance back to packet fields. Streamed responses;
threads persisted; "promote to IDEA card" action.

---

## 6. Component Hierarchy (abridged)
```
<App>
 ├─ <ShellProviders>        zustand stores, query client, ws manager, theme
 ├─ <TopBar>                <WorkspaceTabs> <CommandLine> <Clocks> <Bell>
 ├─ <Rail>
 ├─ <DockHost>              Dockview root
 │   └─ <PanelFrame>        header: title, mnemonic, link chip, freshness,
 │       │                  params controls; body ↓ (lazy, code-split)
 │       ├─ <SurfacePanel>  <EChartsSurface3D|Heatmap>
 │       ├─ <SmilePanel>    <EChartsSmile> model overlays, history ghosts
 │       ├─ <TermPanel>     <EChartsTerm> + <FwdVolLadder>
 │       ├─ <SignalsPanel>  <AgGrid> + <SignalDrilldown> (math/intuition/
 │       │                   edge/failure-modes from the engine's docs)
 │       ├─ <IdeasPanel>    <IdeaCard>*  (scenario grid, provenance)
 │       ├─ <BlotterPanel>  <AgGrid tx-updates> + <TicketForm>
 │       ├─ <PositionsPanel><VegaLadder> <GreeksStrip>
 │       ├─ <CarryPanel> <HealthPanel> <BacktestPanel>
 │       └─ <AssistantPanel><Thread> <ContextChips> <Composer>
 ├─ <StatusBar>
 └─ <NotificationDrawer> <Toaster> <CommandPalette(cmdk)>
```

## 7. Design Language (token system)
- **Palette** (dark-first): `ink #0B0E14` (app bg) · `panel #11151D` ·
  `chrome #1A2029` (headers/rails) · `line #232B37` · `text #D7DEE8` ·
  `muted #8B95A6` · **accent `desk-amber #E8A33D`** (focus, command line,
  link to terminal heritage — used sparingly) · semantic-only
  `up #3FB68B` / `down #E0586E` / `warn #E8A33D` / `crit #E0586E`.
  Link groups: A `#5B9DD9` B `#C2884E` C `#7FAE6E` D `#A98BC4` — desaturated
  so they label, never shout.
- **Type:** IBM Plex Sans (UI) + **IBM Plex Mono for every number**
  (`font-variant-numeric: tabular-nums` everywhere; columns never wiggle).
  Scale: 11/12/13/15/18 — 12px is the working size; nothing decorative.
- **Density:** 4px spacing grid; row height 24px (grids), 28px (forms);
  panel header 28px; border-radius 4px max — crisp, not friendly-rounded.
- **Motion:** 120ms ease-out on dock operations and drawer; cell flash
  300ms; **no ambient animation** — motion only encodes change.
- **Quality floor:** visible focus rings (amber), full keyboard
  reachability, `prefers-reduced-motion` honored, light theme as a
  first-class token swap (some desks demand it for print/compliance).

## 8. Performance Budgets (enforced in CI via Playwright traces)
- Cold start to interactive shell: **< 1.5s** (sidecar warms in parallel)
- Panel open (code-split chunk + first paint): **< 150ms**
- WS delta → paint: **< 50ms** · sustained 60fps on dock drag/resize
- Workspace switch: **< 200ms** · Memory @ 12 panels: **< 450MB**
- Techniques: code-split per panel; canvas charts (no SVG above 200 pts);
  AG Grid transactions (never full re-render); zustand selector
  subscriptions; rAF-batched WS application; chart instances pooled per
  panel kind; DuckDB/Parquet reads stay server-side.

## 9. Key User Flows
1. **Morning open** → app restores last workspace + window set → status
   bar confirms feed/cycle → SIGS sorted by |z| → click → A-group fans out
   → IDEA card → annotate → done in < 90 seconds, mouse optional.
2. **Signal → trade**: SIGS row → drill-down (engine's math/failure-modes
   inline) → `ASST` with `[SIGS row]` chip ("what invalidates this?") →
   `BLOT NEW` pre-filled from the idea (pair/structure/tenors) → POSN
   updates → notification on fill-note save.
3. **Data doubt**: status bar shows amber staleness → `F` opens freshness
   inspector (per-topic ages, last validation flags) → HLTH panel →
   deep-link from the arb alert to the offending surface tenor.

## 10. Build Phases (each independently shippable)
| Phase | Deliverable | Exit criterion |
|---|---|---|
| 0 | Token system + shell + dock + command line, mock data | Layout serializes/restores; ⌘K opens panels |
| 1 | FastAPI gateway over volwatch (read paths) + WS cycle/signals/health | Live artifacts render in SIGS/IDEA |
| 2 | Chart panels: TERM, SMIL, VSUR, CARRY + link groups | A/B linking across 6 panels @60fps |
| 3 | Blotter + positions (SQLite) + notifications | Ticket → blotter → vega ladder round-trip |
| 4 | Assistant (Claude streaming + context chips + provenance) | Cited answer from a live packet |
| 5 | Tauri packaging, sidecar supervision, multi-window, workspace persistence | Two-monitor restore after reboot |
| 6 | Perf hardening to §8 budgets, keyboard completeness, light theme | CI budget gates green |

## 11. Risks & Open Questions (need your call)
1. **AG Grid Enterprise** appetite if blotter grouping/pivot becomes a
   requirement (Community covers v1)?
2. **Blotter scope**: desk record only (v1 assumption) — or is OMS/FIX
   integration on the horizon (changes the data model now)?
3. **Monitor count & OS** on the desk (Windows assumed; affects webview
   testing matrix)?
4. **Claude API now approved** for the assistant, or do we wire the
   template researcher into ASST first and stream Claude later? (The
   interface is identical either way — researcher swap is one config word.)
