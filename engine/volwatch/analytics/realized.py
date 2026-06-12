"""Realized volatility estimators on daily OHLC.

All annualized with sqrt(252), returned in DECIMAL (0.075 = 7.5%).

Estimator selection guidance (efficiency = variance reduction vs close-close
on the same window, under GBM):

  close_close   the benchmark; unbiased, noisiest (~1x).
  parkinson     range-based, ~5x efficient; biased LOW if there are price
                jumps the range doesn't straddle, and by discrete monitoring.
  garman_klass  OHLC, ~7x efficient; assumes zero drift and no overnight gap.
  yang_zhang    handles overnight gaps + drift; the default for FX where the
                weekend gap is real. (~8x efficient.)

Convention: close-close uses the ZERO-MEAN estimator (sum r^2 / n, no mean
subtraction) — standard for vol trading because the drift over short windows
is noise, and subtracting it biases short-window vol low.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from volwatch.core.models import Tenor

log = logging.getLogger(__name__)

ANN = 252.0

#: tenor -> matched realized window in trading days (for IV-RV comparisons)
TENOR_WINDOW: dict[Tenor, int] = {
    # ON maps to 5d: a 1-day 'realized vol' is a single squared return
    # (pure noise). 5d is the shortest stable proxy; documented basis.
    Tenor.ON: 5, Tenor.W1: 5, Tenor.W2: 10, Tenor.M1: 21, Tenor.M2: 42,
    Tenor.M3: 63, Tenor.M6: 126, Tenor.M9: 189, Tenor.Y1: 252,
}


def _validate(df: pd.DataFrame, n: int, need: list[str]) -> pd.DataFrame:
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"OHLC frame missing columns {missing}")
    tail = df.dropna(subset=need).tail(n)
    if len(tail) < n:
        raise ValueError(f"need {n} clean rows, have {len(tail)}")
    return tail


def close_close(df: pd.DataFrame, n: int) -> float:
    d = _validate(df, n + 1, ["close"])
    r = np.log(d["close"]).diff().dropna().to_numpy()
    return math.sqrt(ANN * np.mean(r * r))


def parkinson(df: pd.DataFrame, n: int) -> float:
    d = _validate(df, n, ["high", "low"])
    hl = np.log(d["high"] / d["low"]).to_numpy()
    return math.sqrt(ANN * np.mean(hl * hl) / (4.0 * math.log(2.0)))


def garman_klass(df: pd.DataFrame, n: int) -> float:
    d = _validate(df, n, ["open", "high", "low", "close"])
    hl = np.log(d["high"] / d["low"]).to_numpy()
    co = np.log(d["close"] / d["open"]).to_numpy()
    var = np.mean(0.5 * hl * hl - (2.0 * math.log(2.0) - 1.0) * co * co)
    return math.sqrt(ANN * max(var, 0.0))


def yang_zhang(df: pd.DataFrame, n: int) -> float:
    d = _validate(df, n + 1, ["open", "high", "low", "close"])
    o, h, lo, c = (np.log(d[x].to_numpy()) for x in
                   ("open", "high", "low", "close"))
    over = o[1:] - c[:-1]                      # overnight (close -> next open)
    oc = c[1:] - o[1:]                         # open -> close
    h_, l_, o_, c_ = h[1:], lo[1:], o[1:], c[1:]
    rs = (h_ - c_) * (h_ - o_) + (l_ - c_) * (l_ - o_)   # Rogers-Satchell

    m = len(oc)
    var_over = np.var(over, ddof=1)
    var_oc = np.var(oc, ddof=1)
    var_rs = np.mean(rs)
    k = 0.34 / (1.34 + (m + 1) / (m - 1))
    return math.sqrt(ANN * (var_over + k * var_oc + (1 - k) * var_rs))


_ESTIMATORS = {"close_close": close_close, "parkinson": parkinson,
               "garman_klass": garman_klass, "yang_zhang": yang_zhang}


@dataclass(frozen=True)
class RealizedVolSet:
    """All estimators x all windows for one pair. Values decimal annualized."""

    pair: str
    values: dict[str, dict[int, float]]        # estimator -> window -> vol

    def get(self, estimator: str, window: int) -> float:
        return self.values[estimator][window]

    def matched(self, tenor: Tenor,
                estimator: str = "yang_zhang") -> float:
        """Realized vol over the window matched to a quoted tenor."""
        return self.get(estimator, TENOR_WINDOW[tenor])


def compute_realized(pair: str, ohlc: pd.DataFrame,
                     windows: list[int] | None = None) -> RealizedVolSet:
    windows = windows or [5, 10, 21, 42, 63, 126, 189, 252]
    out: dict[str, dict[int, float]] = {}
    for name, fn in _ESTIMATORS.items():
        out[name] = {}
        for w in windows:
            try:
                out[name][w] = fn(ohlc, w)
            except ValueError as e:
                log.debug("%s %s w=%d skipped: %s", pair, name, w, e)
    return RealizedVolSet(pair=pair, values=out)


def rolling_close_close(ohlc: pd.DataFrame, window: int) -> pd.Series:
    """Rolling annualized close-close vol series (zero-mean), indexed like
    `ohlc`. Used for z-scoring IV-RV spreads through history — CC is chosen
    for the ROLLING series (cheap, unbiased); point-in-time carry still
    reports Yang-Zhang."""
    r = np.log(ohlc["close"]).diff()
    return np.sqrt(ANN * (r * r).rolling(window).mean())
