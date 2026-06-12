"""Signals 1-2: vol risk premium (rich/cheap vol) and term-structure kink."""
from __future__ import annotations

import numpy as np
import pandas as pd

from volwatch.analytics.realized import rolling_close_close
from volwatch.core.models import Tenor
from volwatch.signals.base import (
    Direction, Signal, SignalContext, SignalInstance, zscore,
)


class VolRiskPremium(Signal):
    name = "vol_risk_premium"

    math = (
        "spread_t = IV_atm(tenor) - RV_cc(matched window); "
        "z = (spread_now - mean(spread_hist)) / std(spread_hist), "
        "history over `lookback_days` of daily spreads built from stored "
        "ATM quotes and rolling close-close realized.")
    intuition = (
        "Implied trades above subsequently-realized most of the time: "
        "option sellers demand a premium for bearing gap risk and "
        "discontinuous P&L. The tradeable observation is not the premium "
        "itself but its EXTREMES vs its own history: an unusually wide "
        "spread means fear is overpriced relative to delivered movement; "
        "unusually narrow or negative means movement is underpriced.")
    edge = (
        "edge_estimate = spread_now - mean(spread_hist), in vol pts: the "
        "EXCESS premium vs what this pair/tenor normally pays. Monetized "
        "by delta-hedged straddles/variance positions over the tenor.")
    failure_modes = (
        "(1) Backward realized is the forecast — wrong precisely at regime "
        "changes (the z spikes BEFORE realized catches up to a new regime, "
        "selling vol into the storm). (2) Event premia: wide spreads ahead "
        "of scheduled events are payment for a known jump, not mispricing — "
        "cross-check the event calendar. (3) Short vol has unbounded loss; "
        "the premium is compensation, not arbitrage.")

    def compute(self, ctx: SignalContext) -> list[SignalInstance]:
        out: list[SignalInstance] = []
        lookback = int(self.params.get("lookback_days", 120))
        z_entry = float(self.params.get("z_entry", 1.5))
        tenors = [Tenor(t) for t in self.params.get("tenors", ["1M", "3M"])]
        windows = {Tenor.M1: 21, Tenor.M3: 63, Tenor.M6: 126}

        for pair, rep in ctx.carry.items():
            ohlc = ctx.ohlc.get(pair)
            if ohlc is None or ohlc.empty:
                continue
            for tenor in tenors:
                try:
                    tc = rep.get(tenor)
                except KeyError:
                    continue
                win = windows.get(tenor, 21)
                iv_hist = ctx.history.series(pair, tenor, "atm")
                rv_roll = rolling_close_close(ohlc, win) * 100.0
                if len(iv_hist) < 5:
                    continue
                rv_daily = pd.Series(
                    rv_roll.values[-len(iv_hist):], index=iv_hist.index)
                spread_hist = (iv_hist - rv_daily).tail(lookback)
                spread_now = tc.implied - rv_roll.iloc[-1]
                z = zscore(spread_hist, spread_now)
                if z is None or abs(z) < z_entry:
                    continue
                direction = Direction.SELL_VOL if z > 0 else Direction.BUY_VOL
                out.append(SignalInstance(
                    signal=self.name, pair=pair,
                    structure=f"{tenor.value} ATM (delta-hedged)",
                    direction=direction, score=z, value=spread_now,
                    edge_estimate=float(spread_now - spread_hist.mean()),
                    asof=ctx.asof, tenors=(tenor,),
                    details={"implied": tc.implied,
                             "realized_cc": float(rv_roll.iloc[-1]),
                             "spread_hist_mean": float(spread_hist.mean()),
                             "matched_window_d": win}))
        return out


class TermStructureKink(Signal):
    name = "term_structure_kink"

    math = (
        "For each interior tenor T_i: kink_i = IV(T_i) - IV_interp(T_i), "
        "where IV_interp linearly interpolates TOTAL VARIANCE between "
        "T_{i-1} and T_{i+1} (the arb-consistent smooth curve). "
        "z = kink_now vs history of the same kink built from stored quotes.")
    intuition = (
        "A single tenor standing off the smooth curve is either flow "
        "(someone paid up for that expiry — often an event date moving "
        "into the bucket) or a stale quote. Forward vol makes it concrete: "
        "a positive kink at T_i makes the T_{i-1}->T_i forward vol rich and "
        "the T_i->T_{i+1} forward vol cheap simultaneously — the classic "
        "forward-vol-agreement RV setup against the kink.")
    edge = (
        "edge_estimate = kink_now - mean(kink_hist), vol pts: what the "
        "bucketed tenor pays over its no-kink interpolation, beyond this "
        "pair's normal local curvature. Monetized with calendar spreads "
        "or FVAs around the kinked tenor.")
    failure_modes = (
        "(1) Event dates are REAL: a CB meeting entering the 1M bucket "
        "produces a justified kink — fading it is selling the event. "
        "(2) Kinks at illiquid tenors (9M) can be quote noise; check "
        "validation flags. (3) Calendar spreads carry vega term-structure "
        "risk beyond the kink itself.")

    def compute(self, ctx: SignalContext) -> list[SignalInstance]:
        out: list[SignalInstance] = []
        lookback = int(self.params.get("lookback_days", 120))
        z_entry = float(self.params.get("z_entry", 1.5))

        for pair, surf in ctx.snapshot.vols.items():
            curve = surf.atm_curve()
            tenors = sorted(curve, key=lambda t: ctx.ts[t])
            hist = {t: ctx.history.series(pair, t, "atm") for t in tenors}
            for lo, mid, hi in zip(tenors, tenors[1:], tenors[2:]):
                t0, t1, t2 = ctx.ts[lo], ctx.ts[mid], ctx.ts[hi]
                kink_now = curve[mid] - _interp_tv(
                    curve[lo], curve[hi], t0, t1, t2)
                h = pd.concat([hist[lo], hist[mid], hist[hi]], axis=1,
                              keys=["lo", "mid", "hi"]).dropna()
                if h.empty:
                    continue
                kink_hist = (h["mid"] - _interp_tv(
                    h["lo"], h["hi"], t0, t1, t2)).tail(lookback)
                z = zscore(kink_hist, kink_now)
                if z is None or abs(z) < z_entry:
                    continue
                direction = (Direction.SELL_FWD_VOL if z > 0
                             else Direction.BUY_FWD_VOL)
                out.append(SignalInstance(
                    signal=self.name, pair=pair,
                    structure=f"{lo.value}/{mid.value}/{hi.value} calendar fly",
                    direction=direction, score=z, value=kink_now,
                    edge_estimate=float(kink_now - kink_hist.mean()),
                    asof=ctx.asof, tenors=(lo, mid, hi),
                    details={"kink_volpts": kink_now,
                             "hist_mean": float(kink_hist.mean()),
                             "curve": {t.value: curve[t]
                                       for t in (lo, mid, hi)}}))
        return out


def _interp_tv(v_lo, v_hi, t0: float, t1: float, t2: float):
    """Vol at t1 from linear-in-total-variance interpolation lo->hi."""
    w_lo, w_hi = v_lo**2 * t0, v_hi**2 * t2
    w1 = w_lo + (w_hi - w_lo) * (t1 - t0) / (t2 - t0)
    return np.sqrt(w1 / t1)
