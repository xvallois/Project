"""Core domain models for volwatch.

Every module in the system communicates through the immutable, typed objects
defined here. Nothing downstream should ever see a raw Bloomberg response or
an untyped dict.

Conventions note: a VolQuote stores the market quote vector (ATM, RR, BF) in
*vol points* (e.g. 7.25 means 7.25%). Smile reconstruction here uses the
standard smile-butterfly identities; the broker-strangle correction is a
deliberate Stage 2+ concern (see ARCHITECTURE.md §4.1).
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, Mapping

import pandas as pd

SCHEMA_VERSION = 1


class Tenor(str, enum.Enum):
    """Standard quoted tenor grid. Order of declaration == curve order."""

    ON = "ON"
    W1 = "1W"
    W2 = "2W"
    M1 = "1M"
    M2 = "2M"
    M3 = "3M"
    M6 = "6M"
    M9 = "9M"
    Y1 = "1Y"

    @property
    def nominal_year_fraction(self) -> float:
        """Calendar-free approximation, used only for sorting/plot axes.

        Real year fractions come from actual expiry dates (core.calendars);
        analytics must never use this for pricing.
        """
        return _TENOR_YF[self]

    @classmethod
    def ordered(cls) -> list["Tenor"]:
        return list(cls)


_TENOR_YF: dict[Tenor, float] = {
    Tenor.ON: 1 / 365,
    Tenor.W1: 7 / 365,
    Tenor.W2: 14 / 365,
    Tenor.M1: 30 / 365,
    Tenor.M2: 61 / 365,
    Tenor.M3: 91 / 365,
    Tenor.M6: 182 / 365,
    Tenor.M9: 274 / 365,
    Tenor.Y1: 1.0,
}


class QuoteStatus(enum.Flag):
    """Bitmask quality flags. Bad data is flagged and stored, never repaired."""

    OK = 0
    STALE = enum.auto()
    OUTLIER = enum.auto()
    PARTIAL = enum.auto()  # some legs of the quote vector missing


@dataclass(frozen=True, slots=True)
class SpotQuote:
    pair: str
    mid: float
    ts: datetime
    bid: float | None = None
    ask: float | None = None
    status: QuoteStatus = QuoteStatus.OK


@dataclass(frozen=True, slots=True)
class ForwardPoints:
    pair: str
    tenor: Tenor
    points: float  # in market points convention (scaled by data layer)
    outright: float | None  # spot + points/scale, filled by data layer
    ts: datetime
    status: QuoteStatus = QuoteStatus.OK


@dataclass(frozen=True, slots=True)
class RatePoint:
    currency: str
    tenor: Tenor
    rate: float  # decimal, e.g. 0.0525
    source: str  # e.g. "SOFR OIS"
    ts: datetime
    status: QuoteStatus = QuoteStatus.OK


@dataclass(frozen=True, slots=True)
class VolQuote:
    """One tenor's quote vector: ATM, 25/10-delta risk reversals & butterflies.

    All values in vol points (percent). RR sign convention: RR = call - put.
    """

    pair: str
    tenor: Tenor
    atm: float
    rr25: float
    bf25: float
    rr10: float | None
    bf10: float | None
    ts: datetime
    status: QuoteStatus = QuoteStatus.OK

    def smile(self) -> dict[str, float]:
        """Reconstruct the 5-point smile in delta space (smile-BF identity).

        sigma(25C) = ATM + BF25 + RR25/2
        sigma(25P) = ATM + BF25 - RR25/2     (and same for 10-delta)
        """
        out = {
            "25P": self.atm + self.bf25 - self.rr25 / 2.0,
            "ATM": self.atm,
            "25C": self.atm + self.bf25 + self.rr25 / 2.0,
        }
        if self.rr10 is not None and self.bf10 is not None:
            out["10P"] = self.atm + self.bf10 - self.rr10 / 2.0
            out["10C"] = self.atm + self.bf10 + self.rr10 / 2.0
        return out


@dataclass(frozen=True, slots=True)
class VolSurface:
    """All vol quotes for one pair at one instant, in market quote space."""

    pair: str
    asof: datetime
    quotes: tuple[VolQuote, ...]

    def __post_init__(self) -> None:
        if any(q.pair != self.pair for q in self.quotes):
            raise ValueError(f"VolSurface[{self.pair}]: mixed-pair quotes")

    def tenors(self) -> list[Tenor]:
        return sorted((q.tenor for q in self.quotes),
                      key=lambda t: t.nominal_year_fraction)

    def get(self, tenor: Tenor) -> VolQuote:
        for q in self.quotes:
            if q.tenor == tenor:
                return q
        raise KeyError(f"{self.pair}: no quote for {tenor.value}")

    def atm_curve(self) -> dict[Tenor, float]:
        return {q.tenor: q.atm for q in self.quotes}

    def __iter__(self) -> Iterator[VolQuote]:
        return iter(self.quotes)


@dataclass(frozen=True, slots=True)
class Position:
    """Book position placeholder (book ingestion planned — see settings.yaml).

    Minimal fields now so the AI/risk layers can be written against a stable
    contract; enrichment (greeks snap, premium ccy, cut) comes with the book
    adapter stage.
    """

    trade_id: str
    pair: str
    structure: str            # e.g. "25d risk reversal", "vanilla call"
    expiry: datetime
    strike: float | None
    notional_base: float      # signed, base-ccy units
    vega: float | None = None # in quote-ccy per vol point, if known


@dataclass(frozen=True)
class MarketSnapshot:
    """One full sweep of the configured universe at time `asof`.

    The atomic unit of history: immutable, id-stamped, schema-versioned.
    """

    asof: datetime
    spots: Mapping[str, SpotQuote]
    forwards: Mapping[str, tuple[ForwardPoints, ...]]
    vols: Mapping[str, VolSurface]
    rates: Mapping[str, tuple[RatePoint, ...]]
    snapshot_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    schema_version: int = SCHEMA_VERSION
    git_sha: str = "dev"

    # ------------------------------------------------------------------ #
    # Persistence projection. The store writes these frames to Parquet.   #
    # ------------------------------------------------------------------ #
    def to_frames(self) -> dict[str, pd.DataFrame]:
        meta = {
            "snapshot_id": self.snapshot_id,
            "asof": self.asof,
            "schema_version": self.schema_version,
            "git_sha": self.git_sha,
        }
        spot_rows = [
            {**meta, "pair": s.pair, "mid": s.mid, "bid": s.bid, "ask": s.ask,
             "ts": s.ts, "status": s.status.value}
            for s in self.spots.values()
        ]
        fwd_rows = [
            {**meta, "pair": f.pair, "tenor": f.tenor.value, "points": f.points,
             "outright": f.outright, "ts": f.ts, "status": f.status.value}
            for fs in self.forwards.values() for f in fs
        ]
        vol_rows = [
            {**meta, "pair": q.pair, "tenor": q.tenor.value, "atm": q.atm,
             "rr25": q.rr25, "bf25": q.bf25, "rr10": q.rr10, "bf10": q.bf10,
             "ts": q.ts, "status": q.status.value}
            for surf in self.vols.values() for q in surf
        ]
        rate_rows = [
            {**meta, "currency": r.currency, "tenor": r.tenor.value,
             "rate": r.rate, "source": r.source, "ts": r.ts,
             "status": r.status.value}
            for rs in self.rates.values() for r in rs
        ]
        return {
            "spot": pd.DataFrame(spot_rows),
            "forward": pd.DataFrame(fwd_rows),
            "vol": pd.DataFrame(vol_rows),
            "rate": pd.DataFrame(rate_rows),
        }

    @staticmethod
    def vol_surface_from_frame(df: pd.DataFrame, pair: str) -> VolSurface:
        """Rebuild a VolSurface from the persisted `vol` frame (round-trip)."""
        sub = df[df["pair"] == pair]
        if sub.empty:
            raise KeyError(f"no vol rows for {pair}")
        quotes = tuple(
            VolQuote(
                pair=row.pair, tenor=Tenor(row.tenor), atm=row.atm,
                rr25=row.rr25, bf25=row.bf25,
                rr10=None if pd.isna(row.rr10) else row.rr10,
                bf10=None if pd.isna(row.bf10) else row.bf10,
                ts=row.ts.to_pydatetime() if hasattr(row.ts, "to_pydatetime") else row.ts,
                status=QuoteStatus(int(row.status)),
            )
            for row in sub.itertuples()
        )
        asof = sub["asof"].iloc[0]
        asof = asof.to_pydatetime() if hasattr(asof, "to_pydatetime") else asof
        return VolSurface(pair=pair, asof=asof, quotes=quotes)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
