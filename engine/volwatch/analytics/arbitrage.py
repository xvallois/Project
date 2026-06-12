"""Arbitrage diagnostics.

Two checks, both reported as CONTINUOUS distances (signed margins), because
the trading content is in the margins:

  * Genuine quoted arbitrage in liquid G10 vol is almost always a stale or
    bad quote — a data alarm, not free money.
  * NEAR-violations (margins compressing toward zero) are dislocations:
    a calendar spread trading at almost-zero forward variance, a wing priced
    at almost-degenerate convexity. Those are tradeable observations.

Butterfly (within-tenor): Durrleman's condition on total variance w(k):

    g(k) = (1 - k*w'/(2w))^2 - (w'^2/4)*(1/w + 1/4) + w''/2  >=  0

evaluated by finite differences on a log-moneyness grid. min g(k) is the
margin (negative => butterfly arbitrage in the FITTED smile).

Calendar (across tenors): total variance non-decreasing in T at fixed
log-moneyness. Margin = min over the grid of w(k,T2) - w(k,T1), scaled to
forward variance for comparability.

All checks run on the SABR fits (smooth, differentiable). Running them on
raw 5-point quotes would mostly measure interpolation noise.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from volwatch.analytics.sabr import SabrFit, hagan_vol_array
from volwatch.core.models import Tenor

log = logging.getLogger(__name__)

_N_GRID = 121


def _grid(fits: "list[SabrFit] | SabrFit") -> np.ndarray:
    """Log-moneyness grid scaled to the smile's natural width.

    A FIXED grid is wrong: +-1.5 log-moneyness is ~100 standard deviations
    for a 1W smile (pure Hagan-extrapolation garbage) and only ~2 sd for a
    high-vol 1Y smile. We span +-6 ATM standard deviations of the WIDEST
    smile under comparison, floored for degenerate inputs.
    """
    fs = fits if isinstance(fits, list) else [fits]
    width = max(max(6.0 * f.alpha * np.sqrt(f.t) for f in fs), 0.02)
    return np.linspace(-width, width, _N_GRID)


@dataclass(frozen=True)
class ButterflyMargin:
    tenor: Tenor
    min_g: float                  # Durrleman margin; < 0 => arb in fit
    argmin_k: float               # where the smile is closest to degenerate


@dataclass(frozen=True)
class CalendarMargin:
    near: Tenor
    far: Tenor
    min_dw: float                 # min total-variance spread on the grid
    fwd_var_floor: float          # min implied forward variance (annualized)
    argmin_k: float


@dataclass(frozen=True)
class ArbReport:
    pair: str
    butterfly: tuple[ButterflyMargin, ...]
    calendar: tuple[CalendarMargin, ...]
    violations: tuple[str, ...] = field(default=())

    @property
    def clean(self) -> bool:
        return not self.violations


def _total_variance_grid(fit: SabrFit, grid: np.ndarray) -> np.ndarray:
    ks = fit.f * np.exp(grid)
    v = hagan_vol_array(fit.f, ks, fit.t, fit.alpha, fit.beta,
                        fit.rho, fit.nu)
    return v * v * fit.t


def butterfly_margin(fit: SabrFit) -> ButterflyMargin:
    k = _grid(fit)
    dk = k[1] - k[0]
    w = _total_variance_grid(fit, k)
    wp = np.gradient(w, dk)
    wpp = np.gradient(wp, dk)
    g = (1.0 - k * wp / (2.0 * w)) ** 2 \
        - (wp ** 2 / 4.0) * (1.0 / w + 0.25) + wpp / 2.0
    # ignore the extreme 5 grid points each side: FD noise at the boundary
    core = slice(5, -5)
    i = int(np.argmin(g[core])) + 5
    return ButterflyMargin(tenor=fit.tenor, min_g=float(g[i]),
                           argmin_k=float(k[i]))


def calendar_margins(fits: list[SabrFit]) -> list[CalendarMargin]:
    out: list[CalendarMargin] = []
    fits = sorted(fits, key=lambda f: f.t)
    for near, far in zip(fits, fits[1:]):
        k = _grid([near, far])
        w1 = _total_variance_grid(near, k)
        w2 = _total_variance_grid(far, k)
        dw = w2 - w1
        i = int(np.argmin(dw))
        fwd_var = dw / (far.t - near.t)
        out.append(CalendarMargin(
            near=near.tenor, far=far.tenor, min_dw=float(dw[i]),
            fwd_var_floor=float(np.min(fwd_var)),
            argmin_k=float(k[i])))
    return out


def check_surface(pair: str, fits: list[SabrFit]) -> ArbReport:
    bf = tuple(butterfly_margin(f) for f in fits)
    cal = tuple(calendar_margins(fits))
    violations: list[str] = []
    for b in bf:
        if b.min_g < 0:
            violations.append(
                f"butterfly: {pair} {b.tenor.value} g={b.min_g:.4g} "
                f"at k={b.argmin_k:.2f}")
    for c in cal:
        if c.min_dw < 0:
            violations.append(
                f"calendar: {pair} {c.near.value}->{c.far.value} "
                f"dw={c.min_dw:.4g} at k={c.argmin_k:.2f}")
    for v in violations:
        log.warning("ARB %s", v)
    return ArbReport(pair=pair, butterfly=bf, calendar=cal,
                     violations=tuple(violations))
