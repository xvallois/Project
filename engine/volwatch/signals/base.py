"""Signal framework.

Every signal MUST declare, as class attributes: `math` (the formula),
`intuition` (why it should work), `edge` (what is being earned), and
`failure_modes` (what kills it). The base class refuses to register a
signal without them — requirement, not convention — and the dashboard
renders them next to every firing. A signal nobody can explain is a bug
with a Sharpe ratio.

SignalInstance scores are z-scores against the signal's own history so
that 'rich' always means 'rich vs its own past', comparable across signals.
"""
from __future__ import annotations

import abc
import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Type

import numpy as np
import pandas as pd

from volwatch.analytics.carry import CarryReport
from volwatch.analytics.fit import CalibratedSurface
from volwatch.analytics.forward_vol import ForwardVol
from volwatch.analytics.realized import RealizedVolSet
from volwatch.core.models import MarketSnapshot, Tenor
from volwatch.data.store import ParquetStore

log = logging.getLogger(__name__)


class Direction(str, enum.Enum):
    BUY_VOL = "buy_vol"
    SELL_VOL = "sell_vol"
    BUY_SKEW = "buy_skew"          # buy RR (calls over puts)
    SELL_SKEW = "sell_skew"
    BUY_CORR = "buy_corr"
    SELL_CORR = "sell_corr"
    BUY_FWD_VOL = "buy_fwd_vol"
    SELL_FWD_VOL = "sell_fwd_vol"


@dataclass(frozen=True)
class SignalInstance:
    signal: str
    pair: str
    structure: str                 # human structure, e.g. "3M ATM straddle"
    direction: Direction
    score: float                   # z-score vs own history (signed)
    value: float                   # the raw metric, signal-defined units
    edge_estimate: float           # vol pts of excess vs historical norm
    asof: datetime
    tenors: tuple[Tenor, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return (f"[{self.signal}] {self.pair} {self.structure} "
                f"{self.direction.value} z={self.score:+.2f} "
                f"edge~{self.edge_estimate:.2f}vp")


@dataclass
class SignalContext:
    """Everything a signal may consume. Built once per cycle, shared."""
    asof: datetime
    snapshot: MarketSnapshot
    calibrated: dict[str, CalibratedSurface]
    carry: dict[str, CarryReport]
    fwd_vols: dict[str, list[ForwardVol]]
    realized: dict[str, RealizedVolSet]
    ohlc: dict[str, pd.DataFrame]
    history: "HistoryView"
    ts: dict[Tenor, float]


class HistoryView:
    """Daily series from the store, OK-status rows only, last snap per day.

    `cutoff` (a date) truncates the view: in backtest replay, a signal
    evaluated as-of day D must see NOTHING after D. Lookahead in z-score
    history is the classic way backtests lie.

    Two modes:
      * lazy (default): one DuckDB query per (pair, tenor) on demand —
        fine for a live cycle (~30 queries).
      * preloaded: `HistoryView.preload(store)` pulls the ENTIRE daily
        panel in ONE query; `with_cutoff(d)` then yields per-day views
        sharing the cached panel for free. This is what makes backtests
        O(1) queries instead of O(days x pairs x tenors)."""

    def __init__(self, store: ParquetStore | None, cutoff=None,
                 _panel: pd.DataFrame | None = None) -> None:
        self._store = store
        self._cutoff = cutoff
        self._panel = _panel        # columns: pair, tenor, date, atm, rr25, bf25

    @classmethod
    def preload(cls, store: ParquetStore, cutoff=None) -> "HistoryView":
        df = store.query(
            'SELECT pair, tenor, "asof", atm, rr25, bf25 FROM vol '
            "WHERE status = 0")
        if df.empty:
            panel = pd.DataFrame(columns=["pair", "tenor", "date",
                                          "atm", "rr25", "bf25"])
        else:
            df["date"] = pd.to_datetime(df["asof"]).dt.date
            panel = (df.sort_values("asof")
                       .groupby(["pair", "tenor", "date"], as_index=False)
                       .last()[["pair", "tenor", "date",
                                "atm", "rr25", "bf25"]])
        return cls(store=None, cutoff=cutoff, _panel=panel)

    def with_cutoff(self, cutoff) -> "HistoryView":
        """Same data, different no-lookahead boundary. O(1)."""
        return HistoryView(self._store, cutoff=cutoff, _panel=self._panel)

    def series(self, pair: str, tenor: Tenor, fld: str) -> pd.Series:
        if fld not in ("atm", "rr25", "bf25"):
            raise ValueError(f"unsupported history field {fld!r}")
        if self._panel is not None:
            sub = self._panel[(self._panel["pair"] == pair)
                              & (self._panel["tenor"] == tenor.value)]
            if self._cutoff is not None:
                sub = sub[sub["date"] <= self._cutoff]
            return sub.set_index("date")[fld]
        df = self._store.atm_history(pair, tenor.value)
        if df.empty:
            return pd.Series(dtype=float)
        df = df[df["status"] == 0]
        if self._cutoff is not None:
            df = df[pd.to_datetime(df["asof"]).dt.date <= self._cutoff]
        df["date"] = pd.to_datetime(df["asof"]).dt.date
        return df.groupby("date")[fld].last()


def zscore(history: pd.Series, current: float, min_obs: int = 20,
           robust: bool = False) -> float | None:
    """Z of `current` vs `history`. None if history too short — a signal
    with no history must stay silent, not fire on garbage statistics."""
    h = history.dropna()
    if len(h) < min_obs:
        return None
    if robust:
        med = h.median()
        mad = (h - med).abs().median() * 1.4826
        return None if mad < 1e-12 else float((current - med) / mad)
    sd = h.std()
    return None if sd < 1e-12 else float((current - h.mean()) / sd)


# --------------------------------------------------------------------------- #
_REQUIRED_DOC = ("math", "intuition", "edge", "failure_modes")
REGISTRY: dict[str, Type["Signal"]] = {}


class Signal(abc.ABC):
    name: str = ""

    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params

    def __init_subclass__(cls, **kw: Any) -> None:
        super().__init_subclass__(**kw)
        missing = [a for a in _REQUIRED_DOC
                   if not getattr(cls, a, "").strip()]
        if missing or not cls.name:
            raise TypeError(
                f"Signal {cls.__name__} missing required attributes: "
                f"{missing or ['name']} — every signal ships with its math, "
                "intuition, edge and failure modes.")
        REGISTRY[cls.name] = cls

    @abc.abstractmethod
    def compute(self, ctx: SignalContext) -> list[SignalInstance]: ...

    # documentation contract (enforced above)
    math: str = ""
    intuition: str = ""
    edge: str = ""
    failure_modes: str = ""
