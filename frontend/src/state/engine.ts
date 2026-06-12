/** Live-engine store: server cards + health over WS, mock fallback. */
import { create } from "zustand";
import { connectWs, getFeed, getHealth, postBlotter, postTransition,
  type ServerCard, type WsEnvelope } from "../api/client";

interface EngineStore {
  connected: boolean | null;        // null = connecting
  cards: ServerCard[];
  health: any;
  start: () => void;
  transition: (id: string, status: string, reason?: string,
    note?: string) => void;
  toBlotter: (c: ServerCard) => void;
}
export const useEngine = create<EngineStore>((set, get) => ({
  connected: null, cards: [], health: {},
  start: () => {
    getFeed().then((cards) => set({ cards, connected: true }))
      .catch(() => set({ connected: false }));
    getHealth().then((health) => set({ health })).catch(() => undefined);
    connectWs((env: WsEnvelope) => {
      if (env.topic === "feed") set({ cards: env.data.cards });
      if (env.topic === "health") set({ health: env.data });
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
