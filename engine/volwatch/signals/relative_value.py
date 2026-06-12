"""Signals 3-4: skew rich/cheap and triangle implied-vs-realized correlation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from volwatch.core.models import Tenor
from volwatch.signals.base import (
    Direction, Signal, SignalContext, SignalInstance, zscore,
)


class SkewRichCheap(Signal):
    name = "skew_richcheap"

    math = (
        "Primary: z = (RR25_now - mean(RR25_hist)) / std(RR25_hist) per "
        "pair/tenor. Supporting diagnostic: realized spot-vol beta = "
        "corr(daily spot return, d(rolling 21d RV)) over the lookback — "
        "the statistical quantity the skew is pricing. SABR rho from the "
        "calibration is attached as the model-space view of the same skew.")
    intuition = (
        "The risk reversal prices the covariance of spot with vol (which "
        "way vol explodes). When RR stretches far from its own history "
        "while the realized spot-vol relationship has NOT changed, the "
        "market is overpaying for directional convexity — typically after "
        "a one-sided spot move loads up hedging demand on one wing.")
    edge = (
        "edge_estimate = RR_now - mean(RR_hist), vol pts of RR: what the "
        "wing spread pays beyond this pair's normal skew. Monetized with "
        "risk reversals (zero-ish vega, long the cheap wing) hedged on a "
        "delta basis.")
    failure_modes = (
        "(1) Skew regimes shift PERSISTENTLY (policy regime change, "
        "intervention risk): the z-score mean-reverts to a mean that no "
        "longer exists. (2) RR positions carry vanna/volga path P&L that "
        "can dominate the entry edge. (3) If the realized spot-vol beta "
        "moved WITH the RR, the repricing is justified — the supporting "
        "diagnostic must disagree with the move for the fade to make sense.")

    def compute(self, ctx: SignalContext) -> list[SignalInstance]:
        out: list[SignalInstance] = []
        lookback = int(self.params.get("lookback_days", 120))
        z_entry = float(self.params.get("z_entry", 1.5))
        tenors = [Tenor(t) for t in self.params.get("tenors", ["1M", "3M"])]

        for pair, surf in ctx.snapshot.vols.items():
            ohlc = ctx.ohlc.get(pair)
            for tenor in tenors:
                try:
                    rr_now = surf.get(tenor).rr25
                except KeyError:
                    continue
                rr_hist = ctx.history.series(pair, tenor, "rr25").tail(lookback)
                z = zscore(rr_hist, rr_now)
                if z is None or abs(z) < z_entry:
                    continue
                beta = _spot_vol_beta(ohlc) if ohlc is not None else None
                sabr_rho = None
                cs = ctx.calibrated.get(pair)
                if cs is not None and tenor in cs.sabr:
                    sabr_rho = cs.sabr[tenor].rho
                direction = (Direction.SELL_SKEW if z > 0
                             else Direction.BUY_SKEW)
                out.append(SignalInstance(
                    signal=self.name, pair=pair,
                    structure=f"{tenor.value} 25d risk reversal",
                    direction=direction, score=z, value=rr_now,
                    edge_estimate=float(rr_now - rr_hist.mean()),
                    asof=ctx.asof, tenors=(tenor,),
                    details={"rr25": rr_now,
                             "rr_hist_mean": float(rr_hist.mean()),
                             "realized_spot_vol_beta": beta,
                             "sabr_rho": sabr_rho}))
        return out


def _spot_vol_beta(ohlc: pd.DataFrame, window: int = 21,
                   lookback: int = 120) -> float | None:
    """corr(spot return, change in rolling RV) — what the skew prices."""
    if len(ohlc) < window + 30:
        return None
    r = np.log(ohlc["close"]).diff()
    rv = np.sqrt(252.0 * (r * r).rolling(window).mean())
    pair = pd.concat([r, rv.diff()], axis=1).dropna().tail(lookback)
    if len(pair) < 30:
        return None
    return float(pair.corr().iloc[0, 1])


class TriangleCorrelation(Signal):
    name = "triangle_correlation"

    math = (
        "For triangle (cross, leg1, leg2): if cross = leg1*leg2 (e.g. "
        "EURJPY = EURUSD*USDJPY) then r_x = r_1 + r_2 and "
        "sigma_x^2 = s1^2 + s2^2 + 2*rho*s1*s2  =>  "
        "rho_implied = (sx^2 - s1^2 - s2^2) / (2*s1*s2); "
        "if cross = leg1/leg2 (EURGBP = EURUSD/GBPUSD), the sign flips: "
        "rho_implied = (s1^2 + s2^2 - sx^2) / (2*s1*s2). "
        "Signal metric: gap = rho_implied - rho_realized(lookback of daily "
        "log returns), fired when |gap| > corr_gap_entry.")
    intuition = (
        "Three vols on a currency triangle embed exactly one correlation; "
        "the legs and the cross are quoted by different flows and desks, "
        "so the embedded correlation drifts from delivered correlation. "
        "Implied corr too HIGH means the cross is rich vs its legs; too "
        "LOW means the cross is cheap. This is the cleanest structural RV "
        "in FX vol because the identity is enforced by triangular spot "
        "arbitrage itself.")
    edge = (
        "edge_estimate ~ |gap| * s1*s2/sx in vol pts of the cross: the "
        "cross-vol repricing implied by correlation converging to realized. "
        "Monetized vega-weighted: sell cross straddle / buy leg straddles "
        "(or inverse), delta-hedged.")
    failure_modes = (
        "(1) Realized correlation is regime-dependent: risk-off spikes "
        "USD-leg correlations violently — the gap can be the market "
        "correctly pricing the NEXT regime. (2) Three-legged structures "
        "have heavy transaction costs; small gaps don't clear them. "
        "(3) Vega weights drift as spot moves; the position needs "
        "rebalancing discipline. (4) ATM vols proxy the full smile — "
        "correlation skew is not captured.")

    def compute(self, ctx: SignalContext) -> list[SignalInstance]:
        out: list[SignalInstance] = []
        lookback = int(self.params.get("lookback_days", 60))
        gap_entry = float(self.params.get("corr_gap_entry", 0.10))
        tenor = Tenor(self.params.get("tenor", "3M"))

        for tri in self.params.get("triangles", []):
            cross, l1, l2 = tri["cross"], tri["leg1"], tri["leg2"]
            rel = tri.get("relation", "product")
            vols = ctx.snapshot.vols
            if not all(p in vols for p in (cross, l1, l2)):
                continue
            try:
                sx = vols[cross].get(tenor).atm / 100.0
                s1 = vols[l1].get(tenor).atm / 100.0
                s2 = vols[l2].get(tenor).atm / 100.0
            except KeyError:
                continue
            if rel == "product":
                rho_imp = (sx**2 - s1**2 - s2**2) / (2 * s1 * s2)
            else:
                rho_imp = (s1**2 + s2**2 - sx**2) / (2 * s1 * s2)
            rho_real = _realized_corr(ctx.ohlc.get(l1), ctx.ohlc.get(l2),
                                      lookback)
            if rho_real is None:
                continue
            if rel == "product":
                # legs' corr enters cross variance with +sign as computed
                gap = rho_imp - rho_real
            else:
                gap = rho_imp - rho_real
            if abs(gap) < gap_entry:
                continue
            edge_volpts = abs(gap) * s1 * s2 / sx * 100.0
            direction = Direction.SELL_CORR if gap > 0 else Direction.BUY_CORR
            cross_leg = ("sell cross vol / buy leg vols" if gap > 0
                         else "buy cross vol / sell leg vols")
            out.append(SignalInstance(
                signal=self.name, pair=cross,
                structure=f"{tenor.value} triangle vs {l1}/{l2} "
                          f"({cross_leg})",
                direction=direction,
                score=gap / max(gap_entry, 1e-9),   # gap in entry units
                value=gap, edge_estimate=edge_volpts,
                asof=ctx.asof, tenors=(tenor,),
                details={"rho_implied": rho_imp, "rho_realized": rho_real,
                         "vol_cross": sx * 100, "vol_leg1": s1 * 100,
                         "vol_leg2": s2 * 100, "relation": rel}))
        return out


def _realized_corr(o1: pd.DataFrame | None, o2: pd.DataFrame | None,
                   lookback: int) -> float | None:
    if o1 is None or o2 is None:
        return None
    r1 = np.log(o1["close"]).diff().tail(lookback).reset_index(drop=True)
    r2 = np.log(o2["close"]).diff().tail(lookback).reset_index(drop=True)
    n = min(len(r1), len(r2))
    if n < 30:
        return None
    return float(np.corrcoef(r1.tail(n), r2.tail(n))[0, 1])
