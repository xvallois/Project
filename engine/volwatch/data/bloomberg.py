"""Bloomberg Desktop API adapter.

The ONLY module allowed to import blpapi. Implements MarketDataProvider so
the rest of the system never knows Bloomberg exists.

Requirements on the desk machine:
  * Bloomberg Terminal running and logged in
  * `pip install blpapi --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/`
  * Desktop API enabled (default localhost:8194)

Design notes:
  * One ReferenceDataRequest per snap, batched (~900 securities for the full
    G10 grid — well inside refdata limits).
  * Missing/errored securities are logged and flagged PARTIAL, never fatal:
    a snapshot with 99% of the market is far better than no snapshot.
  * `LAST_UPDATE_DT`-based staleness is left to the validator — the adapter
    reports, it does not judge.
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


class BloombergProvider(MarketDataProvider):
    def __init__(self, config_path: str | Path = "config/bloomberg.yaml") -> None:
        try:
            import blpapi  # noqa: F401  (deferred: machine may lack Terminal)
        except ImportError as e:
            raise RuntimeError(
                "blpapi not installed. On the desk machine: pip install blpapi "
                "--index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/"
            ) from e
        self._blpapi = blpapi
        cfg = yaml.safe_load(Path(config_path).read_text())
        self._factory = TickerFactory(cfg)
        sess_opts = blpapi.SessionOptions()
        sess_opts.setServerHost(cfg["session"]["host"])
        sess_opts.setServerPort(cfg["session"]["port"])
        self._session = blpapi.Session(sess_opts)
        if not self._session.start() or not self._session.openService("//blp/refdata"):
            raise RuntimeError("Failed to start blpapi session / open refdata "
                               "(is the Terminal running and logged in?)")
        self._refdata = self._session.getService("//blp/refdata")
        log.info("Bloomberg session established")

    # ------------------------------------------------------------------ #
    def snapshot(self, pairs: list[str], tenors: list[Tenor]) -> MarketSnapshot:
        ts = utcnow()
        universe = self._factory.universe(pairs, tenors)
        values = self._reference_data(list(universe),
                                      ["PX_LAST", "PX_BID", "PX_ASK"])
        return assemble_snapshot(values, universe, pairs, tenors, ts)

    # ------------------------------------------------------------------ #
    def history_ohlc(self, pair: str, start: datetime,
                     end: datetime) -> pd.DataFrame:
        req = self._refdata.createRequest("HistoricalDataRequest")
        req.getElement("securities").appendValue(f"{pair} Curncy")
        for f in ("PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"):
            req.getElement("fields").appendValue(f)
        req.set("startDate", start.strftime("%Y%m%d"))
        req.set("endDate", end.strftime("%Y%m%d"))
        rows = []
        self._session.sendRequest(req)
        for msg in self._iter_response():
            sec = msg.getElement("securityData")
            for i in range(sec.getElement("fieldData").numValues()):
                fd = sec.getElement("fieldData").getValueAsElement(i)
                rows.append({
                    "date": fd.getElementAsDatetime("date"),
                    "open": fd.getElementAsFloat("PX_OPEN"),
                    "high": fd.getElementAsFloat("PX_HIGH"),
                    "low": fd.getElementAsFloat("PX_LOW"),
                    "close": fd.getElementAsFloat("PX_LAST"),
                })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ #
    def _reference_data(self, tickers: list[str],
                        fields: list[str]) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        CHUNK = 400
        for i in range(0, len(tickers), CHUNK):
            req = self._refdata.createRequest("ReferenceDataRequest")
            for t in tickers[i:i + CHUNK]:
                req.getElement("securities").appendValue(t)
            for f in fields:
                req.getElement("fields").appendValue(f)
            self._session.sendRequest(req)
            for msg in self._iter_response():
                arr = msg.getElement("securityData")
                for j in range(arr.numValues()):
                    sd = arr.getValueAsElement(j)
                    tkr = sd.getElementAsString("security")
                    if sd.hasElement("securityError"):
                        log.error("security error %s", tkr)
                        continue
                    fd = sd.getElement("fieldData")
                    out[tkr] = {f: fd.getElementAsFloat(f)
                                for f in fields if fd.hasElement(f)}
        return out

    def _iter_response(self):
        b = self._blpapi
        while True:
            ev = self._session.nextEvent(10_000)
            for msg in ev:
                if msg.hasElement("responseError"):
                    log.error("responseError: %s", msg)
                    continue
                yield msg
            if ev.eventType() == b.Event.RESPONSE:
                break

    def close(self) -> None:
        self._session.stop()
