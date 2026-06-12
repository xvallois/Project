"""Shared snapshot assembly: {ticker: PX_LAST...} -> MarketSnapshot.

Extracted so the refdata adapter (bloomberg.py) and the BQL adapter
(bql_provider.py) share one parsing path — a convention bug should only be
possible once.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from volwatch.core.conventions import REGISTRY
from volwatch.core.models import (
    ForwardPoints, MarketSnapshot, QuoteStatus, RatePoint, SpotQuote, Tenor,
    VolQuote, VolSurface,
)
from volwatch.data.tickers import TickerKind, TickerMeta

log = logging.getLogger(__name__)


def assemble_snapshot(values: dict[str, dict[str, float]],
                      universe: dict[str, TickerMeta],
                      pairs: list[str], tenors: list[Tenor],
                      ts: datetime) -> MarketSnapshot:
    spots: dict[str, SpotQuote] = {}
    fwds: dict[str, list[ForwardPoints]] = defaultdict(list)
    legs: dict[tuple[str, Tenor], dict[str, float]] = defaultdict(dict)
    rates: dict[str, list[RatePoint]] = defaultdict(list)

    for ticker, meta in universe.items():
        px = values.get(ticker, {})
        last = px.get("PX_LAST")
        if last is None:
            log.warning("missing PX_LAST for %s (%s)", ticker,
                        meta.kind.value)
            continue
        if meta.kind is TickerKind.SPOT:
            spots[meta.pair] = SpotQuote(pair=meta.pair, mid=last, ts=ts,
                                         bid=px.get("PX_BID"),
                                         ask=px.get("PX_ASK"))
        elif meta.kind is TickerKind.FORWARD:
            fwds[meta.pair].append(ForwardPoints(
                pair=meta.pair, tenor=meta.tenor, points=last,
                outright=None, ts=ts))
        elif meta.kind is TickerKind.ATM:
            legs[(meta.pair, meta.tenor)]["atm"] = last
        elif meta.kind is TickerKind.RR:
            legs[(meta.pair, meta.tenor)][f"rr{meta.delta}"] = last
        elif meta.kind is TickerKind.BF:
            legs[(meta.pair, meta.tenor)][f"bf{meta.delta}"] = last
        elif meta.kind is TickerKind.RATE:
            rates[meta.currency].append(RatePoint(
                currency=meta.currency, tenor=meta.tenor,
                rate=last / 100.0, source=meta.source or "", ts=ts))

    fwds_out = {
        pair: tuple(
            ForwardPoints(pair=f.pair, tenor=f.tenor, points=f.points,
                          outright=(spots[pair].mid
                                    + f.points / REGISTRY.get(pair).points_scale)
                          if pair in spots else None,
                          ts=f.ts, status=f.status)
            for f in fs)
        for pair, fs in fwds.items()}

    vols: dict[str, VolSurface] = {}
    for pair in pairs:
        quotes = []
        for tenor in tenors:
            leg = legs.get((pair, tenor), {})
            if "atm" not in leg:
                log.warning("no ATM for %s %s — tenor dropped this snap",
                            pair, tenor.value)
                continue
            partial = not {"rr25", "bf25"} <= leg.keys()
            quotes.append(VolQuote(
                pair=pair, tenor=tenor, atm=leg["atm"],
                rr25=leg.get("rr25", 0.0), bf25=leg.get("bf25", 0.0),
                rr10=leg.get("rr10"), bf10=leg.get("bf10"), ts=ts,
                status=QuoteStatus.PARTIAL if partial else QuoteStatus.OK))
        if quotes:
            vols[pair] = VolSurface(pair=pair, asof=ts, quotes=tuple(quotes))

    return MarketSnapshot(asof=ts, spots=spots, forwards=fwds_out,
                          vols=vols,
                          rates={k: tuple(v) for k, v in rates.items()})
