"""Signal 5: event volatility anomaly.

Compares what the surface CHARGES for a scheduled event against what that
event has historically DELIVERED.
"""
from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd

from volwatch.core.models import Tenor
from volwatch.data.events import EventCalendar
from volwatch.signals.base import (
    Direction, Signal, SignalContext, SignalInstance,
)

log = logging.getLogger(__name__)

_ANN = 252.0


class EventVolAnomaly(Signal):
    name = "event_vol"

    math = (
        "For an upcoming event E inside the spanning tenor T (smallest "
        "quoted tenor whose expiry covers E): total implied variance "
        "w_T = sigma_T^2 * t_T decomposes as w_T = sigma_base^2 * t_T "
        "+ v_event, where sigma_base is the pair's non-event baseline "
        "(median 21d realized). Implied event move (1-day, %) = "
        "100*sqrt(max(v_event, 0)). Historical delivered move = "
        "|ln(C_d/C_{d-1})|*100 over past occurrences of the same event. "
        "ratio = implied_move / median(delivered). Fires SELL_VOL above "
        "ratio_hi, BUY_VOL below ratio_lo, with >= min_history "
        "occurrences required.")
    intuition = (
        "Event premia are the most visibly 'manual' part of the vol "
        "surface: traders bucket a number of vols-per-event into the "
        "covering expiry. That number anchors on recent memory and "
        "salience — a violent CPI print inflates the NEXT CPI's premium "
        "long after delivered moves normalize, and sleepy events get "
        "under-bucketed until they surprise. Comparing the bucketed "
        "premium to the event's own delivered history is the most direct "
        "rich/cheap test in vol space.")
    edge = (
        "edge_estimate (vol pts on the spanning tenor) = sigma_T - "
        "sqrt((w_T - v_event + v_median_delivered) / t_T) * 100: the "
        "tenor-vol repricing if the market re-bucketed the event at its "
        "historical median delivery. Monetized with the spanning-tenor "
        "straddle (or event-date FVA/weekly) delta-hedged through the "
        "event, against a neighbor tenor to isolate the event bucket.")
    failure_modes = (
        "(1) Small samples: a handful of past occurrences is a noisy "
        "median — min_history is a floor, not a guarantee. (2) Regime "
        "breaks: the NEXT CPI genuinely matters more when policy is "
        "data-dependent; history under-prices it (the premium can be "
        "RIGHT). (3) Baseline contamination: if recent realized is itself "
        "event-inflated, v_event is understated. (4) Calendar errors: a "
        "rescheduled or mis-dated event makes the whole decomposition "
        "wrong — the calendar CSV is desk-maintained, garbage in garbage "
        "out. (5) Selling event vol is short a jump by construction; "
        "sizing must assume the tail occurrence happens.")

    def compute(self, ctx: SignalContext) -> list[SignalInstance]:
        out: list[SignalInstance] = []
        cal = EventCalendar.from_csv(
            self.params.get("calendar_path", "config/events.csv"))
        horizon = int(self.params.get("horizon_days", 7))
        ratio_hi = float(self.params.get("ratio_hi", 1.5))
        ratio_lo = float(self.params.get("ratio_lo", 0.6))
        min_hist = int(self.params.get("min_history", 3))

        asof_d = ctx.asof.date()
        for ev in cal.upcoming(asof_d, horizon):
            for pair, surf in ctx.snapshot.vols.items():
                if not cal.affects(ev, pair):
                    continue
                ohlc = ctx.ohlc.get(pair)
                if ohlc is None or len(ohlc) < 60:
                    continue
                span = _spanning_tenor(ctx, ev.date, asof_d)
                if span is None:
                    continue
                try:
                    sigma_t = surf.get(span).atm / 100.0
                except KeyError:
                    continue
                t_t = ctx.ts[span]
                base = _baseline_vol(ohlc)
                w_t = sigma_t ** 2 * t_t
                v_event = max(w_t - base ** 2 * t_t, 0.0)
                implied_move = 100.0 * math.sqrt(v_event)

                hist_moves = _delivered_moves(
                    ohlc, cal.past_occurrences(ev.name, ev.ccy, asof_d))
                if len(hist_moves) < min_hist:
                    log.debug("event %s %s: only %d past moves — silent",
                              ev.name, pair, len(hist_moves))
                    continue
                med = float(np.median(hist_moves))
                if med <= 0 or implied_move <= 0:
                    continue
                ratio = implied_move / med
                if ratio_lo <= ratio <= ratio_hi:
                    continue

                v_med = (med / 100.0) ** 2
                repriced = math.sqrt(max(w_t - v_event + v_med, 1e-12) / t_t)
                edge_vp = (sigma_t - repriced) * 100.0
                direction = (Direction.SELL_VOL if ratio > ratio_hi
                             else Direction.BUY_VOL)
                out.append(SignalInstance(
                    signal=self.name, pair=pair,
                    structure=f"{span.value} straddle over {ev.ccy} "
                              f"{ev.name} ({ev.date.isoformat()})",
                    direction=direction,
                    score=math.log(ratio) / math.log(ratio_hi),
                    value=ratio,
                    edge_estimate=edge_vp if direction is Direction.SELL_VOL
                    else -edge_vp,
                    asof=ctx.asof, tenors=(span,),
                    details={"event": ev.name, "event_date": str(ev.date),
                             "implied_move_pct": round(implied_move, 3),
                             "median_delivered_pct": round(med, 3),
                             "n_history": len(hist_moves),
                             "baseline_vol": round(base * 100, 3),
                             "spanning_tenor_vol": round(sigma_t * 100, 3)}))
        return out


def _spanning_tenor(ctx: SignalContext, ev_date, asof_d) -> Tenor | None:
    """Smallest quoted tenor whose expiry covers the event date."""
    days_to = (ev_date - asof_d).days
    for tenor in sorted(ctx.ts, key=ctx.ts.get):
        if ctx.ts[tenor] * 365.0 >= days_to:
            return tenor
    return None


def _baseline_vol(ohlc: pd.DataFrame, window: int = 21) -> float:
    """Median rolling 21d close-close vol — the 'normal day' rate."""
    r = np.log(ohlc["close"]).diff()
    roll = np.sqrt(_ANN * (r * r).rolling(window).mean()).dropna()
    return float(roll.median())


def _delivered_moves(ohlc: pd.DataFrame, occurrences) -> list[float]:
    """|log return| in % on each past event date present in the OHLC."""
    if "date" not in ohlc.columns or ohlc.empty:
        return []
    df = ohlc.reset_index(drop=True)
    dates = pd.to_datetime(df["date"]).dt.date          # normalize once
    idx = {d: i for i, d in enumerate(dates)}
    out = []
    for ev in occurrences:
        i = idx.get(ev.date)
        if i is None or i == 0:
            continue
        move = abs(math.log(df["close"].iloc[i] / df["close"].iloc[i - 1]))
        out.append(move * 100.0)
    return out
