"""Strike-space surface construction.

Pipeline:  VolQuote (ATM/RR/BF, delta space)
        -> 5-point smile σ(Δ)
        -> strikes via convention-aware solving
        -> StrikeSmile / StrikeSurface, with delta-space interpolation.

The dangerous part is premium-adjusted CALL deltas: Δ_pa(K) is NOT monotonic
in strike — it rises then falls, so a target delta can have two roots. Market
convention takes the strike on the RIGHT branch (the larger strike, where
delta is falling). We locate the maximum first, then root-find to its right.
Unadjusted deltas invert in closed form. (Clark 2011 §3.5–3.6.)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq, minimize_scalar
from scipy.special import ndtri

from volwatch.analytics import black
from volwatch.core.conventions import REGISTRY, DeltaType, PairConventions
from volwatch.core.models import Tenor, VolQuote, VolSurface

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Strike solving                                                               #
# --------------------------------------------------------------------------- #
def strike_from_delta(target_delta: float, f: float, vol: float, t: float,
                      rf: float, omega: int, delta_type: DeltaType,
                      premium_adjusted: bool) -> float:
    """Invert delta -> strike under the given convention.

    target_delta is SIGNED (e.g. -0.25 for a 25d put).
    """
    if not premium_adjusted:
        # closed form: Δ = ω·disc·N(ω d1)  =>  d1 = ω·N^{-1}(ω Δ/disc)
        disc = math.exp(-rf * t) if delta_type is DeltaType.SPOT else 1.0
        _d1 = omega * ndtri(omega * target_delta / disc)
        return f * math.exp(-_d1 * vol * math.sqrt(t) + 0.5 * vol * vol * t)

    def dlt(k: float) -> float:
        return black.delta(f, k, vol, t, rf, omega, delta_type, True)

    # Bracket scaled to the smile's natural width: strikes for 10d-25d live
    # within a few sigma*sqrt(T) of F. A fixed [0.2F, 5F] bracket fails for
    # short tenors where the PA-call delta peak is a needle near F that a
    # bounded optimizer steps straight over.
    w = 8.0 * vol * math.sqrt(t) + 0.5 * vol * vol * t
    lo, hi = f * math.exp(-w), f * math.exp(w)
    if omega == -1:
        # PA put delta is monotone decreasing in K on any sane range
        return brentq(lambda k: dlt(k) - target_delta, lo, hi, xtol=1e-10)

    # PA call: find the delta maximum, then solve on the right branch
    res = minimize_scalar(lambda k: -dlt(k), bounds=(lo, hi), method="bounded")
    k_star, d_max = res.x, -res.fun
    if target_delta > d_max:
        raise ValueError(
            f"unattainable premium-adjusted call delta {target_delta:.4f} "
            f"(max {d_max:.4f}) — check vol/T inputs")
    return brentq(lambda k: dlt(k) - target_delta, k_star, hi, xtol=1e-10)


# --------------------------------------------------------------------------- #
# Smile in strike space                                                        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class SmileNode:
    label: str          # "10P","25P","ATM","25C","10C"
    delta: float        # signed quoted delta (ATM: DNS, reported as 0.50 conv.)
    strike: float
    vol: float          # decimal


@dataclass(frozen=True, slots=True)
class StrikeSmile:
    pair: str
    tenor: Tenor
    t: float            # year fraction
    f: float            # forward outright
    nodes: tuple[SmileNode, ...]      # ordered by strike

    def vol_at_delta(self, call_delta: float) -> float:
        """Interpolated vol at a simple call-delta coordinate (see builder)."""
        pts = sorted(((_smile_x(n.label), n.vol) for n in self.nodes))
        xs, ys = zip(*pts)          # nodes are strike-ordered = decreasing x
        return float(CubicSpline(xs, ys)(call_delta))

    def vol_at_strike(self, k: float) -> float:
        """Vol at arbitrary strike via monotone strike-space spline.

        v1 interpolator. Replaced by SABR/SSVI fits in Stage 3 for anything
        risk-bearing; retained as a model-free cross-check thereafter.
        """
        xs = np.log([n.strike for n in self.nodes])
        ys = [n.vol for n in self.nodes]
        return float(CubicSpline(xs, ys, bc_type="natural")(math.log(k)))


def _smile_x(label: str) -> float:
    """Smile coordinate: approximate call-delta axis 0.10 .. 0.90."""
    return {"10C": 0.10, "25C": 0.25, "ATM": 0.50,
            "25P": 0.75, "10P": 0.90}[label]


# --------------------------------------------------------------------------- #
# Builder                                                                      #
# --------------------------------------------------------------------------- #
class SmileBuilder:
    """VolQuote + market state -> StrikeSmile under the pair's conventions."""

    def __init__(self, conventions: PairConventions) -> None:
        self.conv = conventions

    def build(self, quote: VolQuote, f: float, t: float,
              rf: float) -> StrikeSmile:
        conv = self.conv
        dtype = conv.delta_type(quote.tenor)
        smile = quote.smile()                       # label -> vol pts

        nodes: list[SmileNode] = []
        atm_vol = smile["ATM"] / 100.0
        k_atm = black.atm_dns_strike(f, atm_vol, t, conv.premium_adjusted)
        nodes.append(SmileNode("ATM", 0.50, k_atm, atm_vol))

        for label, signed_delta in (("25C", 0.25), ("10C", 0.10),
                                    ("25P", -0.25), ("10P", -0.10)):
            if label not in smile:
                continue
            vol = smile[label] / 100.0
            omega = 1 if label.endswith("C") else -1
            k = strike_from_delta(signed_delta, f, vol, t, rf, omega,
                                  dtype, conv.premium_adjusted)
            nodes.append(SmileNode(label, signed_delta, k, vol))

        nodes.sort(key=lambda n: n.strike)
        strikes = [n.strike for n in nodes]
        if strikes != sorted(set(strikes)):
            raise ValueError(
                f"{quote.pair} {quote.tenor.value}: non-monotone strikes "
                f"{[(n.label, round(n.strike, 5)) for n in nodes]} — "
                "quote vector is internally inconsistent")
        return StrikeSmile(pair=quote.pair, tenor=quote.tenor, t=t, f=f,
                           nodes=tuple(nodes))


@dataclass(frozen=True)
class StrikeSurface:
    pair: str
    smiles: tuple[StrikeSmile, ...]                 # ordered by t

    def get(self, tenor: Tenor) -> StrikeSmile:
        for s in self.smiles:
            if s.tenor == tenor:
                return s
        raise KeyError(f"{self.pair}: no smile for {tenor.value}")


def build_surface(surface: VolSurface, forwards: dict[Tenor, float],
                  year_fractions: dict[Tenor, float],
                  rf_curve: dict[Tenor, float]) -> StrikeSurface:
    """Assemble a full strike surface. Tenors lacking a forward or yf are
    skipped with a warning (never fabricated)."""
    conv = REGISTRY.get(surface.pair)
    builder = SmileBuilder(conv)
    smiles = []
    for q in surface:
        if q.tenor not in forwards or q.tenor not in year_fractions:
            log.warning("%s %s: missing forward/yf — tenor skipped",
                        surface.pair, q.tenor.value)
            continue
        smiles.append(builder.build(q, forwards[q.tenor],
                                    year_fractions[q.tenor],
                                    rf_curve.get(q.tenor, 0.0)))
    smiles.sort(key=lambda s: s.t)
    return StrikeSurface(pair=surface.pair, smiles=tuple(smiles))
