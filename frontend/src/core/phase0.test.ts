/** Phase 0 contract tests. These lock the LOCKED DECISIONS in code:
 *  hard budget with triage reserve & carryover cap, dismissal cooldown
 *  with escalation override, invalidation-on-disappearance, order-flexible
 *  grammar, versioned workspace persistence.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { BASE_DAILY, CARRYOVER_CAP, COST, TRIAGE_RESERVE, freshState,
  remaining, rollover, spend } from "../core/budget/engine";
import { COOLDOWN_MS, applyCycle, band, emptyFeed, transition }
  from "../core/opportunities/feed";
import type { ConfidenceInputs, OpportunityCard }
  from "../core/opportunities/types";
import { completePair, parse } from "../core/grammar/parser";
import { buildHistory, detect, percentile, toCards, zscore }
  from "../mock/market";
import { DEFAULT_WORKSPACES, loadWorkspaces, saveWorkspaces }
  from "../core/workspace/types";

/* ------------------------------------------------------------ grammar */
describe("command grammar", () => {
  it("parses order-flexible tokens", () => {
    const a = parse("SMIL EURJPY 3M");
    const b = parse("eurjpy 3m smil");
    expect(a).toEqual(b);
    expect(a).toEqual({ kind: "open-panel", panel: "SMIL",
      pair: "EURJPY", tenor: "3M", zMin: undefined });
  });
  it("bare pair => repoint", () => {
    expect(parse("USDJPY")).toEqual(
      { kind: "repoint", pair: "USDJPY", tenor: undefined });
    expect(parse("USDJPY 1W")).toEqual(
      { kind: "repoint", pair: "USDJPY", tenor: "1W" });
  });
  it("z filter and workspace forms", () => {
    expect(parse("SIGS >2")).toMatchObject(
      { kind: "open-panel", panel: "SIGS", zMin: 2 });
    expect(parse("ws ecb")).toEqual(
      { kind: "workspace", mnemonic: "ECB" });
  });
  it("unresolvable text falls through to search", () => {
    expect(parse("why is the curve kinked").kind).toBe("search");
  });
  it("unique pair prefix completes", () => {
    expect(completePair("EURJ")).toBe("EURJPY");
    expect(completePair("EUR")).toBeNull();        // ambiguous
  });
});

/* ------------------------------------------------------------- budget */
describe("analyst budget (locked decision #2: HARD limits)", () => {
  it("spends and refuses at the hard ceiling", () => {
    let s = freshState("2026-06-11");
    for (let i = 0; i < BASE_DAILY; i++) {
      const r = spend(s, "triage", "2026-06-11");
      if (r.ok) s = r.state;
    }
    expect(remaining(s)).toBe(0);
    expect(spend(s, "triage", "2026-06-11").ok).toBe(false);
  });
  it("triage reserve blocks deep-dives, never triage", () => {
    let s = freshState("2026-06-11");
    // burn down to just above the reserve with deep-dives
    while (remaining(s) - COST.deep >= TRIAGE_RESERVE)
      s = spend(s, "deep", "2026-06-11").state;
    const deep = spend(s, "deep", "2026-06-11");
    expect(deep.ok).toBe(false);
    expect(deep.reason).toBe("reserve-protected");
    expect(spend(s, "triage", "2026-06-11").ok).toBe(true);
  });
  it("carryover is capped at 20% of base", () => {
    const s = freshState("2026-06-11");          // nothing used
    const next = rollover(s, "2026-06-12");
    expect(next.carryover).toBe(BASE_DAILY * CARRYOVER_CAP);
    expect(remaining(next)).toBe(BASE_DAILY * (1 + CARRYOVER_CAP));
  });
});

/* ------------------------------------------------------- confidence */
describe("confidence banding", () => {
  const base: ConfidenceInputs = { absZ: 3.0, persistenceCycles: 3,
    dataQualityOk: true, modelsAgree: true,
    backtestPrior: { hitRate: 0.61, n: 42 } };
  it("full evidence => ACTIONABLE", () => {
    expect(band(base)).toBe("ACTIONABLE");
  });
  it("data-quality flags can NEVER be actionable", () => {
    expect(band({ ...base, dataQualityOk: false })).toBe("SPECULATIVE");
  });
  it("thin evidence => SPECULATIVE", () => {
    expect(band({ absZ: 1.2, persistenceCycles: 1, dataQualityOk: true,
      modelsAgree: false })).toBe("SPECULATIVE");
  });
});

/* ------------------------------------------------------ feed lifecycle */
const mkCard = (over: Partial<OpportunityCard> = {}): OpportunityCard => ({
  id: "SKEW_STRETCH|EURJPY|3M", type: "SKEW_STRETCH", pair: "EURJPY",
  tenors: ["3M"], headline: "h", structure: "3M 25d RR",
  band: "WATCH",
  confidence: { absZ: 2, persistenceCycles: 1, dataQualityOk: true,
    modelsAgree: true },
  evidence: [], status: "new",
  createdAt: "2026-06-11T08:00:00Z", updatedAt: "2026-06-11T08:00:00Z",
  ...over,
});

describe("feed lifecycle", () => {
  it("dedup: re-detection updates, never duplicates", () => {
    let f = applyCycle(emptyFeed(), [mkCard()], "2026-06-11T08:00:00Z");
    f = applyCycle(f, [mkCard()], "2026-06-11T08:30:00Z");
    expect(Object.keys(f.cards)).toHaveLength(1);
    expect(f.cards[mkCard().id].createdAt).toBe("2026-06-11T08:00:00Z");
    expect(f.cards[mkCard().id].updatedAt).toBe("2026-06-11T08:30:00Z");
  });
  it("dismissed stays dismissed inside cooldown...", () => {
    let f = applyCycle(emptyFeed(), [mkCard()], "2026-06-11T08:00:00Z");
    f = transition(f, mkCard().id, "dismissed", "2026-06-11T08:05:00Z",
      { reason: "Too low conviction" });
    f = applyCycle(f, [mkCard()], "2026-06-11T09:00:00Z");
    expect(f.cards[mkCard().id].status).toBe("dismissed");
  });
  it("...but band ESCALATION overrides the cooldown", () => {
    let f = applyCycle(emptyFeed(), [mkCard()], "2026-06-11T08:00:00Z");
    f = transition(f, mkCard().id, "dismissed", "2026-06-11T08:05:00Z",
      { reason: "Timing not suitable" });
    f = applyCycle(f, [mkCard({ band: "ACTIONABLE" })],
      "2026-06-11T09:00:00Z");
    expect(f.cards[mkCard().id].status).toBe("new");
  });
  it("...and cooldown expiry resurrects", () => {
    let f = applyCycle(emptyFeed(), [mkCard()], "2026-06-11T08:00:00Z");
    f = transition(f, mkCard().id, "dismissed", "2026-06-11T08:05:00Z",
      { reason: "Not relevant" });
    const later = new Date(Date.parse("2026-06-11T08:05:00Z")
      + COOLDOWN_MS + 1000).toISOString();
    f = applyCycle(f, [mkCard()], later);
    expect(f.cards[mkCard().id].status).toBe("new");
  });
  it("disappearance without action => invalidated (decision #3)", () => {
    let f = applyCycle(emptyFeed(), [mkCard()], "2026-06-11T08:00:00Z");
    f = applyCycle(f, [], "2026-06-11T09:00:00Z");
    const c = f.cards[mkCard().id];
    expect(c.status).toBe("invalidated");
    expect(c.invalidation?.at).toBe("2026-06-11T09:00:00Z");
  });
  it("acted/watching are sticky through re-detection and disappearance", () => {
    let f = applyCycle(emptyFeed(), [mkCard()], "2026-06-11T08:00:00Z");
    f = transition(f, mkCard().id, "acted", "2026-06-11T08:10:00Z");
    f = applyCycle(f, [mkCard()], "2026-06-11T08:30:00Z");
    expect(f.cards[mkCard().id].status).toBe("acted");
    f = applyCycle(f, [], "2026-06-11T09:00:00Z");
    expect(f.cards[mkCard().id].status).toBe("acted");   // never invalidated
  });
  it("ranking: actionable first, then by |z|", () => {
    const weak = mkCard({ id: "A|EURUSD|1M", band: "SPECULATIVE",
      confidence: { absZ: 4, persistenceCycles: 1, dataQualityOk: true,
        modelsAgree: false } });
    const strong = mkCard({ id: "B|USDJPY|3M", band: "ACTIONABLE",
      confidence: { absZ: 2.6, persistenceCycles: 3, dataQualityOk: true,
        modelsAgree: true } });
    const f = applyCycle(emptyFeed(), [weak, strong], "2026-06-11T08:00:00Z");
    expect(f.order[0]).toBe("B|USDJPY|3M");
  });
});

/* ----------------------------------------------------- mock detectors */
describe("deterministic detectors on mock data", () => {
  const hist = buildHistory(2026);
  it("seeded build is deterministic", () => {
    const a = buildHistory(7)["EURUSD"]["3M"].at(-1)!.atm;
    const b = buildHistory(7)["EURUSD"]["3M"].at(-1)!.atm;
    expect(a).toBe(b);
  });
  it("planted dislocations are detected with correct types", () => {
    const obs = detect(hist, "2026-06-11T08:00:00Z");
    const types = (p: string, t: string) => obs
      .filter((o) => o.pair === p && o.tenor === t).map((o) => o.type);
    expect(types("EURJPY", "3M")).toContain("SKEW_STRETCH");
    expect(types("USDJPY", "9M")).toContain("TERM_KINK");
    expect(obs.filter((o) => o.pair === "GBPUSD" && o.tenor === "1M")
      .some((o) => ["SURFACE_MOVE", "PERCENTILE_BREACH"]
        .includes(o.type))).toBe(true);
  });
  it("cards cluster by (type, pair, tenor) and carry evidence", () => {
    const cards = toCards(detect(hist, "x"), "x");
    const ids = cards.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);    // unique == clustered
    for (const c of cards) expect(c.evidence.length).toBeGreaterThan(0);
  });
  it("percentile/zscore sanity", () => {
    expect(percentile([1, 2, 3, 4], 5)).toBe(100);
    expect(percentile([1, 2, 3, 4], 0)).toBe(0);
    expect(zscore([1, 1, 1], 1)).toBe(0);
  });
});

/* -------------------------------------------------------- persistence */
describe("workspace persistence (versioned, migration-friendly)", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    (globalThis as any).localStorage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    };
  });
  it("round-trips and survives a bad blob", () => {
    const ws = [...DEFAULT_WORKSPACES];
    ws[0] = { ...ws[0], assistantBrief: "edited brief" };
    saveWorkspaces(ws);
    expect(loadWorkspaces()[0].assistantBrief).toBe("edited brief");
    (globalThis as any).localStorage.setItem(
      "volwatch.workspaces.v1", "{corrupt");
    expect(loadWorkspaces()).toEqual(DEFAULT_WORKSPACES);
  });
  it("unknown schema version falls back to defaults", () => {
    (globalThis as any).localStorage.setItem("volwatch.workspaces.v1",
      JSON.stringify([{ ...DEFAULT_WORKSPACES[0], schemaVersion: 99 }]));
    expect(loadWorkspaces()).toEqual(DEFAULT_WORKSPACES);
  });
  it("ships the five modes with briefs and alert profiles", () => {
    expect(DEFAULT_WORKSPACES.map((w) => w.mnemonic))
      .toEqual(["MORN", "ECB", "NFP", "G10RV", "RISK"]);
    for (const w of DEFAULT_WORKSPACES) {
      expect(w.assistantBrief.length).toBeGreaterThan(10);
      expect(w.alertProfile.toastMin).toBeDefined();
    }
  });
});
