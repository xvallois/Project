"""Persistence: append-only Parquet history + DuckDB query layer.

Layout (hive-partitioned by date only — see note):

    {root}/parquet/{data_type}/date=YYYY-MM-DD/snap_{snapshot_id}.parquet
    {root}/latest/{data_type}.parquet          (overwritten each snap)

NOTE — deviation from ARCHITECTURE.md §5: we partition by date only, NOT
date/pair. At 5-min snaps, date/pair would create ~10k small files/day
(9 pairs x 288 snaps x 4 types); pair stays a column and DuckDB's predicate
pushdown filters it for free. `compact_day()` merges a day's snap files into
one file per type at EOD.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from volwatch.core.models import (
    ForwardPoints, MarketSnapshot, QuoteStatus, SpotQuote, Tenor,
)

log = logging.getLogger(__name__)

DATA_TYPES = ("spot", "forward", "vol", "rate")


class ParquetStore:
    """NB: the cached DuckDB connection is NOT thread-safe. The daemon runs
    jobs with max_instances=1 and the dashboard opens its own store — if a
    multi-threaded consumer appears, give it its own ParquetStore."""

    def __init__(self, root: str | Path, latest_dir: str | Path) -> None:
        self.root = Path(root)
        self.latest = Path(latest_dir)
        self.latest.mkdir(parents=True, exist_ok=True)
        self._con: "duckdb.DuckDBPyConnection | None" = None
        self._views: set[str] = set()

    # -- write --------------------------------------------------------- #
    def write_snapshot(self, snap: MarketSnapshot) -> None:
        frames = snap.to_frames()
        d = snap.asof.date().isoformat()
        for dtype, df in frames.items():
            if df.empty:
                continue
            part = self.root / "parquet" / dtype / f"date={d}"
            part.mkdir(parents=True, exist_ok=True)
            df.to_parquet(part / f"snap_{snap.snapshot_id}.parquet", index=False)
            df.to_parquet(self.latest / f"{dtype}.parquet", index=False)
        log.info("stored snapshot %s (%s)", snap.snapshot_id[:8], d)

    # -- read ---------------------------------------------------------- #
    def _glob(self, dtype: str) -> str:
        return str(self.root / "parquet" / dtype / "**" / "*.parquet")

    def _connection(self) -> "duckdb.DuckDBPyConnection":
        """Lazily-created persistent connection. Views are glob-based, so
        DuckDB re-expands them per execution — NEW parquet files are picked
        up automatically; only brand-new data_type dirs need registration."""
        if self._con is None:
            self._con = duckdb.connect()
        for dtype in DATA_TYPES:
            if dtype not in self._views and                     (self.root / "parquet" / dtype).exists():
                self._con.execute(
                    f"CREATE VIEW {dtype} AS SELECT * FROM "
                    f"read_parquet('{self._glob(dtype)}', hive_partitioning=1)")
                self._views.add(dtype)
        return self._con

    def query(self, sql: str) -> pd.DataFrame:
        """Raw DuckDB over the store. Tables: spot, forward, vol, rate.

        NB: `asof` is a DuckDB reserved keyword (ASOF joins) — quote it
        as "asof" in raw SQL.
        """
        return self._connection().execute(sql).df()

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con, self._views = None, set()

    def latest_frame(self, dtype: str) -> pd.DataFrame:
        return pd.read_parquet(self.latest / f"{dtype}.parquet")

    def atm_history(self, pair: str, tenor: str,
                    start: date | None = None) -> pd.DataFrame:
        """Convenience: ATM time series for z-score / signal lookbacks."""
        where = f"pair='{pair}' AND tenor='{tenor}'"
        if start:
            where += f" AND date >= '{start.isoformat()}'"
        return self.query(
            f'SELECT "asof", atm, rr25, bf25, status FROM vol '
            f'WHERE {where} ORDER BY "asof"')

    # -- maintenance ----------------------------------------------------#
    def compact_day(self, d: date) -> None:
        """EOD: merge a day's per-snap files into one file per data type."""
        for dtype in DATA_TYPES:
            part = self.root / "parquet" / dtype / f"date={d.isoformat()}"
            files = sorted(part.glob("snap_*.parquet")) if part.exists() else []
            if len(files) <= 1:
                continue
            merged = pd.concat((pd.read_parquet(f) for f in files),
                               ignore_index=True)
            merged.to_parquet(part / "day.parquet", index=False)
            for f in files:
                f.unlink()
            log.info("compacted %s %s: %d files -> 1 (%d rows)",
                     dtype, d, len(files), len(merged))

    def snapshot_on(self, d: date) -> MarketSnapshot:
        """Reconstruct the LAST stored snapshot of day `d` for replay.

        Validation flags are preserved. Rates are not reconstructed in v1
        (replay runs calibrate=False). For windowed replays prefer
        fetching the frames ONCE and calling reconstruct_snapshot per day
        (see backtest.ReplayCache)."""
        ds = d.isoformat()
        vol = self.query(f"SELECT * FROM vol WHERE date='{ds}'")
        if vol.empty:
            raise KeyError(f"no vol data stored on {ds}")
        spot = self.query(f"SELECT * FROM spot WHERE date='{ds}'")
        fwd = self.query(f"SELECT * FROM forward WHERE date='{ds}'")
        return reconstruct_snapshot(vol, spot, fwd)


def reconstruct_snapshot(vol: pd.DataFrame, spot: pd.DataFrame,
                         fwd: pd.DataFrame) -> MarketSnapshot:
    """Frame-level snapshot reconstruction (last snapshot_id in `vol`)."""
    if vol.empty:
        raise KeyError("empty vol frame")
    last_id = vol.sort_values("asof")["snapshot_id"].iloc[-1]
    vol = vol[vol["snapshot_id"] == last_id]
    spot = spot[spot["snapshot_id"] == last_id]
    fwd = fwd[fwd["snapshot_id"] == last_id]

    asof = pd.to_datetime(vol["asof"].iloc[0]).to_pydatetime()
    vols = {p_: MarketSnapshot.vol_surface_from_frame(vol, p_)
            for p_ in vol["pair"].unique()}
    spots = {r.pair: SpotQuote(pair=r.pair, mid=r.mid, bid=r.bid,
                               ask=r.ask,
                               ts=pd.to_datetime(r.ts).to_pydatetime(),
                               status=QuoteStatus(int(r.status)))
             for r in spot.itertuples()}
    forwards: dict[str, list[ForwardPoints]] = {}
    for r in fwd.itertuples():
        forwards.setdefault(r.pair, []).append(ForwardPoints(
            pair=r.pair, tenor=Tenor(r.tenor), points=r.points,
            outright=r.outright,
            ts=pd.to_datetime(r.ts).to_pydatetime(),
            status=QuoteStatus(int(r.status))))
    return MarketSnapshot(
        asof=asof, spots=spots,
        forwards={k: tuple(v) for k, v in forwards.items()},
        vols=vols, rates={}, snapshot_id=last_id)

