"""Garman–Kohlhagen (FX Black–Scholes) machinery.

Pure functions only — no state, no market objects. Inputs in natural units:
spot/strike in price terms, vol as decimal (0.075 = 7.5%), rates as decimal
continuous-compounding approximations, T in year fractions.

Delta conventions implemented (Clark 2011, ch.3):

    spot, unadjusted        Δ = ω·e^{-r_f T}·N(ω d1)
    forward, unadjusted     Δ = ω·N(ω d1)
    spot, premium-adjusted  Δ = ω·e^{-r_f T}·(K/F)·N(ω d2)
    forward, premium-adj.   Δ = ω·(K/F)·N(ω d2)

ω = +1 call / -1 put. Premium adjustment subtracts the option premium (paid
in base ccy) from the hedge — hence the (K/F)·N(d2) structure.
"""
from __future__ import annotations

import math

from volwatch.core.conventions import DeltaType

_SQRT2 = math.sqrt(2.0)
_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)


def ncdf(x: float) -> float:
    """Standard normal CDF via math.erf — ~50x faster than
    scipy.stats.ncdf for scalars, identical to ~1e-16. Matters because
    delta() sits inside brentq/minimize loops (strike solving, PA branch
    search)."""
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) * _INV_SQRT_2PI


def forward(spot: float, rd: float, rf: float, t: float) -> float:
    """Covered-interest forward. rd = quote(domestic) ccy rate, rf = base."""
    return spot * math.exp((rd - rf) * t)


def d1(f: float, k: float, vol: float, t: float) -> float:
    return (math.log(f / k) + 0.5 * vol * vol * t) / (vol * math.sqrt(t))


def d2(f: float, k: float, vol: float, t: float) -> float:
    return d1(f, k, vol, t) - vol * math.sqrt(t)


def price(f: float, k: float, vol: float, t: float, rd: float,
          omega: int) -> float:
    """Undiscounted-forward Black price, discounted at rd (quote ccy units)."""
    _d1, _d2 = d1(f, k, vol, t), d2(f, k, vol, t)
    return math.exp(-rd * t) * omega * (f * ncdf(omega * _d1)
                                        - k * ncdf(omega * _d2))


def delta(f: float, k: float, vol: float, t: float, rf: float, omega: int,
          delta_type: DeltaType, premium_adjusted: bool) -> float:
    """Dispatch to the right convention. This signature is the ONE entry
    point — analytics must never compute N(d1) by hand."""
    disc = math.exp(-rf * t) if delta_type is DeltaType.SPOT else 1.0
    if premium_adjusted:
        return omega * disc * (k / f) * ncdf(omega * d2(f, k, vol, t))
    return omega * disc * ncdf(omega * d1(f, k, vol, t))


def atm_dns_strike(f: float, vol: float, t: float,
                   premium_adjusted: bool) -> float:
    """Delta-neutral-straddle strike.

    Unadjusted:        K = F·exp(+σ²T/2)   (d1 = 0)
    Premium-adjusted:  K = F·exp(-σ²T/2)   (d2 = 0)
    """
    sign = -1.0 if premium_adjusted else 1.0
    return f * math.exp(sign * 0.5 * vol * vol * t)


def vega(f: float, k: float, vol: float, t: float, rd: float) -> float:
    """dPrice/dVol per 1.0 of vol (divide by 100 for per-vol-point)."""
    return math.exp(-rd * t) * f * npdf(d1(f, k, vol, t)) * math.sqrt(t)
