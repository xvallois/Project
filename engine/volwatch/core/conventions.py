"""FX quoting-convention registry.

This module encodes *market practice*, not math. Getting these wrong produces
strike errors of multiple big figures that no unit test of the math will
catch — so the knowledge lives in one auditable place.

Rules encoded for G10 (interbank standard):

* Delta type: SPOT delta for tenors <= 1Y, FORWARD delta beyond (config: switch_tenor).
* Premium adjustment: applies when the option premium is paid in the BASE
  (foreign) currency of the pair. For USD-quoted majors (EURUSD, GBPUSD,
  AUDUSD, NZDUSD) premium is in USD = quote ccy -> NOT premium-adjusted.
  For USD-base pairs (USDJPY, USDCHF, USDCAD) premium is in USD = base ccy
  -> premium-adjusted. EUR crosses (EURJPY, EURGBP, EURCHF): premium in EUR
  = base ccy -> premium-adjusted.
* ATM: delta-neutral straddle (DNS) throughout G10 at these tenors.

References for reviewers: Clark, "Foreign Exchange Option Pricing" (2011),
ch.3; Wystup, "FX Options and Structured Products", §1.5.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

from volwatch.core.models import Tenor


class DeltaType(str, enum.Enum):
    SPOT = "spot"
    FORWARD = "forward"


class AtmType(str, enum.Enum):
    DELTA_NEUTRAL_STRADDLE = "dns"
    AT_THE_MONEY_FORWARD = "atmf"


@dataclass(frozen=True, slots=True)
class PairConventions:
    pair: str
    premium_adjusted: bool
    atm_type: AtmType = AtmType.DELTA_NEUTRAL_STRADDLE
    delta_type_short: DeltaType = DeltaType.SPOT
    delta_type_long: DeltaType = DeltaType.FORWARD
    switch_tenor: Tenor = Tenor.Y1  # tenors > switch use delta_type_long
    points_scale: float = 1e4      # fwd points divisor (JPY pairs: 1e2)

    def delta_type(self, tenor: Tenor) -> DeltaType:
        if tenor.nominal_year_fraction > self.switch_tenor.nominal_year_fraction:
            return self.delta_type_long
        return self.delta_type_short


_PREMIUM_ADJUSTED_TRUE = ("USDJPY", "USDCHF", "USDCAD",
                          "EURJPY", "EURGBP", "EURCHF")
_PREMIUM_ADJUSTED_FALSE = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD")
_JPY_POINTS = ("USDJPY", "EURJPY")


class ConventionRegistry:
    """Lookup of PairConventions; unknown pairs raise loudly (never guess)."""

    def __init__(self) -> None:
        self._table: dict[str, PairConventions] = {}
        for p in _PREMIUM_ADJUSTED_FALSE:
            self._register(p, premium_adjusted=False)
        for p in _PREMIUM_ADJUSTED_TRUE:
            self._register(p, premium_adjusted=True)

    def _register(self, pair: str, premium_adjusted: bool) -> None:
        self._table[pair] = PairConventions(
            pair=pair,
            premium_adjusted=premium_adjusted,
            points_scale=1e2 if pair in _JPY_POINTS else 1e4,
        )

    def get(self, pair: str) -> PairConventions:
        try:
            return self._table[pair.upper()]
        except KeyError:
            raise KeyError(
                f"No conventions registered for {pair!r}. Refusing to guess — "
                "add the pair to core/conventions.py with a reviewed entry."
            ) from None

    def register(self, conv: PairConventions) -> None:
        """Explicit extension point (e.g. EM pairs later)."""
        self._table[conv.pair.upper()] = conv


REGISTRY = ConventionRegistry()
