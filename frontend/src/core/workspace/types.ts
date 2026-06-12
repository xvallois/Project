/** Workspace = MODE: layout + link groups + filters + alert profile +
 * standing assistant brief (design v1.1 §3). Persisted versioned;
 * localStorage in Phase 0, SQLite via sidecar from Phase 4.
 */
import type { Band } from "../opportunities/types";
import type { LinkContext, LinkGroupId, Pair } from "../types";

export type Severity = "info" | "warn" | "crit";

export interface AlertProfile {
  toastMin: Severity;
  suppressInvalidationBelow?: Band;   // decision #3: category suppression
  pairs?: Pair[];                     // empty/undefined = all
}

export interface Workspace {
  id: string;
  name: string;
  mnemonic: string;                   // WS <mnemonic>
  layout: object | null;              // dockview api.toJSON()
  linkGroups: Partial<Record<LinkGroupId, LinkContext>>;
  filters: { oppsBandMin: Band; sigsZMin: number; pairs?: Pair[] };
  alertProfile: AlertProfile;
  assistantBrief: string;             // standing instructions (Phase 2 use)
  schemaVersion: 1;
}

export const DEFAULT_WORKSPACES: Workspace[] = [
  { id: "morn", name: "Morning Vol Check", mnemonic: "MORN", layout: null,
    linkGroups: { A: { pair: "EURJPY", tenor: "3M" } },
    filters: { oppsBandMin: "WATCH", sigsZMin: 1.5 },
    alertProfile: { toastMin: "warn" },
    assistantBrief: "Summarize overnight surface moves first; flag anything that crossed p95.",
    schemaVersion: 1 },
  { id: "ecb", name: "ECB Day", mnemonic: "ECB", layout: null,
    linkGroups: { A: { pair: "EURUSD", tenor: "1W" },
                  B: { pair: "EURJPY", tenor: "1W" } },
    filters: { oppsBandMin: "SPECULATIVE", sigsZMin: 1.0,
               pairs: ["EURUSD", "EURJPY", "EURGBP"] },
    alertProfile: { toastMin: "info", pairs: ["EURUSD","EURJPY","EURGBP"] },
    assistantBrief: "Prioritize EUR event pricing vs delivered history; track the 1W bucket through the print.",
    schemaVersion: 1 },
  { id: "nfp", name: "NFP Mode", mnemonic: "NFP", layout: null,
    linkGroups: { A: { pair: "USDJPY", tenor: "1W" } },
    filters: { oppsBandMin: "SPECULATIVE", sigsZMin: 1.0,
               pairs: ["EURUSD","USDJPY","GBPUSD","USDCAD"] },
    alertProfile: { toastMin: "info" },
    assistantBrief: "USD event premium vs NFP delivered; watch ON->1W fwd vol.",
    schemaVersion: 1 },
  { id: "g10rv", name: "G10 Relative Value", mnemonic: "G10RV", layout: null,
    linkGroups: { A: { pair: "EURUSD", tenor: "3M" },
                  B: { pair: "GBPUSD", tenor: "3M" } },
    filters: { oppsBandMin: "WATCH", sigsZMin: 1.5 },
    alertProfile: { toastMin: "warn",
                    suppressInvalidationBelow: "WATCH" },
    assistantBrief: "Rank cross-pair and triangle dislocations; ignore sub-WATCH carry items.",
    schemaVersion: 1 },
  { id: "risk", name: "Risk Management", mnemonic: "RISK", layout: null,
    linkGroups: {},
    filters: { oppsBandMin: "ACTIONABLE", sigsZMin: 2.0 },
    alertProfile: { toastMin: "warn" },
    assistantBrief: "Relate every new alert to open positions; flag concentration.",
    schemaVersion: 1 },
];

const KEY = "volwatch.workspaces.v1";

export function loadWorkspaces(): Workspace[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT_WORKSPACES;
    const parsed = JSON.parse(raw) as Workspace[];
    return parsed.every((w) => w.schemaVersion === 1)
      ? parsed : DEFAULT_WORKSPACES;
  } catch { return DEFAULT_WORKSPACES; }
}

export function saveWorkspaces(ws: Workspace[]): void {
  localStorage.setItem(KEY, JSON.stringify(ws));
}
