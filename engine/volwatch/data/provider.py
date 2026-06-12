"""Market data provider interface and the mock implementation.

`MarketDataProvider` is the ONLY seam between the outside world and the
system. The Bloomberg adapter and the mock both implement it; everything
downstream is provider-agnostic, which is what lets the full pipeline run
in CI without a Terminal.
"""
from __future__ import annotations

import abc
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from volwatch.core.conventions import REGISTRY
from volwatch.core.models import (
    ForwardPoints, MarketSnapshot, RatePoint, SpotQuote, Tenor, VolQuote,
    VolSurface, utcnow,
)

log = logging.getLogger(__name__)


class MarketDataProvider(abc.ABC):
    """Contract every data source must satisfy."""

    @abc.abstractmethod
    def snapshot(self, pairs: list[str], tenors: list[Tenor]) -> MarketSnapshot:
        """One full sweep of the universe. Must never raise on partial data:
        missing quotes are flagged, the snapshot is still returned."""

    @abc.abstractmethod
    def history_ohlc(self, pair: str, start: datetime,
                     end: datetime) -> pd.DataFrame:
        """Daily OHLC for realized-vol estimators.
        Columns: [date, open, high, low, close]."""


# --------------------------------------------------------------------------- #
# Mock provider                                                                #
# --------------------------------------------------------------------------- #
_BASE_SPOT = {"EURUSD": 1.0850, "GBPUSD": 1.2700, "USDJPY": 155.00,
              "USDCHF": 0.8900, "USDCAD": 1.3600, "AUDUSD": 0.6600,
              "NZDUSD": 0.6100, "EURJPY": 168.20, "EURGBP": 0.8540}
# (level_1m, slope_to_1y) in vol pts — plausible regimes, not live marks
_BASE_ATM = {"EURUSD": (7.2, 0.8), "GBPUSD": (8.0, 0.7), "USDJPY": (10.5, 0.5),
             "USDCHF": (7.0, 0.6), "USDCAD": (6.2, 0.6), "AUDUSD": (9.5, 0.6),
             "NZDUSD": (10.0, 0.6), "EURJPY": (9.8, 0.6), "EURGBP": (6.0, 0.5)}
# Typical RR25 sign/level: JPY pairs strongly negative (downside/JPY-call bid)
_BASE_RR25 = {"EURUSD": -0.35, "GBPUSD": -0.55, "USDJPY": -1.60,
              "USDCHF": -0.50, "USDCAD": 0.35, "AUDUSD": -0.90,
              "NZDUSD": -0.80, "EURJPY": -1.40, "EURGBP": -0.25}


class MockProvider(MarketDataProvider):
    """Deterministic-but-evolving synthetic market.

    Seeded RNG; each `snapshot()` call random-walks the state slightly so
    successive snaps differ realistically. `corrupt=True` injects defects
    (stale/insane quotes) so validator behaviour can be tested end-to-end.
    """

    def __init__(self, seed: int = 42, corrupt: bool = False,
                 clock=None) -> None:
        """clock: optional callable -> datetime, injectable so tests can
        synthesize daily history. Defaults to utcnow."""
        self._rng = np.random.default_rng(seed)
        self._corrupt = corrupt
        self._clock = clock or utcnow
        self._drift: dict[str, float] = {}        # accumulated vol drift / pair

    def snapshot(self, pairs: list[str], tenors: list[Tenor]) -> MarketSnapshot:
        ts = self._clock()
        spots, forwards, vols, rates = {}, {}, {}, {}
        for pair in pairs:
            conv = REGISTRY.get(pair)
            self._drift[pair] = self._drift.get(pair, 0.0) + \
                self._rng.normal(0, 0.03)
            spot_mid = _BASE_SPOT[pair] * (1 + self._rng.normal(0, 5e-4))
            spots[pair] = SpotQuote(pair=pair, mid=round(spot_mid, 5), ts=ts,
                                    bid=round(spot_mid * 0.99995, 5),
                                    ask=round(spot_mid * 1.00005, 5))
            fps = []
            for tenor in tenors:
                if tenor is Tenor.ON:
                    continue
                pts = -15.0 * tenor.nominal_year_fraction * \
                    (100 if conv.points_scale == 1e2 else 1) \
                    + self._rng.normal(0, 0.5)
                fps.append(ForwardPoints(
                    pair=pair, tenor=tenor, points=round(pts, 3),
                    outright=round(spot_mid + pts / conv.points_scale, 5), ts=ts))
            forwards[pair] = tuple(fps)
            vols[pair] = self._surface(pair, tenors, ts)

        for ccy, base in (("USD", 0.0420), ("EUR", 0.0215)):
            rates[ccy] = tuple(
                RatePoint(currency=ccy, tenor=t,
                          rate=round(base + 0.001 * t.nominal_year_fraction
                                     + self._rng.normal(0, 1e-4), 6),
                          source="MOCK OIS", ts=ts)
                for t in (Tenor.M1, Tenor.M3, Tenor.M6, Tenor.Y1))

        snap = MarketSnapshot(asof=ts, spots=spots, forwards=forwards,
                              vols=vols, rates=rates)
        if self._corrupt:
            snap = self._inject_defects(snap)
        return snap

    def _surface(self, pair: str, tenors: list[Tenor], ts: datetime) -> VolSurface:
        lvl, slope = _BASE_ATM[pair]
        rr_base = _BASE_RR25[pair]
        quotes = []
        for tenor in tenors:
            yf = tenor.nominal_year_fraction
            atm = lvl + slope * np.sqrt(yf) + self._drift[pair] \
                + self._rng.normal(0, 0.04)
            rr25 = rr_base * (0.6 + 0.4 * np.sqrt(yf / 0.25)) \
                + self._rng.normal(0, 0.03)
            bf25 = 0.15 + 0.20 * np.sqrt(yf) + self._rng.normal(0, 0.015)
            quotes.append(VolQuote(
                pair=pair, tenor=tenor, atm=round(float(atm), 3),
                rr25=round(float(rr25), 3), bf25=round(float(bf25), 3),
                rr10=round(float(rr25 * 1.85), 3),
                bf10=round(float(bf25 * 3.2), 3), ts=ts))
        return VolSurface(pair=pair, asof=ts, quotes=tuple(quotes))

    def _inject_defects(self, snap: MarketSnapshot) -> MarketSnapshot:
        """Make EURUSD 1M ATM insane and GBPUSD spot stale (for validator tests)."""
        vols = dict(snap.vols)
        eur = vols["EURUSD"]
        bad = tuple(
            VolQuote(pair=q.pair, tenor=q.tenor,
                     atm=95.0 if q.tenor is Tenor.M1 else q.atm,
                     rr25=q.rr25, bf25=q.bf25, rr10=q.rr10, bf10=q.bf10,
                     ts=q.ts, status=q.status)
            for q in eur)
        vols["EURUSD"] = VolSurface(pair="EURUSD", asof=eur.asof, quotes=bad)
        spots = dict(snap.spots)
        g = spots["GBPUSD"]
        spots["GBPUSD"] = SpotQuote(pair=g.pair, mid=g.mid, bid=g.bid,
                                    ask=g.ask, ts=g.ts - timedelta(hours=3))
        return MarketSnapshot(asof=snap.asof, spots=spots,
                              forwards=snap.forwards, vols=vols,
                              rates=snap.rates,
                              snapshot_id=snap.snapshot_id)

    def history_ohlc(self, pair: str, start: datetime,
                     end: datetime) -> pd.DataFrame:
        days = pd.bdate_range(start, end)
        s0 = _BASE_SPOT[pair]
        daily_vol = _BASE_ATM[pair][0] / 100 / np.sqrt(252)
        rets = self._rng.normal(0, daily_vol, len(days))
        close = s0 * np.exp(np.cumsum(rets))
        intr = np.abs(self._rng.normal(0, daily_vol, len(days)))
        return pd.DataFrame({
            "date": days,
            "open": close * np.exp(-rets / 2),
            "high": close * np.exp(intr),
            "low": close * np.exp(-intr),
            "close": close,
        })
