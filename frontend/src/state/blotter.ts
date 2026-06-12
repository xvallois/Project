/** Decision ledger store: localStorage in Phase 0, sidecar SQLite later.
 *  The store API is already shaped like the future REST calls. */
import { create } from "zustand";
import type { BlotterEntry } from "../core/blotter/schema";

const KEY = "volwatch.blotter.v1";
const load = (): BlotterEntry[] => {
  try { return JSON.parse(localStorage.getItem(KEY) ?? "[]"); }
  catch { return []; }
};
const persist = (rows: BlotterEntry[]) =>
  localStorage.setItem(KEY, JSON.stringify(rows));

interface BlotterStore {
  rows: BlotterEntry[];
  add: (e: Omit<BlotterEntry, "id" | "openedAt">) => void;
  close: (id: string, pnlVolPts: number, notes: string) => void;
}
export const useBlotter = create<BlotterStore>((set, get) => ({
  rows: load(),
  add: (e) => {
    const rows = [{ ...e, id: crypto.randomUUID(),
      openedAt: new Date().toISOString() }, ...get().rows];
    persist(rows); set({ rows });
  },
  close: (id, pnlVolPts, notes) => {
    const rows = get().rows.map((r) => r.id === id
      ? { ...r, status: "closed" as const, pnlVolPts, notes,
          closedAt: new Date().toISOString() } : r);
    persist(rows); set({ rows });
  },
}));
