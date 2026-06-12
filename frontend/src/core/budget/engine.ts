/** Analyst budget engine (locked decision #2): HARD daily budget.
 *
 *  - 100 units/day; Haiku triage 1u, Sonnet 3u, Opus deep-dive 8-12u
 *  - feed triage must never block: a dedicated reserve is carved out so
 *    deep-dives cannot starve the cycle triage
 *  - daily reset with carry-over capped at 20% of base
 *  - spend() is the ONLY mutation; refusal is a typed result, not a throw
 *    (the UI renders refusals; the system never silently degrades)
 */
export type Tier = "triage" | "analysis" | "deep";

export const BASE_DAILY = 100;
export const CARRYOVER_CAP = 0.2;          // of BASE_DAILY
export const TRIAGE_RESERVE = 12;          // units/day deep-dives can't touch
export const COST: Record<Tier, number> = { triage: 1, analysis: 3, deep: 10 };

export interface BudgetState {
  date: string;            // ISO day
  used: number;
  carryover: number;       // granted at last reset, already inside `total`
}

export interface SpendResult {
  ok: boolean;
  state: BudgetState;
  reason?: "insufficient" | "reserve-protected";
}

export const totalFor = (s: BudgetState) => BASE_DAILY + s.carryover;
export const remaining = (s: BudgetState) => totalFor(s) - s.used;

export function freshState(date: string, carryover = 0): BudgetState {
  return { date, used: 0,
    carryover: Math.min(carryover, BASE_DAILY * CARRYOVER_CAP) };
}

/** Roll to a new day if needed; unused units carry over, capped. */
export function rollover(s: BudgetState, today: string): BudgetState {
  if (s.date === today) return s;
  return freshState(today, remaining(s));
}

export function spend(s: BudgetState, tier: Tier, today: string,
                      units = COST[tier]): SpendResult {
  const cur = rollover(s, today);
  const rem = remaining(cur);
  if (units > rem)
    return { ok: false, state: cur, reason: "insufficient" };
  // non-triage spends may not dig into the triage reserve
  if (tier !== "triage" && rem - units < TRIAGE_RESERVE)
    return { ok: false, state: cur, reason: "reserve-protected" };
  return { ok: true, state: { ...cur, used: cur.used + units } };
}
