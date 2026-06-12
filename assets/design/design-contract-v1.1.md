# volwatch Workstation — Design Iteration v1.1
## Opportunity Discovery · Workspace Memory · Multi-Monitor · Keyboard · Assistant Workflows

**Status:** supersedes §4–5 of v1.0 where they conflict. Locked decisions
recorded in §0. This is still design — implementation starts at Phase 0
only after sign-off.

---

## 0. Decisions locked (from your review)
- SQLite, schema migration-friendly (every table gets surrogate PKs,
  ISO timestamps, JSON columns only for genuinely schemaless payloads,
  Alembic from day one).
- Tauri primary; **Windows/WebView2 first** — macOS best-effort.
- **2 monitors minimum, 3 ideal** — §4 designs the roles explicitly.
- Blotter = desk record: ideas, paper trades, live trades, notes,
  outcomes, post-mortems. Extensible, not OMS-shaped (§6.3).
- **Claude wired from day one** — the assistant is load-bearing, and §1–§5
  are designed around that.
- 3D surface demoted to an on-demand mode. §2 is the replacement.

---

## 1. Opportunity Discovery — the Analyst, not a chatbot

### 1.1 Mental model
The trader's first question is "what deserves my attention right now?" —
not "what should I ask?". So the assistant's PRIMARY surface is a
**feed it writes**, and chat is the drill-down, not the front door.

### 1.2 Two-tier pipeline (cost, latency, and trust by construction)

```
every 5-min snap ─┐
                  ▼
   TIER 1 — Deterministic detectors (Python, free, instant)
   • existing signal engine (z-scored, documented)
   • surface-move detector: per-cell |Δ| vs trailing distribution
   • percentile breach: any metric crossing p5/p95 of its own history
   • regime sentinels: realized-vol regime shift (variance ratio),
     correlation regime shift, curve slope sign change
   • event-pricing checks (existing event_vol)
                  │  emits Observation records (typed, numeric, sourced)
                  ▼
every 30-min cycle (and on-demand)
   TIER 2 — Claude synthesis ("the Analyst")
   • input: new/changed Observations + ResearchPacket + workspace brief
     (§3.5) + open positions summary + recent feed state
   • output: OpportunityCards — clustered, prioritized, narrated
   • clustering: kink + fwd-vol + event on the same tenor = ONE card,
     not three rows (the thing rule engines can't do)
   • "what changed" framing: diffs vs the previous cycle, never
     re-shouting standing items
   • each numeric claim carries an evidence ref (packet/store path) —
     the engine's traceability contract, enforced server-side: a card
     with an unverifiable number is rejected and regenerated
```

Model tiering: Tier-2 triage runs on a fast model (Haiku-class) every
cycle; **Investigate** deep-dives (§5.3) run on Sonnet/Opus on demand.
A token-budget meter lives in HLTH — cost is an ops metric like latency.

### 1.3 The OpportunityCard (anatomy)
```
┌──────────────────────────────────────────────────────────────┐
│ ▲ ACTIONABLE   SKEW DISLOCATION            EURJPY · 3M    A↗ │  header:
│ Cross skew rich vs legs and vs its own 2-year history        │  confidence
│                                                              │  band, type,
│ evidence ▸  RR25 −1.41 (p97) · ρ_imp .68 vs ρ_real .08       │  pair, link-
│             spot-vol beta unchanged (−0.21 → −0.24)          │  fan-out btn
│             [sparkline: RR25 90d]   data quality ✓           │
│ why now  ▸  one-sided spot move loaded JPY-call hedging;     │  Tier-2
│             delivered correlation hasn't followed            │  narrative
│ confidence: |z| 3.4 · persisted 3 cycles · models agree      │  inputs
│             · backtest prior 61% (n=42)                      │  visible
│ [Investigate]  [→ Workspace]  [→ Blotter]  [Watch]  [Dismiss]│
└──────────────────────────────────────────────────────────────┘
```
- **Confidence bands, not fake percentages:** `SPECULATIVE / WATCH /
  ACTIONABLE`, computed deterministically from (|z|, persistence in
  cycles, data-quality flags, SABR↔SSVI agreement, that signal's
  backtest hit-rate prior). The Analyst may move a card ±1 band but must
  state why ("event in bucket justifies the premium → downgraded").
  The inputs are always rendered — confidence is *evidence strength*,
  never probability of profit, and the UI says so on hover.
- **Lifecycle:** `new → seen → watching → acted | dismissed | invalidated
  | expired`. Invalidation is first-class: when the dislocation closes
  *without* the trader acting, the card flips to a quiet "closed: −2.1vp
  convergence you didn't take" state — that's information, and over time
  it's the trader's own calibration data.
- **Feed hygiene:** dedup key `(type, pair, structure)`; cooldown after
  dismissal (with optional reason — feeds future ranking); standing items
  compress into a single "still open (4d)" row; CRIT data-quality issues
  can suppress cards built on flagged quotes (a dislocation on a stale
  quote is a data alarm, rendered as such).

### 1.4 OPPS panel UX
A vertical feed (newest/highest first) with band filter chips, type
filter, pair filter (link-group aware), and a top "since you left"
divider after any absence > 30 min. Row density ~64px collapsed; cards
expand inline. `→ Workspace` performs the **fan-out**: repoints the
active link group and opens any missing panels for that opportunity type
(skew card → SMIL + RCHP + history percentile view).

---

## 2. Surface visualization, rethought (your 3D challenge — sustained)

You're right, and here's the principled version of why: 3D surfaces
encode value in *projected height*, which is unreadable without rotation,
occludes its own far side, and can't be diffed or percentile-colored.
They're narrative devices. Day-to-day RV work needs **comparison,
history, and decomposition** — flat encodings win on all three.

### 2.1 VHEAT — the new primary surface view
Tenor × strike-node grid (9 × 5), one cell per quote-vector point, with
**three lenses** (hotkey `L` cycles):
- **LEVEL** — vols, sequential colormap.
- **Δ** — change vs T-1/T-5/last cycle (selectable), diverging colormap
  centered at 0. *The morning view.*
- **%ILE** — each cell's percentile vs its own trailing 1y distribution,
  diverging around p50. *The rich/cheap map at a glance — this lens is
  the default.*
Cells are live (flash on snap), readable (value printed in-cell at this
density), and clickable (→ SMIL/TERM at that node). The 3D view remains
as a VHEAT mode (`3` key) for communicating shape — demoted, not deleted.

### 2.2 RCHP — rich/cheap decomposition
Per pair: a column decomposing where richness lives —
`ATM vs realized (carry)` + `skew (RR vs history & vs realized beta)` +
`convexity (BF vs history)` + `term (kink residuals)` — each as a
percentile bar with the underlying numbers. Answers "rich *how*?" in one
glance; feeds directly from existing carry/skew/kink analytics.

### 2.3 RVSC — relative value screen
The matrix view: pairs × {ATM %ile, IV−RV, RR %ile, BF %ile, 3M6M fwd
kink, triangle gap, event premium ratio} — sortable, conditional-colored,
filterable, every cell deep-linking. This is the "screener" institutional
muscle memory expects, and it's pure existing-engine data.

### 2.4 SMIL v2 — percentile cone
Smile chart gains a **historical cone** (p10–p90 band of each node over
the lookback) behind today's smile + SABR/SSVI fit overlays. Instantly
shows *which wing* is stretched. TERM gets the same cone treatment.

---

## 3. Workspace Memory System

### 3.1 A workspace is a *mode*, not a layout
```ts
Workspace {
  id, name, mnemonic            // "ECB", "NFP", "MORN", "G10RV", "RISK"
  windows: { fingerprint, dockviewLayout, panelParams[] }[]   // per monitor
  linkGroups: { A: {pair,tenor}, B: ... }
  filters: { opps: BandFilter, sigs: ZFilter, pairs: string[] }
  alertProfile: { toastMin: Severity, perType: {...}, routing: MonitorRole }
  assistantContext: {
    brief: string               // standing instructions (§3.5)
    pinnedChips: ContextChip[]
    threadId?: string           // the workspace's running conversation
  }
  schemaVersion
}
```
Stored in SQLite as versioned rows + JSON payload; Alembic-migratable;
export/import as a file (desk sharing, backup).

### 3.2 The five shipped modes (templates, fully editable)
| Mode | Layout bias | Filters/alerts | Assistant brief (excerpt) |
|---|---|---|---|
| **MORN** Morning Vol Check | OPPS + VHEAT(%ile) + RVSC + HLTH | all pairs, WATCH+ | "Summarize overnight surface moves first; flag anything that crossed p95." |
| **ECB** ECB Day | EUR pairs fanned, event panels, 1W/2W focus | EUR only, event alerts CRIT-toast | "Prioritize EUR event pricing vs delivered history; track the 1W bucket through the print." |
| **NFP** NFP Mode | USD majors, ON/1W, event vol | USD pairs, tight staleness alerts | "USD event premium vs NFP delivered; watch ON→1W fwd vol." |
| **G10RV** Relative Value | RVSC + dual link groups A/B + triangle panels | cross-pair signals boosted | "Rank cross-pair and triangle dislocations; ignore sub-WATCH carry items." |
| **RISK** Risk Management | BLOT + POSN + scenario strip + NOTF pinned | position-linked alerts only | "Relate every new alert to open positions; flag concentration." |

### 3.3 Event-aware activation
The event calendar already exists in the engine. When a high-importance
event is < 24h out, a notification offers the matching mode: *"ECB
tomorrow 13:45 — switch to ECB Day at 07:00?"* (accept / snooze / always).
Modes can also auto-revert after the event window. This is the moment the
workspace system stops being a layout manager and starts being a desk
routine.

### 3.4 Switching & versioning UX
`Ctrl+\`` opens the **mode switcher** (grid of live thumbnails +
mnemonics, type-to-filter); `WS ECB` in the command line does the same.
Dirty-state model: layout changes accumulate as an unsaved delta
(asterisk on tab); `Ctrl+S` saves, `Ctrl+Shift+S` saves-as, `Ctrl+Z` on
the tab reverts to last saved. Auto-snapshot on switch (last 5 kept).

### 3.5 The standing brief is the key innovation here
The `assistantContext.brief` is prepended to every Tier-2 triage and
every ASST conversation while the mode is active. ECB Day doesn't just
*look* different — the Analyst literally reads the room differently.
Briefs are plain text, editable in place, versioned with the workspace.

---

## 4. Multi-monitor design (Windows-first, 2–3 displays)

### 4.1 Monitor roles
Named roles, assigned per workspace, remembered per monitor fingerprint:
```
CANVAS (primary)  — investigation: VHEAT/SMIL/TERM/RCHP fan-outs, RVSC
WATCH  (second)   — always-on: OPPS + SIGS + HLTH + notification drawer
DESK   (third)    — ASST (full-height) + BLOT/POSN
```
2-monitor degradation: DESK content docks into CANVAS's right third.
1-monitor (laptop, rare): WATCH becomes the first tab; toasts carry more
weight. Fingerprint = sorted (count, resolutions, scale factors); a
docked-laptop → desk transition restores the right variant automatically.

### 4.2 Cross-window mechanics
- Each monitor = one Tauri native window hosting a dock root; the window
  set IS part of the workspace document.
- **Link groups are global across windows** — the sidecar relays
  link-context changes to all windows over WS (one hop, < 5ms local).
- Panel movement: Dockview popout → Tauri adopts as child window → drop
  onto another window's dock re-docks it.
- Focus discipline: `⌘K` always opens on the *focused* window; `F8`
  cycles window focus; alerts route per the workspace's `alertProfile`
  (default: toasts on WATCH; CRIT on all; never on a window showing a
  full-screen chart during a presentation — "presenter guard").

---

## 5. Keyboard-first navigation (the full grammar)

### 5.1 Principles
Mouse-optional for 100% of monitoring/investigation flows; mouse-helpful
for layout surgery. Every interactive element is reachable; **hold `Alt`
to reveal key badges on everything** (hint overlay, Vimium-style). All
bindings remappable (settings, not per-workspace).

### 5.2 The command line grammar (formalized)
```
input      := command | jump | search
command    := MNEMONIC args*        SMIL EURJPY 3M · SIGS >2 · WS ECB
jump       := PAIR TENOR? MNEMONIC? — order-flexible: "EURJPY 3M SMIL"
              and "SMIL EURJPY 3M" both parse; bare "EURJPY⏎" repoints
              the focused panel (with ⇧: the panel's whole link group)
search     := anything else → fuzzy across panels, pairs, commands,
              opportunities, blotter entries, assistant threads
```
`.` repeats the last command; `↑` recalls history; the parser is shared
with ASST so "open the eurjpy smile" in chat resolves to the same action.

### 5.3 Chord map (excerpt — KEYS panel ships the full searchable map)
```
Workspaces   Ctrl+1..9 switch · Ctrl+` mode switcher · Ctrl+S/Shift+S save
Panels       Alt+1..9 focus by badge · Ctrl+Tab MRU · Ctrl+\ split ·
             Ctrl+W close · Alt+A/B/C/D set link group · L cycle lens
Feed rows    j/k or ↑↓ move · Enter expand · I investigate · W watch ·
             B blotter · X dismiss · G go-to (fan-out)
Global       ⌘K command · F freshness inspector · N notifications ·
             F8 next window · ? = KEYS
```

---

## 6. Assistant-driven research workflows

### 6.1 Three surfaces, one Analyst
1. **OPPS** — proactive (§1). 2. **ASST** — conversational deep-dive.
3. **Inline ✦** — every chart, grid row, card, and blotter entry carries
an "ask" affordance that opens ASST pre-seeded with that exact artifact.

### 6.2 Ambient context (what the Analyst always sees)
Auto-attached to every ASST turn and every triage, rendered as a visible
context bar (never hidden — the trader must know what the model knows):
`mode:ECB · focus:SMIL EURJPY 3M · linkA:EURJPY/3M · positions:3 (vega
−42k) · alerts:2 WARN · packet:09:30`. Each chip is removable per-turn;
chips serialize the *rendered data*, not screenshots — numeric, citable.

### 6.3 Structured tasks (the workflows that aren't chat)
- **Investigate** (from a card or `I`): server-side tool loop with a
  fixed checklist — history percentile pull, model-agreement check,
  event-calendar scan, related-positions lookup, similar-episode search
  via the backtest panel's stored events — returning a structured brief:
  *finding / supporting / contradicting / what would invalidate /
  suggested expression*. Tools are read-only + bounded-compute; the loop
  is capped (≤8 tool calls) and the brief renders its tool trail.
- **Post-mortem** (blotter): when a trade closes, the Analyst drafts a
  post-mortem from the entry thesis (captured at `→ Blotter` time —
  the card's evidence is frozen into the blotter row) vs realized
  outcome; trader edits, saves; post-mortems are searchable and feed the
  morning brief ("you've faded JPY skew 4× this quarter, 3 winners").
- **Morning brief** (first open of the day, or `BRIEF`): overnight
  surface moves (Δ lens summary), feed deltas, positions vs moves, and
  the calendar — one card, 30-second read.
- **Promote to IDEA**: any assistant brief can be promoted to a standing
  idea card with its provenance intact.

### 6.4 Provenance as UI
Every number the Analyst emits is a hoverable chip → source path
(`packet.market.EURJPY.rr25.3M`, store query, or computed-from refs).
Server-side verifier rejects unverifiable numerics before they render
(regenerate with the violation named). Unverifiable-but-qualitative
claims render in a visually distinct "analyst judgment" style. This is
the chatbot-trust problem solved structurally, not by disclaimer.

### 6.5 Tool surface exposed to the Analyst (read-only, day one)
`get_packet · get_history(pair,tenor,field,window) · get_percentile ·
get_positions · get_blotter(filter) · get_events(window) ·
run_backtest_slice(signal,window) · get_surface(pair)` — all existing
engine calls; no write tools in v1 (the trader acts, the Analyst advises).

---

## 7. Revised panel inventory
`OPPS`* (hero) · `VHEAT`* (primary surface, 3 lenses; 3D as mode) ·
`RCHP`* · `RVSC`* · `SMIL` v2 (cone) · `TERM` v2 (cone) · `SIGS` ·
`IDEA` · `ASST` v2 (ambient bar, tasks) · `BLOT` v2 (thesis capture,
post-mortems) · `POSN` · `CARY` · `HLTH` (+ token budget) · `BTST` ·
`NOTF` · `KEYS`.   (* new this iteration)

## 8. Revised build phases
| Phase | Adds | Exit criterion |
|---|---|---|
| 0 | Tokens, shell, dock, command line + grammar, mode switcher (mock data) | Keyboard-only tour of 3 mock workspaces |
| 1 | Sidecar (read APIs + WS) · **Tier-1 observations** · OPPS (deterministic cards) · SIGS · HLTH | Live feed updates on cycle |
| 2 | **Claude day-one**: Tier-2 triage + ASST with ambient context + provenance verifier | Cited synthesis card from a live packet |
| 3 | VHEAT (3 lenses) · SMIL/TERM cones · RCHP · RVSC · link groups | %ile lens live across 9 pairs @60fps |
| 4 | BLOT (thesis capture) · POSN · post-mortem task · Investigate task | Card → trade → post-mortem round trip |
| 5 | Tauri multi-window, monitor roles, fingerprints, workspace persistence, event-aware modes | 3-monitor ECB-Day restore after reboot |
| 6 | Perf budgets, Alt-hints, KEYS, light theme, polish | CI gates green; keyboard coverage audit |

## 9. Open questions for next review
1. Dismissal reasons: free-text, picklist, or skip in v1? (Feeds future
   ranking; picklist recommended.)
2. Token budget ceiling/day for the Analyst (drives Haiku/Sonnet split)?
3. Should Invalidation events ("the one you didn't take") be on by
   default, or opt-in? (Powerful but psychologically loaded.)
4. Blotter: do paper and live trades share one table with a `kind` field
   (recommended, simplest migration story) or separate ledgers?
