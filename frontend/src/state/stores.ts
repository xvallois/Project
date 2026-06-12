/** Application stores. One store per domain; panels subscribe with
 * fine-grained selectors so a link-group repoint re-renders only the
 * affected panels (perf budget §8 of the design).
 */
import { create } from "zustand";

import { COST, freshState, remaining, spend, totalFor, type BudgetState,
  type Tier } from "../core/budget/engine";
import { applyCycle, emptyFeed, transition, type FeedState }
  from "../core/opportunities/feed";
import type { DismissalReason } from "../core/opportunities/types";
import type { LinkContext, LinkGroupId, Pair, PanelKind, Tenor }
  from "../core/types";
import { buildHistory, detect, toCards, type History } from "../mock/market";
import { loadWorkspaces, saveWorkspaces, type Workspace }
  from "../core/workspace/types";

const today = () => new Date().toISOString().slice(0, 10);
const nowIso = () => new Date().toISOString();

// ----------------------------------------------------------------- market
interface MarketStore {
  history: History;
  asof: string;
}
export const useMarket = create<MarketStore>(() => ({
  history: buildHistory(2026),
  asof: nowIso(),
}));

// --------------------------------------------------------------------- ui
interface UiStore {
  linkGroups: Partial<Record<LinkGroupId, LinkContext>>;
  focusedPanel: string | null;            // dockview panel id
  paletteOpen: boolean;
  selectedCard: string | null;
  setSelectedCard: (id: string | null) => void;
  setLink: (g: LinkGroupId, ctx: Partial<LinkContext>) => void;
  setFocused: (id: string | null) => void;
  setPalette: (open: boolean) => void;
}
export const useUi = create<UiStore>((set) => ({
  linkGroups: { A: { pair: "EURJPY", tenor: "3M" } },
  focusedPanel: null,
  paletteOpen: false,
  selectedCard: null,
  setSelectedCard: (id) => set({ selectedCard: id }),
  setLink: (g, ctx) => set((s) => ({
    linkGroups: { ...s.linkGroups,
      [g]: { ...(s.linkGroups[g] ?? { pair: "EURUSD", tenor: "3M" }),
        ...ctx } } })),
  setFocused: (id) => set({ focusedPanel: id }),
  setPalette: (open) => set({ paletteOpen: open }),
}));

// ------------------------------------------------------------------- feed
interface FeedStore {
  feed: FeedState;
  runCycle: () => void;
  act: (id: string, status: "seen" | "watching" | "acted") => void;
  dismiss: (id: string, reason: DismissalReason, note?: string) => void;
}
export const useFeed = create<FeedStore>((set, get) => ({
  feed: applyCycle(emptyFeed(),
    toCards(detect(useMarket.getState().history, nowIso()), nowIso(),
      { "SKEW_STRETCH|EURJPY|3M": 3 }),       // mock persistence
    nowIso()),
  runCycle: () => {
    const obs = detect(useMarket.getState().history, nowIso());
    set({ feed: applyCycle(get().feed, toCards(obs, nowIso()), nowIso()) });
    useBudget.getState().spendTier("triage");  // a cycle costs 1 unit
  },
  act: (id, status) =>
    set({ feed: transition(get().feed, id, status, nowIso()) }),
  dismiss: (id, reason, note) =>
    set({ feed: transition(get().feed, id, "dismissed", nowIso(),
      { reason, note }) }),
}));

// ----------------------------------------------------------------- budget
interface BudgetStore {
  state: BudgetState;
  spendTier: (t: Tier, units?: number) => boolean;
  refusedAt: string | null;               // last refusal, for the meter
}
export const useBudget = create<BudgetStore>((set, get) => ({
  state: freshState(today()),
  refusedAt: null,
  spendTier: (t, units = COST[t]) => {
    const r = spend(get().state, t, today(), units);
    set({ state: r.state, refusedAt: r.ok ? get().refusedAt : nowIso() });
    return r.ok;
  },
}));
export const budgetPct = (s: BudgetState) =>
  Math.round((100 * remaining(s)) / totalFor(s));

// ------------------------------------------------------------- workspaces
export interface OpenPanelRequest {
  kind: PanelKind; pair?: Pair; tenor?: Tenor; zMin?: number;
}
interface WorkspaceStore {
  all: Workspace[];
  activeId: string;
  dirty: boolean;
  /** set by DockHost: imperative dock control for palette/commands */
  dockApi: {
    openPanel: (req: OpenPanelRequest) => void;
    toJSON: () => object;
    fromJSON: (layout: object | null) => void;
  } | null;
  setDockApi: (api: WorkspaceStore["dockApi"]) => void;
  markDirty: () => void;
  switchTo: (mnemonic: string) => void;
  saveActive: () => void;
}
export const useWorkspaces = create<WorkspaceStore>((set, get) => ({
  all: loadWorkspaces(),
  activeId: "morn",
  dirty: false,
  dockApi: null,
  setDockApi: (api) => set({ dockApi: api }),
  markDirty: () => set({ dirty: true }),
  switchTo: (mnemonic) => {
    const { all, activeId, dockApi } = get();
    const target = all.find(
      (w) => w.mnemonic === mnemonic.toUpperCase());
    if (!target || !dockApi) return;
    // auto-snapshot the outgoing layout (design §3.4)
    const updated = all.map((w) =>
      w.id === activeId ? { ...w, layout: dockApi.toJSON() } : w);
    saveWorkspaces(updated);
    set({ all: updated, activeId: target.id, dirty: false });
    dockApi.fromJSON(target.layout);
    // apply the mode's link groups
    const ui = useUi.getState();
    for (const [g, ctx] of Object.entries(target.linkGroups))
      ui.setLink(g as LinkGroupId, ctx);
  },
  saveActive: () => {
    const { all, activeId, dockApi } = get();
    if (!dockApi) return;
    const updated = all.map((w) =>
      w.id === activeId
        ? { ...w, layout: dockApi.toJSON(),
            linkGroups: useUi.getState().linkGroups }
        : w);
    saveWorkspaces(updated);
    set({ all: updated, dirty: false });
  },
}));
