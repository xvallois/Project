"""SABR smile model (Hagan et al. 2002 lognormal expansion).

Role in the system: per-tenor smile fit whose PARAMETERS are themselves
signal inputs — alpha tracks ATM level, rho the skew (maps to RR), nu the
convexity (maps to BF). beta is FIXED by config (FX desk standard: 1.0);
fitting beta and rho together is ill-posed (they trade off ~1:1 in skew).

Hagan's expansion is an approximation: it degrades for very long expiries,
extreme wings, and very high nu*sqrt(T). At G10 <=1Y, 10d-10d, it is desk
standard. The fit RMSE is always reported; trust it, not the model.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

try:                                    # optional accelerator: pure speed,
    from numba import njit              # zero behavior change; the numpy
    _HAVE_NUMBA = True                  # paths below are the reference.
except ImportError:                     # desk machines without numba run
    _HAVE_NUMBA = False                 # the numpy/math fallbacks.

    def njit(*a, **k):                  # passthrough decorator
        def deco(fn):
            return fn
        return deco if not (len(a) == 1 and callable(a[0])) else a[0]

from volwatch.analytics.surface import StrikeSmile
from volwatch.core.models import Tenor

log = logging.getLogger(__name__)

_EPS = 1e-12


@njit(cache=True, fastmath=True)
def _hagan_scalar(f: float, k: float, t: float, alpha: float, beta: float,
                  rho: float, nu: float) -> float:
    log_fk = math.log(f / k)
    fk_pow = (f * k) ** ((1.0 - beta) / 2.0)
    corr = (((1 - beta) ** 2 / 24.0) * alpha * alpha / (fk_pow * fk_pow)
            + 0.25 * rho * beta * nu * alpha / fk_pow
            + (2.0 - 3.0 * rho * rho) / 24.0 * nu * nu)
    if abs(log_fk) < _EPS:                       # ATM limit: z/x(z) -> 1
        return (alpha / fk_pow) * (1.0 + corr * t)
    z = (nu / alpha) * fk_pow * log_fk
    x = math.log((math.sqrt(1.0 - 2.0 * rho * z + z * z) + z - rho)
                 / (1.0 - rho))
    denom = fk_pow * (1.0 + ((1 - beta) ** 2 / 24.0) * log_fk ** 2
                      + ((1 - beta) ** 4 / 1920.0) * log_fk ** 4)
    return (alpha / denom) * (z / x) * (1.0 + corr * t)


def hagan_vol(f: float, k: float, t: float, alpha: float, beta: float,
              rho: float, nu: float) -> float:
    """Hagan lognormal implied vol (scalar). Handles the ATM limit smoothly.
    Routed through the numba kernel when available; identical math either
    way (the kernel is a verbatim transcription, parity-tested)."""
    if f <= 0 or k <= 0:
        raise ValueError("F and K must be positive")
    return _hagan_scalar(f, k, t, alpha, beta, rho, nu)


def hagan_vol_array(f: float, ks: np.ndarray, t: float, alpha: float,
                    beta: float, rho: float, nu: float) -> np.ndarray:
    """Vectorized Hagan over a strike array — the calibration-residual and
    arb-grid workhorse (one numpy pass replaces N Python-level calls)."""
    ks = np.asarray(ks, dtype=np.float64)
    log_fk = np.log(f / ks)
    fk_pow = (f * ks) ** ((1.0 - beta) / 2.0)
    corr = (((1 - beta) ** 2 / 24.0) * alpha * alpha / (fk_pow * fk_pow)
            + 0.25 * rho * beta * nu * alpha / fk_pow
            + (2.0 - 3.0 * rho * rho) / 24.0 * nu * nu)
    z = (nu / alpha) * fk_pow * log_fk
    safe = np.abs(log_fk) >= _EPS
    z_s = np.where(safe, z, 1.0)                 # avoid 0/0 in masked lanes
    x = np.log((np.sqrt(1.0 - 2.0 * rho * z_s + z_s * z_s) + z_s - rho)
               / (1.0 - rho))
    zx = np.where(safe, z_s / x, 1.0)            # ATM limit: z/x -> 1
    denom = fk_pow * (1.0 + ((1 - beta) ** 2 / 24.0) * log_fk ** 2
                      + ((1 - beta) ** 4 / 1920.0) * log_fk ** 4)
    return (alpha / denom) * zx * (1.0 + corr * t)


@dataclass(frozen=True, slots=True)
class SabrFit:
    pair: str
    tenor: Tenor
    t: float
    f: float
    alpha: float
    beta: float
    rho: float
    nu: float
    rmse: float                     # in vol points, over fitted nodes
    n_nodes: int

    def vol(self, k: float) -> float:
        return hagan_vol(self.f, k, self.t, self.alpha, self.beta,
                         self.rho, self.nu)

    def total_variance(self, k: float) -> float:
        v = self.vol(k)
        return v * v * self.t


def calibrate_sabr(smile: StrikeSmile, beta: float = 1.0,
                   atm_weight: float = 4.0) -> SabrFit:
    """Least-squares fit of (alpha, rho, nu) to the smile nodes.

    ATM is up-weighted: it is the most liquid quote and the anchor every
    downstream consumer assumes is matched near-exactly.
    """
    ks = np.array([n.strike for n in smile.nodes])
    vols = np.array([n.vol for n in smile.nodes])
    w = np.array([atm_weight if n.label == "ATM" else 1.0
                  for n in smile.nodes])
    f, t = smile.f, smile.t

    atm_vol = next(n.vol for n in smile.nodes if n.label == "ATM")
    x0 = np.array([atm_vol * f ** (1.0 - beta),    # alpha ~ ATM level
                   -0.2,                            # rho: mild put skew prior
                   1.0])                            # nu: generic convexity

    def resid(p: np.ndarray) -> np.ndarray:
        a, r, n_ = p
        return w * (hagan_vol_array(f, ks, t, a, beta, r, n_) - vols)

    sol = least_squares(
        resid, x0,
        bounds=([1e-4, -0.999, 1e-4], [5.0, 0.999, 10.0]),
        xtol=1e-12, ftol=1e-12)
    a, r, n_ = sol.x
    rmse = float(np.sqrt(np.mean(((sol.fun / w) * 100.0) ** 2)))
    if rmse > 0.10:
        log.warning("SABR %s %s: poor fit rmse=%.3f volpts",
                    smile.pair, smile.tenor.value, rmse)
    return SabrFit(pair=smile.pair, tenor=smile.tenor, t=t, f=f,
                   alpha=float(a), beta=beta, rho=float(r), nu=float(n_),
                   rmse=rmse, n_nodes=len(ks))
