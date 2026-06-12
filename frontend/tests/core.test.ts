/** Phase 0 logic tests. The UI renders these modules; if these are right,
 * the UI can only be cosmetically wrong. */
import { describe, expect, it } from "vitest";

import { completePair, parse } from "../src/core/grammar/parser";
import { BASE_DAILY, COST, TRIAGE_RESERVE, freshState, remaining,
  rollover, spend } from "../src/core/budget/engine";
import { applyCycle, band, emptyFeed, transition }
  from "../src/core/opportunities/feed";
import type { OpportunityCard } from "../src/core/opportunities/types";
import { buildHistory, detect, percentile, toCards, zscore }
  from "../src/mock/market";
import { DEFAULT_WORKSPACES } from "../src/core/workspace/types";
import { BLOTTER_DDL } from "../src/core/blotter/schema";

const NOW = "2026-06-11T09:30:00Z";

// ---------------------------------------------------------------- grammar
describe("command grammar", () => {
  it("is order-flexible", () => {
    const a = parse("SMIL EURJPY 3M");
    const b = parse("eurjpy 3m smil");
    expect(a).toEqual(b);
    expect(a).toEqual({ kind: "open-panel", panel: "SMIL",
      pair: "EURJPY", tenor: "3M", zMin: undefined });
  });
  it("bare pair repoints", () => {
    expect(parse("USDJPY")).toEqual({ kind: "repoint", pair: "USDJPY",
      tenor: undefined });
    expect(parse("USDJPY 1W")).toMatchObject({ kind: "repoint",
      tenor: "1W" });
  });
  it("z filters and workspaces parse", () => {
    expect(parse("SIGS >2")).toMatchObject({ kind: "open-panel",
      panel: "SIGS", zMin: 2 });
    expect(parse("ws ecb")).toEqual({ kind: "workspace", mnemonic: "ECB" });
  });
  it("falls through to search", () => {
    expect(parse("why is the curve kinked"))
      .toMatchObject({ kind: "search" });
  });
  it("completes unique pair prefixes only", () => {
    expect(completePair("EURJ")).toBe("EURJPY");
    expect(completePair("EUR")).toBeNull();    // EURUSD/EURJPY/EURGBP
  });
});

// ---------------------------------------------------------------- budget
describe("budget engine (hard limits)", () => {
  const D1 = "2026-06-11", D2 = "2026-06-12";
  it("spends by tier and refuses when insufficient", () => {
    let s = freshState(D1);
    const r1 = spend(s, "deep", D1);
    expect(r1.ok).toBe(true);
    s = r1.state;
    expect(s.used).toBe(COST.deep);
    // burn everything except the reserve via analysis spends
    while (spend(s, "analysis", D1).ok) s = spend(s, "analysis", D1).state;
    const refusal = spend(s, "deep", D1);
    expect(refusal.ok).toBe(false);
  });
  it("triage reserve protects the feed from deep-dives", () => {
    let s = freshState(D1);
    // burn non-triage spends down to the reserve boundary
    while (spend(s, "deep", D1).ok) s = spend(s, "deep", D1).state;
    while (spend(s, "analysis", D1).ok)
      s = spend(s, "analysis", D1).state;
    const blocked = spend(s, "analysis", D1);
    expect(blocked.ok).toBe(false);
    expect(blocked.reason).toBe("reserve-protected");
    expect(remaining(s)).toBeGreaterThanOrEqual(TRIAGE_RESERVE);
    // but triage still works down to zero
    let triages = 0;
    while (spend(s, "triage", D1).ok) { s = spend(s, "triage", D1).state;
      triages++; }
    expect(triages).toBeGreaterThanOrEqual(TRIAGE_RESERVE);
    expect(remaining(s)).toBe(0);
  });
  it("carries over at most 20% on rollover", () => {
    const s = freshState(D1);                  // 100 unused
    const rolled = rollover(s, D2);
    expect(rolled.carryover).toBe(BASE_DAILY * 0.2);
    expect(remaining(rolled)).toBe(120);
  });
  it("no carryover when fully spent", () => {
    let s = freshState(D1);
    while (spend(s, "triage", D1).ok) s = spend(s, "triage", D1).state;
    expect(rollover(s, D2).carryover).toBe(0);
  });
});

// ------------------------------------------------------------ confidence
describe("confidence banding", () => {
  const base = { absZ: 3, persistenceCycles: 3, dataQualityOk: true,
    modelsAgree: true };
  it("never actionable on flagged data", () => {
    expect(band({ ...base, dataQualityOk: false })).toBe("SPECULATIVE");
  });
  it("strong multi-factor evidence is actionable", () => {
    expect(band(base)).toBe("ACTIONABLE");
  });
  it("thin evidence stays speculative", () => {
    expect(band({ absZ: 1.2, persistenceCycles: 1, dataQualityOk: true,
      modelsAgree: false })).toBe("SPECULATIVE");
  });
});

// ------------------------------------------------------------------ feed
function card(id: string, over: Partial<OpportunityCard> = {}):
    OpportunityCard {
  return { id, type: "SKEW_STRETCH", pair: "EURJPY", tenors: ["3M"],
    headline: "h", structure: "s", band: "WATCH",
    confidence: { absZ: 2, persistenceCycles: 1, dataQualityOk: true,
      modelsAgree: true },
    evidence: [], status: "new", createdAt: NOW, updatedAt: NOW, ...over };
}

describe("feed lifecycle", () => {
  it("dedups by id and preserves createdAt", () => {
    let f = applyCycle(emptyFeed(), [card("k1")], NOW);
    f = applyCycle(f, [card("k1", { headline: "updated" })],
      "2026-06-11T10:00:00Z");
    expect(Object.keys(f.cards)).toHaveLength(1);
    expect(f.cards.k1.createdAt).toBe(NOW);
    expect(f.cards.k1.headline).toBe("updated");
  });
  it("disappearance without action invalidates (decision #3)", () => {
    let f = applyCycle(emptyFeed(), [card("k1")], NOW);
    f = applyCycle(f, [], "2026-06-11T10:00:00Z");
    expect(f.cards.k1.status).toBe("invalidated");
    expect(f.cards.k1.invalidation?.outcome).toContain("without action");
  });
  it("dismissal cooldown holds unless band escalates", () => {
    let f = applyCycle(emptyFeed(), [card("k1")], NOW);
    f = transition(f, "k1", "dismissed", NOW,
      { reason: "Too low conviction" });
    // same band, 1h later -> stays dismissed
    f = applyCycle(f, [card("k1")], "2026-06-11T10:30:00Z");
    expect(f.cards.k1.status).toBe("dismissed");
    // escalation to ACTIONABLE -> returns
    f = applyCycle(f, [card("k1", { band: "ACTIONABLE" })],
      "2026-06-11T11:00:00Z");
    expect(f.cards.k1.status).toBe("new");
  });
  it("watching is sticky across cycles", () => {
    let f = applyCycle(emptyFeed(), [card("k1")], NOW);
    f = transition(f, "k1", "watching", NOW);
    f = applyCycle(f, [card("k1")], "2026-06-11T10:00:00Z");
    expect(f.cards.k1.status).toBe("watching");
  });
  it("ranks live cards by band then z", () => {
    const f = applyCycle(emptyFeed(), [
      card("a", { band: "WATCH",
        confidence: { absZ: 9, persistenceCycles: 1, dataQualityOk: true,
          modelsAgree: true } }),
      card("b", { band: "ACTIONABLE" }),
    ], NOW);
    expect(f.order[0]).toBe("b");
  });
});

// ------------------------------------------------------------- detectors
describe("deterministic detectors on seeded mock", () => {
  const hist = buildHistory(2026);
  const obs = detect(hist, NOW);
  it("finds the planted dislocations", () => {
    const types = (p: string, t: string) =>
      obs.filter((o) => o.pair === p && o.tenor === t).map((o) => o.type);
    expect(types("EURJPY", "3M")).toContain("SKEW_STRETCH");
    expect(types("USDJPY", "9M")).toContain("TERM_KINK");
    expect(types("GBPUSD", "1M")).toContain("SURFACE_MOVE");
  });
  it("evidence is numeric and percentiles are sane", () => {
    for (const o of obs) {
      if (o.percentile !== undefined)
        expect(o.percentile).toBeGreaterThanOrEqual(0);
      expect(Object.keys(o.evidence).length).toBeGreaterThan(0);
    }
    expect(percentile([1, 2, 3, 4], 3.5)).toBe(75);
    expect(zscore([1, 2, 3], 2)).toBeCloseTo(0);
  });
  it("cards cluster, carry confidence inputs, and dedup-key correctly", () => {
    const cards = toCards(obs, NOW);
    const ids = cards.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
    const eurjpy = cards.find((c) => c.id.includes("SKEW_STRETCH|EURJPY"));
    expect(eurjpy).toBeDefined();
    expect(eurjpy!.confidence.absZ).toBeGreaterThan(1.5);
  });
});

// ------------------------------------------------------------ workspaces
describe("workspace modes", () => {
  it("ships five modes with briefs and alert profiles", () => {
    expect(DEFAULT_WORKSPACES).toHaveLength(5);
    for (const w of DEFAULT_WORKSPACES) {
      expect(w.assistantBrief.length).toBeGreaterThan(10);
      expect(w.alertProfile.toastMin).toBeDefined();
      expect(w.schemaVersion).toBe(1);
    }
  });
  it("G10RV suppresses low-band invalidations (decision #3 option)", () => {
    const g10 = DEFAULT_WORKSPACES.find((w) => w.mnemonic === "G10RV")!;
    expect(g10.alertProfile.suppressInvalidationBelow).toBe("WATCH");
  });
});

describe("blotter schema (decision #4)", () => {
  it("is one table with kind+status lifecycle", () => {
    expect(BLOTTER_DDL).toContain("'idea','paper','live','invalidated'");
    expect(BLOTTER_DDL).toContain("linked_opportunity_id");
    expect(BLOTTER_DDL).not.toMatch(/CREATE TABLE .*paper_/);
  });
});
