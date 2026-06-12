"""SSVI surface parameterization (Gatheral & Jacquier 2014).

Total variance:  w(k, theta) = theta/2 * [1 + rho*phi(theta)*k
                                + sqrt((phi(theta)*k + rho)^2 + 1 - rho^2)]
with power-law  phi(theta) = eta / theta^gamma  and theta_T = ATM total
variance at expiry T (taken from the market, interpolated linearly in T).

Role in the system: the GLOBAL, calendar-consistent view. Three parameters
(rho, eta, gamma) for the whole surface — deliberately rigid. Where the
rigid fit disagrees with quotes or with per-tenor SABR, that disagreement
is information (stale quote, genuine dislocation, or term-structure-of-skew
the model can't bend to).

Known limitation, accepted for v1: a single rho cannot express a skew term
structure (FX RR term structures are real). The upgrade path is eSSVI
(rho(theta)); the residual diagnostics this module emits are exactly what
will justify that upgrade when the time comes.

No-arbitrage (Gatheral-Jacquier Thm 4.2, power-law case): butterfly-free if
    theta*phi(theta)*(1+|rho|) <= 4   and   theta*phi(theta)^2*(1+|rho|) <= 4
for all theta in range. Calendar-free if theta_T is non-decreasing (checked
against market thetas, since we take them as given).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from volwatch.analytics.surface import StrikeSurface
from volwatch.core.models import Tenor

log = logging.getLogger(__name__)


def ssvi_total_variance(k: float, theta: float, rho: float, eta: float,
                        gamma: float) -> float:
    phi = eta / (theta ** gamma)
    return 0.5 * theta * (1.0 + rho * phi * k
                          + math.sqrt((phi * k + rho) ** 2 + 1.0 - rho * rho))


@dataclass(frozen=True)
class SsviFit:
    pair: str
    rho: float
    eta: float
    gamma: float
    thetas: dict[Tenor, float]      # market ATM total variance per tenor
    ts: dict[Tenor, float]
    forwards: dict[Tenor, float]
    rmse: float                     # vol points, all non-ATM nodes
    butterfly_ok: bool              # Gatheral-Jacquier static conditions
    calendar_ok: bool               # theta monotone in T

    def theta_at(self, t: float) -> float:
        """Linear interpolation of ATM total variance in T (flat extrap)."""
        pts = sorted(zip(self.ts.values(), self.thetas.values()))
        ts, ths = zip(*pts)
        return float(np.interp(t, ts, ths))

    def vol(self, k_strike: float, tenor: Tenor) -> float:
        t = self.ts[tenor]
        k = math.log(k_strike / self.forwards[tenor])
        w = ssvi_total_variance(k, self.thetas[tenor], self.rho,
                                self.eta, self.gamma)
        return math.sqrt(w / t)

    def vol_at_t(self, k_logmoneyness: float, t: float) -> float:
        w = ssvi_total_variance(k_logmoneyness, self.theta_at(t),
                                self.rho, self.eta, self.gamma)
        return math.sqrt(w / t)


def _static_butterfly_ok(thetas: list[float], rho: float, eta: float,
                         gamma: float) -> bool:
    for th in thetas:
        phi = eta / th ** gamma
        if th * phi * (1 + abs(rho)) > 4.0 or \
           th * phi * phi * (1 + abs(rho)) > 4.0:
            return False
    return True


def calibrate_ssvi(surface: StrikeSurface,
                   min_t: float = 10.0 / 365.0) -> SsviFit:
    """Fit global (rho, eta, gamma) to all wing nodes of all tenors.

    ATM nodes are matched by construction (w(0) = theta = market ATM total
    variance), so only wings enter the objective.

    Tenors with t < min_t are EXCLUDED entirely (default: < ~2 weeks).
    Rationale: theta -> 0 makes phi = eta/theta^gamma explode, so the
    power-law SSVI cannot speak at ON/1W — observed as ~18 volpts of
    SABR/SSVI divergence at ON before this exclusion. Per-tenor SABR
    remains the authority at short dates.
    """
    thetas: dict[Tenor, float] = {}
    ts: dict[Tenor, float] = {}
    fwds: dict[Tenor, float] = {}
    rows: list[tuple[float, float, float]] = []   # (k, theta, w_obs)

    smiles = [sm for sm in surface.smiles if sm.t >= min_t]
    if len(smiles) < 2:
        log.warning("SSVI %s: <2 tenors above min_t=%.4f — fitting all "
                    "tenors (degraded mode)", surface.pair, min_t)
        smiles = list(surface.smiles)
    for sm in smiles:
        atm = next(n for n in sm.nodes if n.label == "ATM")
        theta = atm.vol ** 2 * sm.t
        thetas[sm.tenor], ts[sm.tenor], fwds[sm.tenor] = theta, sm.t, sm.f
        for n in sm.nodes:
            if n.label == "ATM":
                continue
            rows.append((math.log(n.strike / sm.f), theta,
                         n.vol ** 2 * sm.t))

    karr = np.array([r[0] for r in rows])
    tharr = np.array([r[1] for r in rows])
    wobs = np.array([r[2] for r in rows])

    def resid(p: np.ndarray) -> np.ndarray:
        rho, eta, gamma = p
        phi = eta / tharr ** gamma
        w = 0.5 * tharr * (1 + rho * phi * karr
                           + np.sqrt((phi * karr + rho) ** 2 + 1 - rho ** 2))
        return w - wobs

    sol = least_squares(resid, x0=np.array([-0.2, 0.8, 0.4]),
                        bounds=([-0.999, 1e-3, 0.01], [0.999, 50.0, 0.99]),
                        xtol=1e-12, ftol=1e-12)
    rho, eta, gamma = (float(v) for v in sol.x)

    # report rmse in vol points for comparability with SABR
    w_fit = wobs + sol.fun
    t_arr = np.array([ts[s.tenor] for s in smiles
                      for n in s.nodes if n.label != "ATM"])
    vol_err = (np.sqrt(w_fit / t_arr) - np.sqrt(wobs / t_arr)) * 100.0
    rmse = float(np.sqrt(np.mean(vol_err ** 2)))

    th_sorted = [thetas[t_] for t_ in sorted(ts, key=ts.get)]
    calendar_ok = all(b >= a - 1e-12 for a, b in zip(th_sorted, th_sorted[1:]))
    butterfly_ok = _static_butterfly_ok(list(thetas.values()), rho, eta, gamma)

    if rmse > 0.25:
        log.warning("SSVI %s: poor global fit rmse=%.3f volpts — inspect "
                    "residuals before trusting surface-wide analytics",
                    surface.pair, rmse)
    return SsviFit(pair=surface.pair, rho=rho, eta=eta, gamma=gamma,
                   thetas=thetas, ts=ts, forwards=fwds, rmse=rmse,
                   butterfly_ok=butterfly_ok, calendar_ok=calendar_ok)
