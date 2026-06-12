/** Mock market + deterministic Tier-1 detectors (Phase 0).
 *
 * The mock mirrors the Python engine's MockProvider: seeded, regime-aware
 * series of (atm, rr25, bf25) per pair-tenor over 250 business days, plus
 * a current snap. The DETECTOR LOGIC IS REAL — only the data is mocked,
 * so when the sidecar arrives the detectors move server-side unchanged in
 * spirit and the feed contract is already exercised.
 */
import type { Pair, Tenor } from "../core/types";
import { PAIRS, TENORS } from "../core/types";
import { band } from "../core/opportunities/feed";
import type { Observation, ObservationType, OpportunityCard }
  from "../core/opportunities/types";

// mulberry32 — deterministic, tiny
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const gauss = (r: () => number) =>
  Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r());

const BASE_ATM: Record<Pair, number> = { EURUSD: 7.2, GBPUSD: 8.0,
  USDJPY: 10.5, USDCHF: 7.0, USDCAD: 6.2, AUDUSD: 9.5, NZDUSD: 10.0,
  EURJPY: 9.8, EURGBP: 6.0 };
const BASE_RR: Record<Pair, number> = { EURUSD: -0.35, GBPUSD: -0.55,
  USDJPY: -1.6, USDCHF: -0.5, USDCAD: 0.35, AUDUSD: -0.9, NZDUSD: -0.8,
  EURJPY: -1.4, EURGBP: -0.25 };
const TYF: Record<Tenor, number> = { ON: 1/365, "1W": 7/365, "2W": 14/365,
  "1M": 30/365, "2M": 61/365, "3M": 91/365, "6M": 182/365,
  "9M": 274/365, "1Y": 1 };

export interface SeriesPoint { atm: number; rr25: number; bf25: number }
export type History = Record<Pair, Record<Tenor, SeriesPoint[]>>;

export function buildHistory(seed = 2026, days = 250): History {
  const r = rng(seed);
  const out = {} as History;
  for (const pair of PAIRS) {
    out[pair] = {} as Record<Tenor, SeriesPoint[]>;
    let drift = 0;
    const rrDrift: Record<string, number> = {};
    for (let d = 0; d < days; d++) {
      drift += gauss(r) * 0.05;
      for (const tenor of TENORS) {
        const yf = TYF[tenor];
        const series = (out[pair][tenor] ??= []);
        rrDrift[tenor] = (rrDrift[tenor] ?? 0) + gauss(r) * 0.02;
        series.push({
          atm: BASE_ATM[pair] + 0.8 * Math.sqrt(yf) + drift
            + gauss(r) * 0.06,
          rr25: BASE_RR[pair] * (0.6 + 0.4 * Math.sqrt(yf / 0.25))
            + rrDrift[tenor] + gauss(r) * 0.03,
          bf25: 0.15 + 0.2 * Math.sqrt(yf) + gauss(r) * 0.015,
        });
      }
    }
  }
  // plant Phase-0 demo dislocations in the FINAL point (today):
  const plant = (p: Pair, t: Tenor, f: (x: SeriesPoint) => void) => {
    const s = out[p][t]; f(s[s.length - 1]);
  };
  plant("EURJPY", "3M", (x) => { x.rr25 -= 0.55; });     // skew stretch
  plant("USDJPY", "9M", (x) => { x.atm += 0.30; });      // term kink
  plant("GBPUSD", "1M", (x) => { x.atm += 0.45; });      // surface move
  return out;
}

export function percentile(series: number[], value: number): number {
  const below = series.filter((v) => v < value).length;
  return (100 * below) / series.length;
}
export function zscore(series: number[], value: number): number {
  const m = series.reduce((a, b) => a + b, 0) / series.length;
  const sd = Math.sqrt(series.reduce((a, b) => a + (b - m) ** 2, 0)
    / series.length);
  return sd < 1e-12 ? 0 : (value - m) / sd;
}

/** Tenor kink vs linear-in-total-variance interpolation of neighbours
 *  (same math as the Python engine's term_structure_kink). */
function kink(atm: number[], yfs: number[], i: number): number {
  const [t0, t1, t2] = [yfs[i - 1], yfs[i], yfs[i + 1]];
  const w0 = (atm[i - 1] / 100) ** 2 * t0;
  const w2 = (atm[i + 1] / 100) ** 2 * t2;
  const w1 = w0 + ((w2 - w0) * (t1 - t0)) / (t2 - t0);
  return atm[i] - Math.sqrt(w1 / t1) * 100;
}

// ----------------------------------------------------------------------
export function detect(hist: History, asof: string): Observation[] {
  const obs: Observation[] = [];
  let n = 0;
  const push = (type: ObservationType, pair: Pair, tenor: Tenor | undefined,
    metric: string, value: number, extra: Partial<Observation>) =>
    obs.push({ id: `obs-${n++}`, type, pair, tenor, metric,
      value: +value.toFixed(3), asof,
      evidence: {}, ...extra } as Observation);

  for (const pair of PAIRS) {
    const yfs = TENORS.map((t) => TYF[t]);
    const atmNow = TENORS.map((t) => hist[pair][t].at(-1)!.atm);

    for (const tenor of TENORS) {
      const s = hist[pair][tenor];
      const past = s.slice(0, -1);
      const cur = s.at(-1)!;
      // percentile breach (rr / atm beyond p95/p5)
      for (const metric of ["rr25", "atm"] as const) {
        const seriesVals = past.map((x) => x[metric]);
        const p = percentile(seriesVals, cur[metric]);
        const z = zscore(seriesVals, cur[metric]);
        if (p >= 95 || p <= 5) {
          push(metric === "rr25" ? "SKEW_STRETCH" : "PERCENTILE_BREACH",
            pair, tenor, metric, cur[metric],
            { percentile: +p.toFixed(1), zscore: +z.toFixed(2),
              evidence: { percentile: +p.toFixed(1), z: +z.toFixed(2),
                histMean: +(seriesVals.reduce((a,b)=>a+b,0)
                  / seriesVals.length).toFixed(3) } });
        }
      }
      // surface move: today's atm change vs distribution of daily changes
      const changes = past.slice(1).map((x, i) => x.atm - past[i].atm);
      const dNow = cur.atm - past.at(-1)!.atm;
      const zMove = zscore(changes, dNow);
      if (Math.abs(zMove) >= 3)
        push("SURFACE_MOVE", pair, tenor, "atm_change", dNow,
          { zscore: +zMove.toFixed(2),
            evidence: { dVolPts: +dNow.toFixed(3), z: +zMove.toFixed(2) } });
    }
    // term kinks on interior tenors
    for (let i = 1; i < TENORS.length - 1; i++) {
      const k = kink(atmNow, yfs, i);
      const histK = hist[pair][TENORS[i]].slice(0, -1).map((_, d) =>
        kink(TENORS.map((t) => hist[pair][t][d].atm), yfs, i));
      const z = zscore(histK, k);
      if (Math.abs(z) >= 2.2)
        push("TERM_KINK", pair, TENORS[i], "kink_volpts", k,
          { zscore: +z.toFixed(2),
            evidence: { kink: +k.toFixed(3), z: +z.toFixed(2) } });
    }
  }
  return obs;
}

const HEADLINE: Record<ObservationType, (o: Observation) => string> = {
  SKEW_STRETCH: (o) => `${o.tenor} risk reversal at p${o.percentile} of 1y`,
  PERCENTILE_BREACH: (o) => `${o.tenor} ATM at p${o.percentile} of 1y`,
  SURFACE_MOVE: (o) =>
    `${o.tenor} ATM moved ${o.value > 0 ? "+" : ""}${o.value}vp on the day`,
  TERM_KINK: (o) => `${o.tenor} standing ${o.value > 0 ? "+" : ""}${o.value}vp off the curve`,
  REGIME_SHIFT: () => "Correlation regime shift",
  EVENT_PRICING: () => "Event premium vs delivered history",
};

const STRUCTURE: Record<ObservationType, (o: Observation) => string> = {
  SKEW_STRETCH: (o) => `${o.tenor} 25d risk reversal`,
  PERCENTILE_BREACH: (o) => `${o.tenor} ATM (delta-hedged)`,
  SURFACE_MOVE: (o) => `${o.tenor} ATM`,
  TERM_KINK: (o) => `${o.tenor} calendar fly`,
  REGIME_SHIFT: () => "portfolio",
  EVENT_PRICING: (o) => `${o.tenor} straddle`,
};

/** Cluster observations into cards (Phase 0: same pair+tenor merge). */
export function toCards(obs: Observation[], asof: string,
                        persistence: Record<string, number> = {}):
                        OpportunityCard[] {
  const groups = new Map<string, Observation[]>();
  for (const o of obs) {
    const key = `${o.type}|${o.pair}|${o.tenor ?? ""}`;
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(o);
  }
  return [...groups.entries()].map(([key, members]) => {
    const lead = members.reduce((a, b) =>
      Math.abs(b.zscore ?? 0) > Math.abs(a.zscore ?? 0) ? b : a);
    const confidence = {
      absZ: Math.abs(lead.zscore ?? 0),
      persistenceCycles: persistence[key] ?? 1,
      dataQualityOk: true,
      modelsAgree: true,
    };
    return {
      id: key, type: lead.type, pair: lead.pair,
      tenors: lead.tenor ? [lead.tenor] : [],
      headline: HEADLINE[lead.type](lead),
      structure: STRUCTURE[lead.type](lead),
      band: band(confidence), confidence, evidence: members,
      status: "new" as const, createdAt: asof, updatedAt: asof,
    };
  });
}
