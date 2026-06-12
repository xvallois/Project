"""BQL adapter: server-side bulk queries to cut data consumption.

Why BQL alongside refdata:
  * ONE BQL request retrieves the entire universe (one universe list,
    one data item) computed server-side, vs per-security refdata hits.
    On metered Desktop/Server API setups this is a material daily-hit
    saving at 5-minute snap frequency (~900 securities x 288 snaps).
  * BQL can also screen/aggregate server-side (future: pull only quotes
    that CHANGED since the last snap).

Availability caveat (honest): the `bql` Python package ships with
Bloomberg's BQuant environment and selected SAPI licenses — it is NOT a
pip-installable public package. If `import bql` fails on the desk
machine, stay on BloombergProvider; this adapter exists so the switch is
one config word when the license is there.

Same MarketDataProvider contract, same TickerFactory universe, same
assemble_snapshot parser as the refdata path.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from volwatch.core.models import MarketSnapshot, Tenor, utcnow
from volwatch.data.assemble import assemble_snapshot
from volwatch.data.provider import MarketDataProvider
from volwatch.data.tickers import TickerFactory

log = logging.getLogger(__name__)


class BqlProvider(MarketDataProvider):
    def __init__(self, config_path: str | Path = "config/bloomberg.yaml") -> None:
        try:
            import bql  # noqa: F401 — BQuant/SAPI environments only
        except ImportError as e:
            raise RuntimeError(
                "bql package unavailable — it ships with BQuant/SAPI, not "
                "pip. Use BloombergProvider (refdata) on this machine."
            ) from e
        self._bql = bql
        self._svc = bql.Service()
        cfg = yaml.safe_load(Path(config_path).read_text())
        self._factory = TickerFactory(cfg)
        log.info("BQL service established")

    def snapshot(self, pairs: list[str], tenors: list[Tenor]) -> MarketSnapshot:
        ts = utcnow()
        universe = self._factory.universe(pairs, tenors)
        tickers = list(universe)
        req = self._bql.Request(tickers, {"px": self._svc.data.px_last()})
        res = self._svc.execute(req)            # ONE round trip
        df = res[0].df()
        values = {t: {"PX_LAST": float(v)}
                  for t, v in df["px"].items() if pd.notna(v)}
        log.info("BQL snap: %d/%d tickers resolved in one request",
                 len(values), len(tickers))
        return assemble_snapshot(values, universe, pairs, tenors, ts)

    def history_ohlc(self, pair: str, start: datetime,
                     end: datetime) -> pd.DataFrame:
        rng = self._bql.func.range(start.strftime("%Y-%m-%d"),
                                   end.strftime("%Y-%m-%d"))
        d = self._svc.data
        req = self._bql.Request(f"{pair} Curncy", {
            "open": d.px_open(dates=rng), "high": d.px_high(dates=rng),
            "low": d.px_low(dates=rng), "close": d.px_last(dates=rng)})
        res = self._svc.execute(req)
        frames = {r.name: r.df()[r.name] for r in res}
        out = pd.DataFrame(frames).reset_index(names="date")
        return out[["date", "open", "high", "low", "close"]]
