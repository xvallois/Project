"""Stage 0 unit tests: domain models, conventions, config.

The convention tests assert *market facts* (Clark 2011, Wystup) — if a code
change breaks one, the change is wrong, not the test.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from volwatch.config import Settings, load_settings
from volwatch.core.conventions import REGISTRY, DeltaType
from volwatch.core.models import (
    MarketSnapshot, QuoteStatus, SpotQuote, Tenor, VolQuote, VolSurface,
)

TS = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def make_quote(tenor: Tenor = Tenor.M3) -> VolQuote:
    return VolQuote(pair="EURUSD", tenor=tenor, atm=7.50, rr25=-0.40,
                    bf25=0.20, rr10=-0.75, bf10=0.65, ts=TS)


# --------------------------------------------------------------------------- #
# Smile reconstruction                                                         #
# --------------------------------------------------------------------------- #
class TestSmile:
    def test_smile_bf_identity(self) -> None:
        s = make_quote().smile()
        # 25C = 7.50 + 0.20 + (-0.40)/2 = 7.50 ; 25P = 7.50 + 0.20 + 0.20 = 7.90
        assert s["25C"] == pytest.approx(7.50)
        assert s["25P"] == pytest.approx(7.90)
        assert s["ATM"] == pytest.approx(7.50)

    def test_rr_recovered(self) -> None:
        s = make_quote().smile()
        assert s["25C"] - s["25P"] == pytest.approx(-0.40)   # RR = C - P
        assert s["10C"] - s["10P"] == pytest.approx(-0.75)

    def test_bf_recovered(self) -> None:
        s = make_quote().smile()
        assert (s["25C"] + s["25P"]) / 2 - s["ATM"] == pytest.approx(0.20)

    def test_missing_10d_wings(self) -> None:
        q = VolQuote(pair="EURUSD", tenor=Tenor.M1, atm=7.0, rr25=-0.3,
                     bf25=0.15, rr10=None, bf10=None, ts=TS,
                     status=QuoteStatus.PARTIAL)
        assert set(q.smile()) == {"25P", "ATM", "25C"}


# --------------------------------------------------------------------------- #
# Surface invariants                                                           #
# --------------------------------------------------------------------------- #
class TestSurface:
    def test_rejects_mixed_pairs(self) -> None:
        bad = VolQuote(pair="USDJPY", tenor=Tenor.M1, atm=9.0, rr25=1.2,
                       bf25=0.3, rr10=None, bf10=None, ts=TS)
        with pytest.raises(ValueError, match="mixed-pair"):
            VolSurface(pair="EURUSD", asof=TS, quotes=(make_quote(), bad))

    def test_tenor_ordering(self) -> None:
        surf = VolSurface(pair="EURUSD", asof=TS,
                          quotes=(make_quote(Tenor.Y1), make_quote(Tenor.W1),
                                  make_quote(Tenor.M3)))
        assert surf.tenors() == [Tenor.W1, Tenor.M3, Tenor.Y1]

    def test_get_missing_tenor_raises(self) -> None:
        surf = VolSurface(pair="EURUSD", asof=TS, quotes=(make_quote(),))
        with pytest.raises(KeyError):
            surf.get(Tenor.ON)


# --------------------------------------------------------------------------- #
# Snapshot persistence round-trip                                              #
# --------------------------------------------------------------------------- #
class TestSnapshotRoundTrip:
    def make_snapshot(self) -> MarketSnapshot:
        surf = VolSurface(pair="EURUSD", asof=TS,
                          quotes=(make_quote(Tenor.M1), make_quote(Tenor.M3)))
        return MarketSnapshot(
            asof=TS,
            spots={"EURUSD": SpotQuote(pair="EURUSD", mid=1.0850, ts=TS)},
            forwards={}, vols={"EURUSD": surf}, rates={},
        )

    def test_frames_carry_lineage(self) -> None:
        snap = self.make_snapshot()
        vol = snap.to_frames()["vol"]
        assert (vol["snapshot_id"] == snap.snapshot_id).all()
        assert (vol["schema_version"] == 1).all()

    def test_parquet_round_trip(self, tmp_path) -> None:
        snap = self.make_snapshot()
        path = tmp_path / "vol.parquet"
        snap.to_frames()["vol"].to_parquet(path)
        rebuilt = MarketSnapshot.vol_surface_from_frame(
            pd.read_parquet(path), "EURUSD")
        original = snap.vols["EURUSD"]
        assert rebuilt.tenors() == original.tenors()
        for t in rebuilt.tenors():
            assert rebuilt.get(t).smile() == pytest.approx(
                original.get(t).smile())


# --------------------------------------------------------------------------- #
# Conventions — these assert market practice                                   #
# --------------------------------------------------------------------------- #
class TestConventions:
    @pytest.mark.parametrize("pair", ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"])
    def test_usd_quote_pairs_not_premium_adjusted(self, pair: str) -> None:
        assert REGISTRY.get(pair).premium_adjusted is False

    @pytest.mark.parametrize("pair", ["USDJPY", "USDCHF", "USDCAD",
                                      "EURJPY", "EURGBP"])
    def test_usd_eur_base_pairs_premium_adjusted(self, pair: str) -> None:
        assert REGISTRY.get(pair).premium_adjusted is True

    def test_spot_delta_short_dates(self) -> None:
        conv = REGISTRY.get("EURUSD")
        assert conv.delta_type(Tenor.M3) is DeltaType.SPOT
        assert conv.delta_type(Tenor.Y1) is DeltaType.SPOT  # <= switch tenor

    def test_jpy_points_scale(self) -> None:
        assert REGISTRY.get("USDJPY").points_scale == 1e2
        assert REGISTRY.get("EURUSD").points_scale == 1e4

    def test_unknown_pair_refuses_to_guess(self) -> None:
        with pytest.raises(KeyError, match="Refusing to guess"):
            REGISTRY.get("USDTRY")


# --------------------------------------------------------------------------- #
# Config                                                                       #
# --------------------------------------------------------------------------- #
class TestConfig:
    def test_loads_repo_settings(self) -> None:
        s = load_settings("config/settings.yaml")
        assert isinstance(s, Settings)
        assert "EURUSD" in s.universe.pairs
        assert s.schedule.snap_interval_minutes == 5
        assert s.book.enabled is False          # planned, not yet on

    def test_every_configured_pair_has_conventions(self) -> None:
        """Boot-time invariant: universe ⊆ convention registry."""
        s = load_settings("config/settings.yaml")
        for pair in s.universe.all_pairs:
            REGISTRY.get(pair)  # raises if missing

    def test_invalid_pair_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid pair"):
            Settings.model_validate({
                "universe": {"pairs": ["EURUSD", "eurjpy!"],
                             "tenors": ["1M"]},
                "schedule": {"snap_interval_minutes": 5},
                "storage": {"root": ".", "latest_dir": "."},
            })
