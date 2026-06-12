/** Live-engine store: server cards + health over WS, mock fallback. */
import { create } from "zustand";
import { connectWs, getFeed, getHealth, postBlotter, postInvestigate,
  postTransition, type ResearchBrief, type ServerCard, type WsEnvelope }
  from "../api/client";
import { useWorkspaces } from "./stores";

interface EngineStore {
  connected: boolean | null;        // null = connecting
  cards: ServerCard[];
  health: any;
  brief: ResearchBrief | null;      // latest research brief
  investigating: string | null;     // card id in flight
  investigate: (id: string, depth?: "investigate" | "deep") => void;
  start: () => void;
  transition: (id: string, status: string, reason?: string,
    note?: string) => void;
  toBlotter: (c: ServerCard) => void;
}
export const useEngine = create<EngineStore>((set, get) => ({
  connected: null, cards: [], health: {}, brief: null, investigating: null,
  investigate: (id, depth = "investigate") => {
    const ws = useWorkspaces.getState();
    const active = ws.all.find((w) => w.id === ws.activeId);
    set({ investigating: id });
    ws.dockApi?.openPanel({ kind: "ASST" });
    postInvestigate(id, depth, active?.assistantBrief ?? "")
      .then((brief) => set({ brief, investigating: null }))
      .catch(() => set({ investigating: null }));
  },
  start: () => {
    getFeed().then((cards) => set({ cards, connected: true }))
      .catch(() => set({ connected: false }));
    getHealth().then((health) => set({ health })).catch(() => undefined);
    connectWs((env: WsEnvelope) => {
      if (env.topic === "feed") set({ cards: env.data.cards });
      if (env.topic === "health") set({ health: env.data });
      if (env.topic === "brief") set({ brief: env.data });
    }, (up: boolean) => set({ connected: up }));
  },
  transition: (id, status, reason, note) => {
    // optimistic; server echoes authoritative state on the next feed delta
    set({ cards: get().cards.map((c) => c.id === id
      ? { ...c, status, dismissal: reason
          ? { reason, note, at: new Date().toISOString() } : c.dismissal }
      : c) });
    postTransition(id, status, reason, note).catch(() => undefined);
  },
  toBlotter: (c) => {
    postBlotter({ kind: "idea", status: "open", pair: c.pair,
      structure: c.structure, direction: c.type.toLowerCase(),
      linked_opportunity_id: c.id,
      entry_thesis: `${c.headline} — ` + c.evidence
        .map((e) => `${e.label}=${e.value} [${e.provenance}]`).join("; "),
    }).catch(() => undefined);
    get().transition(c.id, "acted");
  },
}));
