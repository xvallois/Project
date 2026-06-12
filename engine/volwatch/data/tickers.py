"""Ticker construction from config templates.

Bloomberg tickers are built ONLY here, from templates in config/bloomberg.yaml,
and every generated ticker carries a TickerMeta so responses can be mapped
back to (kind, pair, tenor, delta) without string-parsing heuristics.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

import yaml

from volwatch.core.models import Tenor


class TickerKind(str, enum.Enum):
    SPOT = "spot"
    FORWARD = "forward"
    ATM = "atm_vol"
    RR = "rr"
    BF = "bf"
    RATE = "rate"


@dataclass(frozen=True, slots=True)
class TickerMeta:
    ticker: str
    kind: TickerKind
    pair: str | None = None
    tenor: Tenor | None = None
    delta: int | None = None        # 25 or 10 for RR/BF
    currency: str | None = None     # for rates
    source: str | None = None       # e.g. "SOFR OIS"


class TickerFactory:
    """Builds the full request universe and the ticker->meta reverse map."""

    def __init__(self, bbg_config: dict) -> None:
        self._t = bbg_config["tickers"]
        self._rates_cfg = bbg_config.get("rates", {})

    @classmethod
    def from_yaml(cls, path: str | Path = "config/bloomberg.yaml") -> "TickerFactory":
        return cls(yaml.safe_load(Path(path).read_text()))

    # -- individual builders ------------------------------------------------
    def spot(self, pair: str) -> TickerMeta:
        return TickerMeta(self._t["spot"].format(pair=pair),
                          TickerKind.SPOT, pair=pair)

    def forward(self, pair: str, tenor: Tenor) -> TickerMeta:
        return TickerMeta(self._t["forward"].format(pair=pair, tenor=tenor.value),
                          TickerKind.FORWARD, pair=pair, tenor=tenor)

    def atm(self, pair: str, tenor: Tenor) -> TickerMeta:
        return TickerMeta(self._t["atm_vol"].format(pair=pair, tenor=tenor.value),
                          TickerKind.ATM, pair=pair, tenor=tenor)

    def rr(self, pair: str, delta: int, tenor: Tenor) -> TickerMeta:
        return TickerMeta(
            self._t["rr"].format(pair=pair, delta=delta, tenor=tenor.value),
            TickerKind.RR, pair=pair, tenor=tenor, delta=delta)

    def bf(self, pair: str, delta: int, tenor: Tenor) -> TickerMeta:
        return TickerMeta(
            self._t["bf"].format(pair=pair, delta=delta, tenor=tenor.value),
            TickerKind.BF, pair=pair, tenor=tenor, delta=delta)

    # -- universe -----------------------------------------------------------
    def universe(self, pairs: list[str], tenors: list[Tenor]) -> dict[str, TickerMeta]:
        """Full snap universe: spot, forwards (>=1W), ATM/RR/BF grid, rates."""
        out: dict[str, TickerMeta] = {}

        def add(m: TickerMeta) -> None:
            out[m.ticker] = m

        for pair in pairs:
            add(self.spot(pair))
            for tenor in tenors:
                if tenor is not Tenor.ON:        # ON outright fwd: not snapped v1
                    add(self.forward(pair, tenor))
                add(self.atm(pair, tenor))
                for delta in (25, 10):
                    add(self.rr(pair, delta, tenor))
                    add(self.bf(pair, delta, tenor))

        for ccy, cfg in self._rates_cfg.items():
            for tenor_s, ticker in cfg["tickers"].items():
                add(TickerMeta(ticker, TickerKind.RATE, currency=ccy,
                               tenor=Tenor(tenor_s), source=cfg["source"]))
        return out
