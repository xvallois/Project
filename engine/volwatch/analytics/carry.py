"""Volatility carry analytics.

For each quoted tenor, three numbers a vol trader lives on:

  iv_rv_spread   ATM implied minus matched-window realized (vol pts).
                 The raw vol risk premium: what shorting vol "earns" if the
                 future repeats the recent past. Positive most of the time
                 in G10 — that is the premium, not free money: it is paid
                 for bearing gap/crash risk, and it inverts violently.

  rolldown_1w    sigma_atm(T) - sigma_atm(T - 1w), curve-interpolated.
                 What a long-vol position re-marks to in a week if the curve
                 is UNCHANGED. Upward-sloping curve => positive number
                 => long vol bleeds this many vol pts/week from roll alone.

  breakeven_daily   implied/sqrt(252): the daily move (in %) spot must
                 average for long gamma at this implied to pay for theta.

Failure modes (these print on the dashboard next to the numbers):
  * IV-RV uses BACKWARD realized as the forecast — it is wrong precisely
    when regimes change, which is when it matters most.
  * Rolldown assumes static curve; curves steepen/flatten.
  * Matched windows use calendar-day tenors vs trading-day realized — small
    basis, consistent across pairs, fine for RV ranking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from volwatch.analytics.realized import RealizedVolSet
from volwatch.core.models import Tenor

log = logging.getLogger(__name__)

_WEEK = 7.0 / 365.0


@dataclass(frozen=True, slots=True)
class TenorCarry:
    pair: str
    tenor: Tenor
    implied: float                # ATM, vol pts (e.g. 7.50)
    realized_matched: float       # vol pts, matched window (yang-zhang)
    iv_rv_spread: float           # vol pts
    rolldown_1w: float | None     # vol pts; None for the shortest tenor
    breakeven_daily_pct: float    # spot % move per day


@dataclass(frozen=True)
class CarryReport:
    pair: str
    tenors: tuple[TenorCarry, ...]

    def get(self, tenor: Tenor) -> TenorCarry:
        for tc in self.tenors:
            if tc.tenor == tenor:
                return tc
        raise KeyError(tenor)

    def richest_vs_realized(self) -> TenorCarry:
        return max(self.tenors, key=lambda x: x.iv_rv_spread)


def _interp_curve(ts: list[float], vols: list[float], t: float) -> float:
    """Linear in TOTAL VARIANCE, the arbitrage-consistent interpolation."""
    w = [v * v * t_ for v, t_ in zip(vols, ts)]
    wt = float(np.interp(t, ts, w))
    return float(np.sqrt(wt / t))


def carry_report(pair: str, atm_curve: dict[Tenor, float],
                 ts: dict[Tenor, float],
                 realized: RealizedVolSet) -> CarryReport:
    """atm_curve in VOL POINTS (7.5 = 7.5%); realized set in decimal."""
    tenors = sorted(atm_curve, key=lambda t: ts[t])
    curve_ts = [ts[t] for t in tenors]
    curve_vs = [atm_curve[t] for t in tenors]

    rows = []
    for tenor in tenors:
        implied = atm_curve[tenor]
        t = ts[tenor]
        try:
            rv = realized.matched(tenor) * 100.0
        except KeyError:
            log.debug("%s %s: no matched realized window", pair, tenor.value)
            continue
        roll = None
        if t - _WEEK > curve_ts[0]:
            roll = implied - _interp_curve(curve_ts, curve_vs, t - _WEEK)
        rows.append(TenorCarry(
            pair=pair, tenor=tenor, implied=implied, realized_matched=rv,
            iv_rv_spread=implied - rv, rolldown_1w=roll,
            breakeven_daily_pct=implied / np.sqrt(252.0)))
    return CarryReport(pair=pair, tenors=tuple(rows))
