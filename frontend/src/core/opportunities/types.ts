import type { Pair, Tenor } from "../types";

export type ObservationType = "PERCENTILE_BREACH" | "SURFACE_MOVE"
  | "TERM_KINK" | "SKEW_STRETCH" | "REGIME_SHIFT" | "EVENT_PRICING";

export interface Observation {
  id: string;
  type: ObservationType;
  pair: Pair;
  tenor?: Tenor;
  node?: string;
  metric: string;            // e.g. "rr25"
  value: number;
  percentile?: number;       // 0..100 vs own history
  zscore?: number;
  evidence: Record<string, number | string>;   // numeric, sourced
  asof: string;
}

export type Band = "SPECULATIVE" | "WATCH" | "ACTIONABLE";
export type CardStatus = "new" | "seen" | "watching" | "acted"
  | "dismissed" | "invalidated" | "expired";

/** Locked decision #1: controlled picklist + optional note. */
export const DISMISSAL_REASONS = ["Not relevant","Already priced in",
  "Too low conviction","Data quality issue","Wrong regime",
  "Redundant signal","Timing not suitable"] as const;
export type DismissalReason = (typeof DISMISSAL_REASONS)[number];

export interface ConfidenceInputs {
  absZ: number;
  persistenceCycles: number;
  dataQualityOk: boolean;
  modelsAgree: boolean;        // SABR/SSVI divergence inside envelope
  backtestPrior?: { hitRate: number; n: number };
}

export interface OpportunityCard {
  id: string;                  // dedup key: type|pair|structure
  type: ObservationType;
  pair: Pair;
  tenors: Tenor[];
  headline: string;
  structure: string;
  band: Band;
  confidence: ConfidenceInputs;
  evidence: Observation[];
  whyNow?: string;             // Tier-2 only (Phase 2+); absent = deterministic
  status: CardStatus;
  createdAt: string;
  updatedAt: string;
  dismissal?: { reason: DismissalReason; note?: string; at: string };
  invalidation?: { at: string; outcome: string; missedVolPts?: number };
}
