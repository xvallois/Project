/** Decision ledger store, backed by the sidecar's SQLite blotter
 *  (ADR-0006: one blotter). The store keeps the Phase-0 interface
 *  (rows/add/close) so panels are unchanged; writes are optimistic and
 *  the server's rows are authoritative on the next refresh. With no
 *  sidecar (mock-only shell) entries live in memory for the session. */
import { create } from "zustand";
import type { BlotterEntry, BlotterKind, BlotterStatus }
  from "../core/blotter/schema";
import { getBlotter, postBlotter, postBlotterClose,
  type ServerBlotterRow } from "../api/client";

const fromServer = (r: ServerBlotterRow): BlotterEntry => ({
  id: r.id, kind: r.kind as BlotterKind, status: r.status as BlotterStatus,
  pair: r.pair as BlotterEntry["pair"], structure: r.structure,
  direction: r.direction,
  linkedOpportunityId: r.linked_opportunity_id ?? undefined,
  entryThesis: r.entry_thesis ?? undefined, size: r.size ?? undefined,
  pnlVolPts: r.pnl_volpts ?? undefined, pnlCcy: r.pnl_ccy ?? undefined,
  notes: r.notes ?? undefined, postMortem: r.post_mortem ?? undefined,
  openedAt: r.opened_at, closedAt: r.closed_at ?? undefined,
});

interface BlotterStore {
  rows: BlotterEntry[];
  refresh: () => void;
  add: (e: Omit<BlotterEntry, "id" | "openedAt">) => void;
  close: (id: string, pnlVolPts: number, notes: string) => void;
}
export const useBlotter = create<BlotterStore>((set, get) => ({
  rows: [],
  refresh: () => {
    getBlotter().then((rows) => set({ rows: rows.map(fromServer) }))
      .catch(() => undefined);            // serverless: keep local rows
  },
  add: (e) => {
    set({ rows: [{ ...e, id: crypto.randomUUID(),
      openedAt: new Date().toISOString() }, ...get().rows] });
    postBlotter({ kind: e.kind, status: e.status, pair: e.pair,
      structure: e.structure, direction: e.direction,
      linked_opportunity_id: e.linkedOpportunityId,
      entry_thesis: e.entryThesis, size: e.size })
      .then(() => get().refresh()).catch(() => undefined);
  },
  close: (id, pnlVolPts, notes) => {
    set({ rows: get().rows.map((r) => r.id === id
      ? { ...r, status: "closed" as const, pnlVolPts, notes,
          closedAt: new Date().toISOString() } : r) });
    postBlotterClose(id, pnlVolPts, notes)
      .then(() => get().refresh()).catch(() => undefined);
  },
}));
