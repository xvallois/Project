"""Stage 1 tests: data layer end-to-end without a Bloomberg Terminal."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from volwatch.config import load_settings
from volwatch.core.models import QuoteStatus, Tenor
from volwatch.data.pipeline import SnapPipeline
from volwatch.data.provider import MockProvider
from volwatch.data.store import ParquetStore
from volwatch.data.tickers import TickerFactory, TickerKind
from volwatch.data.validation import SnapshotValidator

PAIRS = ["EURUSD", "USDJPY", "GBPUSD"]
TENORS = [Tenor.ON, Tenor.M1, Tenor.M3, Tenor.Y1]


# --------------------------------------------------------------------------- #
class TestTickers:
    @pytest.fixture(scope="class")
    def factory(self) -> TickerFactory:
        return TickerFactory.from_yaml("config/bloomberg.yaml")

    def test_vol_ticker_formats(self, factory: TickerFactory) -> None:
        assert factory.atm("EURUSD", Tenor.M1).ticker == "EURUSDV1M BGN Curncy"
        assert factory.rr("USDJPY", 25, Tenor.M3).ticker == "USDJPY25R3M BGN Curncy"
        assert factory.bf("GBPUSD", 10, Tenor.Y1).ticker == "GBPUSD10B1Y BGN Curncy"

    def test_universe_complete_and_reversible(self, factory: TickerFactory) -> None:
        uni = factory.universe(PAIRS, TENORS)
        # per pair: 1 spot + 3 fwds (no ON) + 4 tenors * (1 ATM + 2 RR + 2 BF)
        expected_per_pair = 1 + 3 + 4 * 5
        rate_count = sum(len(c["tickers"]) for c in
                         factory._rates_cfg.values())
        assert len(uni) == len(PAIRS) * expected_per_pair + rate_count
        # every meta maps back to its ticker (no parsing heuristics needed)
        for ticker, meta in uni.items():
            assert meta.ticker == ticker
        kinds = {m.kind for m in uni.values()}
        assert TickerKind.RATE in kinds and TickerKind.FORWARD in kinds


# --------------------------------------------------------------------------- #
class TestMockProvider:
    def test_snapshot_complete(self) -> None:
        snap = MockProvider().snapshot(PAIRS, TENORS)
        assert set(snap.spots) == set(PAIRS)
        assert set(snap.vols) == set(PAIRS)
        for pair in PAIRS:
            assert snap.vols[pair].tenors() == sorted(
                TENORS, key=lambda t: t.nominal_year_fraction)

    def test_market_realism(self) -> None:
        """Smile sanity the analytics stage will rely on."""
        snap = MockProvider(seed=7).snapshot(PAIRS, TENORS)
        jpy = snap.vols["USDJPY"]
        assert jpy.get(Tenor.M3).rr25 < 0          # JPY-call skew
        for pair in PAIRS:
            for q in snap.vols[pair]:
                assert q.bf25 > 0                  # convexity positive
                smile = q.smile()
                assert smile["10P"] > smile["25P"]  # wings above shoulders

    def test_successive_snaps_differ(self) -> None:
        p = MockProvider()
        a = p.snapshot(PAIRS, TENORS).vols["EURUSD"].get(Tenor.M3).atm
        b = p.snapshot(PAIRS, TENORS).vols["EURUSD"].get(Tenor.M3).atm
        assert a != b

    def test_deterministic_given_seed(self) -> None:
        a = MockProvider(seed=1).snapshot(PAIRS, TENORS)
        b = MockProvider(seed=1).snapshot(PAIRS, TENORS)
        assert a.vols["EURUSD"].get(Tenor.M1).atm == \
            b.vols["EURUSD"].get(Tenor.M1).atm

    def test_history_ohlc_shape(self) -> None:
        df = MockProvider().history_ohlc(
            "EURUSD", datetime(2026, 1, 1), datetime(2026, 3, 1))
        assert {"date", "open", "high", "low", "close"} <= set(df.columns)
        assert (df["high"] >= df["close"]).all()
        assert (df["low"] <= df["close"]).all()


# --------------------------------------------------------------------------- #
class TestValidator:
    def test_clean_snapshot_passes(self) -> None:
        snap = MockProvider().snapshot(PAIRS, TENORS)
        _, report = SnapshotValidator().validate(snap)
        assert report.clean

    def test_defects_flagged_not_dropped(self) -> None:
        snap = MockProvider(corrupt=True).snapshot(PAIRS, TENORS)
        validated, report = SnapshotValidator().validate(snap)
        assert not report.clean
        bad = validated.vols["EURUSD"].get(Tenor.M1)
        assert bad.status & QuoteStatus.OUTLIER
        assert bad.atm == 95.0                       # stored, not repaired
        assert validated.spots["GBPUSD"].status & QuoteStatus.STALE

    def test_jump_detection_across_snaps(self) -> None:
        v = SnapshotValidator()
        p = MockProvider()
        v.validate(p.snapshot(PAIRS, TENORS))        # establishes baseline
        snap2, _ = v.validate(p.snapshot(PAIRS, TENORS))
        assert all(not (q.status & QuoteStatus.OUTLIER)
                   for q in snap2.vols["EURUSD"])    # small walk: no flags
        snap3 = MockProvider(corrupt=True, seed=99).snapshot(PAIRS, TENORS)
        _, rep = v.validate(snap3)
        assert any("jump" in f or "bounds" in f for f in rep.flagged)


# --------------------------------------------------------------------------- #
class TestStore:
    def test_write_query_roundtrip(self, tmp_path) -> None:
        store = ParquetStore(tmp_path / "data", tmp_path / "latest")
        snap = MockProvider().snapshot(PAIRS, TENORS)
        store.write_snapshot(snap)

        df = store.query("SELECT pair, tenor, atm FROM vol WHERE pair='USDJPY'")
        assert len(df) == len(TENORS)
        hist = store.atm_history("EURUSD", "3M")
        assert len(hist) == 1
        assert store.latest_frame("spot")["pair"].nunique() == len(PAIRS)

    def test_history_accumulates(self, tmp_path) -> None:
        store = ParquetStore(tmp_path / "data", tmp_path / "latest")
        p = MockProvider()
        for _ in range(3):
            store.write_snapshot(p.snapshot(PAIRS, TENORS))
        assert len(store.atm_history("EURUSD", "3M")) == 3
        assert len(store.latest_frame("vol")) == len(PAIRS) * len(TENORS)

    def test_compaction_preserves_rows(self, tmp_path) -> None:
        store = ParquetStore(tmp_path / "data", tmp_path / "latest")
        p = MockProvider()
        snaps = [p.snapshot(PAIRS, TENORS) for _ in range(3)]
        for s in snaps:
            store.write_snapshot(s)
        before = store.query("SELECT count(*) n FROM vol")["n"][0]
        store.compact_day(snaps[0].asof.date())
        after = store.query("SELECT count(*) n FROM vol")["n"][0]
        assert before == after == 3 * len(PAIRS) * len(TENORS)


# --------------------------------------------------------------------------- #
class TestPipelineE2E:
    def test_full_cycle_on_repo_config(self, tmp_path) -> None:
        settings = load_settings("config/settings.yaml")
        store = ParquetStore(tmp_path / "data", tmp_path / "latest")
        pipe = SnapPipeline(settings, MockProvider(), store=store)
        _, report = pipe.run_once()
        assert report.clean
        df = store.query("SELECT DISTINCT pair FROM vol")
        assert set(df["pair"]) == set(settings.universe.all_pairs)
