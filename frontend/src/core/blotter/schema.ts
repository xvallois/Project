/** Unified decision ledger (locked decision #4): ONE table, the value is
 * in the lifecycle. `kind` distinguishes idea/paper/live; never split.
 * The DDL below is the SQLite source of truth the sidecar will run in
 * Phase 4 (Alembic-managed); the TS type mirrors it 1:1.
 */
import type { Pair } from "../types";

export type BlotterKind = "idea" | "paper" | "live" | "invalidated";
export type BlotterStatus = "open" | "closed" | "stopped" | "expired";

export interface BlotterEntry {
  id: string;
  kind: BlotterKind;
  status: BlotterStatus;
  pair: Pair;
  structure: string;             // "3M 25d RR", "1W straddle over ECB"
  direction: string;             // sell_vol / buy_skew / ...
  linkedOpportunityId?: string;  // provenance back to the card
  entryThesis?: string;          // frozen card evidence at entry time
  size?: string;                 // free-form in Phase 0 ("10k vega")
  pnlVolPts?: number;
  pnlCcy?: number;
  notes?: string;
  postMortem?: string;           // Phase 4: Analyst-drafted, trader-edited
  openedAt: string;
  closedAt?: string;
}

export const BLOTTER_DDL = `
CREATE TABLE IF NOT EXISTS blotter (
  id                     TEXT PRIMARY KEY,
  kind                   TEXT NOT NULL CHECK (kind IN
                           ('idea','paper','live','invalidated')),
  status                 TEXT NOT NULL CHECK (status IN
                           ('open','closed','stopped','expired')),
  pair                   TEXT NOT NULL,
  structure              TEXT NOT NULL,
  direction              TEXT NOT NULL,
  linked_opportunity_id  TEXT,
  entry_thesis           TEXT,
  size                   TEXT,
  pnl_volpts             REAL,
  pnl_ccy                REAL,
  notes                  TEXT,
  post_mortem            TEXT,
  opened_at              TEXT NOT NULL,
  closed_at              TEXT,
  schema_version         INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_blotter_status ON blotter(status, kind);
CREATE INDEX IF NOT EXISTS ix_blotter_opp ON blotter(linked_opportunity_id);
`;
