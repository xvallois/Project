/** Shared domain vocabulary. Mirrors the Python engine's models. */
export const PAIRS = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD",
  "NZDUSD","EURJPY","EURGBP"] as const;
export type Pair = (typeof PAIRS)[number];

export const TENORS = ["ON","1W","2W","1M","2M","3M","6M","9M","1Y"] as const;
export type Tenor = (typeof TENORS)[number];

export const NODES = ["10P","25P","ATM","25C","10C"] as const;
export type Node = (typeof NODES)[number];

export type LinkGroupId = "A" | "B" | "C" | "D";
export interface LinkContext { pair: Pair; tenor: Tenor }

export const PANEL_KINDS = ["OPPS","VHEAT","SMIL","TERM","RCHP","RVSC",
  "SIGS","IDEA","ASST","BLOT","POSN","CARY","HLTH","BTST","KEYS"] as const;
export type PanelKind = (typeof PANEL_KINDS)[number];

/** Mnemonics implemented in Phase 0. Others parse but report "phase N". */
export const PHASE0_PANELS: PanelKind[] = ["OPPS","ASST","VHEAT","SMIL",
  "TERM","RCHP","SIGS","BLOT","HLTH","KEYS"];
