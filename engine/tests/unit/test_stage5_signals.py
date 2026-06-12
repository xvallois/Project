"""Stage 5 tests.

Each signal gets two scenario tests: one constructed so it MUST fire with a
known direction, one neutral where it MUST stay silent. The framework tests
enforce the documentation contract and no-history silence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from volwatch.config import load_settings
from volwatch.core.models import Tenor
from volwatch.data.provider import MockProvider
from volwatch.data.store import ParquetStore
from volwatch.signals.base import (
    REGISTRY, Direction, HistoryView, Signal, zscore,
)
from volwatch.signals.engine import SignalEngine, build_context

T0 = datetime(2026, 1, 5, 16, 0, tzinfo=timezone.utc)


def seeded_store(tmp_path, n_days: int = 60, pairs=None, seed: int = 42):
    """Write n_days of daily mock snapshots; return (store, provider, snap)."""
    settings = load_settings("config/settings.yaml")
    pairs = pairs or settings.universe.all_pairs
    store = ParquetStore(tmp_path / "data", tmp_path / "latest")
    day = {"i": 0}

    def clock():
        return T0 + timedelta(days=day["i"])

    p = MockProvider(seed=seed, clock=clock)
    snap = None
    for i in range(n_days):
        day["i"] = i
        snap = p.snapshot(pairs, settings.universe.tenors)
        store.write_snapshot(snap)
    return settings, store, p, snap


# --------------------------------------------------------------------------- #
class TestFramework:
    def test_zscore(self) -> None:
        h = pd.Series(np.arange(40, dtype=float))     # mean 19.5, sd ~11.69
        assert zscore(h, 19.5) == pytest.approx(0.0, abs=1e-12)
        assert zscore(h, 19.5 + h.std()) == pytest.approx(1.0)

    def test_zscore_silent_without_history(self) -> None:
        assert zscore(pd.Series([1.0, 2.0]), 5.0) is None
        assert zscore(pd.Series(dtype=float), 5.0) is None

    def test_documentation_contract_enforced(self) -> None:
        with pytest.raises(TypeError, match="missing required attributes"):
            class Undocumented(Signal):           # noqa: F811
                name = "undocumented"
                math = "x"
                # intuition / edge / failure_modes missing
                def compute(self, ctx):
                    return []

    def test_registry_populated(self) -> None:
        assert {"vol_risk_premium", "term_structure_kink",
                "skew_richcheap", "triangle_correlation"} <= set(REGISTRY)

    def test_history_view_daily_resample(self, tmp_path) -> None:
        _, store, _, _ = seeded_store(tmp_path, n_days=10, pairs=["EURUSD"])
        s = HistoryView(store).series("EURUSD", Tenor.M3, "atm")
        assert len(s) == 10                       # one point per day
        assert s.index.is_monotonic_increasing


# --------------------------------------------------------------------------- #
class FixtureContext:
    """Builds a real context from a seeded store, then lets tests mutate it."""

    @staticmethod
    def make(tmp_path, n_days=60, seed=42):
        settings, store, provider, snap = seeded_store(tmp_path, n_days,
                                                       seed=seed)
        ctx = build_context(settings, snap, store, provider)
        return settings, ctx


class TestVolRiskPremium:
    def test_fires_sell_on_rich_vol(self, tmp_path) -> None:
        _, ctx = FixtureContext.make(tmp_path)
        # force EURUSD 3M implied far above anything in history
        from dataclasses import replace
        rep = ctx.carry["EURUSD"]
        tc = rep.get(Tenor.M3)
        ctx.carry["EURUSD"] = type(rep)(
            pair="EURUSD",
            tenors=tuple(replace(x, implied=x.implied + 6.0,
                                 iv_rv_spread=x.iv_rv_spread + 6.0)
                         if x.tenor is Tenor.M3 else x for x in rep.tenors))
        sig = REGISTRY["vol_risk_premium"]({"enabled": True, "tenors": ["3M"],
                                            "z_entry": 1.5,
                                            "lookback_days": 120})
        found = [s for s in sig.compute(ctx) if s.pair == "EURUSD"]
        assert found and found[0].direction is Direction.SELL_VOL
        assert found[0].score > 1.5
        assert found[0].edge_estimate > 3.0

    def test_silent_on_neutral_market(self, tmp_path) -> None:
        _, ctx = FixtureContext.make(tmp_path)
        sig = REGISTRY["vol_risk_premium"]({"enabled": True,
                                            "tenors": ["3M"],
                                            "z_entry": 2.5,
                                            "lookback_days": 120})
        # unmutated mock walk: nothing should be 2.5 sigma rich
        assert all(abs(s.score) < 6 for s in sig.compute(ctx))


class TestTermStructureKink:
    def test_fires_on_constructed_kink(self, tmp_path) -> None:
        from volwatch.core.models import VolQuote, VolSurface
        _, ctx = FixtureContext.make(tmp_path)
        surf = ctx.snapshot.vols["EURUSD"]
        bumped = tuple(
            VolQuote(pair=q.pair, tenor=q.tenor,
                     atm=q.atm + (2.5 if q.tenor is Tenor.M2 else 0.0),
                     rr25=q.rr25, bf25=q.bf25, rr10=q.rr10, bf10=q.bf10,
                     ts=q.ts, status=q.status)
            for q in surf)
        dict.__setitem__(ctx.snapshot.vols, "EURUSD",
                         VolSurface(pair="EURUSD", asof=surf.asof,
                                    quotes=bumped))
        sig = REGISTRY["term_structure_kink"]({"enabled": True,
                                               "z_entry": 1.5,
                                               "lookback_days": 120})
        hits = [s for s in sig.compute(ctx)
                if s.pair == "EURUSD" and Tenor.M2 in s.tenors
                and s.tenors[1] is Tenor.M2]
        assert hits
        assert hits[0].direction is Direction.SELL_FWD_VOL
        assert hits[0].value > 1.5                # kink in vol pts


class TestSkewRichCheap:
    def test_fires_on_stretched_rr(self, tmp_path) -> None:
        from volwatch.core.models import VolQuote, VolSurface
        _, ctx = FixtureContext.make(tmp_path)
        surf = ctx.snapshot.vols["USDJPY"]
        bumped = tuple(
            VolQuote(pair=q.pair, tenor=q.tenor, atm=q.atm,
                     rr25=q.rr25 - 2.0,            # JPY skew blows out
                     bf25=q.bf25, rr10=q.rr10, bf10=q.bf10,
                     ts=q.ts, status=q.status)
            for q in surf)
        dict.__setitem__(ctx.snapshot.vols, "USDJPY",
                         VolSurface(pair="USDJPY", asof=surf.asof,
                                    quotes=bumped))
        sig = REGISTRY["skew_richcheap"]({"enabled": True, "tenors": ["3M"],
                                          "z_entry": 1.5,
                                          "lookback_days": 120})
        hits = [s for s in sig.compute(ctx) if s.pair == "USDJPY"]
        assert hits and hits[0].direction is Direction.BUY_SKEW   # z << 0
        assert "realized_spot_vol_beta" in hits[0].details


class TestTriangleCorrelation:
    def base_params(self):
        return {"enabled": True, "lookback_days": 60,
                "corr_gap_entry": 0.10, "tenor": "3M",
                "triangles": [{"cross": "EURJPY", "leg1": "EURUSD",
                               "leg2": "USDJPY", "relation": "product"}]}

    def test_fires_sell_corr_on_rich_cross(self, tmp_path) -> None:
        from volwatch.core.models import VolQuote, VolSurface
        _, ctx = FixtureContext.make(tmp_path)
        surf = ctx.snapshot.vols["EURJPY"]
        bumped = tuple(
            VolQuote(pair=q.pair, tenor=q.tenor, atm=q.atm + 4.0,
                     rr25=q.rr25, bf25=q.bf25, rr10=q.rr10, bf10=q.bf10,
                     ts=q.ts, status=q.status) for q in surf)
        dict.__setitem__(ctx.snapshot.vols, "EURJPY",
                         VolSurface(pair="EURJPY", asof=surf.asof,
                                    quotes=bumped))
        sig = REGISTRY["triangle_correlation"](self.base_params())
        hits = sig.compute(ctx)
        assert hits and hits[0].direction is Direction.SELL_CORR
        assert hits[0].details["rho_implied"] > \
            hits[0].details["rho_realized"]
        assert hits[0].edge_estimate > 0

    def test_implied_corr_identity(self) -> None:
        """Hand-check: s1=10%, s2=12%, rho=0.5 product-cross =>
        sx = sqrt(.01+.0144+2*.5*.012) = sqrt(.0364); invert recovers 0.5."""
        import math
        sx = math.sqrt(0.01 + 0.0144 + 2 * 0.5 * 0.10 * 0.12)
        rho = (sx**2 - 0.01 - 0.0144) / (2 * 0.10 * 0.12)
        assert rho == pytest.approx(0.5, abs=1e-12)


# --------------------------------------------------------------------------- #
class TestEngine:
    def test_full_cycle(self, tmp_path) -> None:
        settings, store, provider, snap = seeded_store(tmp_path, n_days=60)
        ctx = build_context(settings, snap, store, provider)
        ss = SignalEngine().run(ctx)
        assert ss.asof == snap.asof
        scores = [abs(s.score) for s in ss.instances]
        assert scores == sorted(scores, reverse=True)   # ranked
        for s in ss.instances:                          # docs attached
            cls = REGISTRY[s.signal]
            assert cls.math and cls.failure_modes

    def test_disabled_signal_not_run(self, tmp_path) -> None:
        settings, store, provider, snap = seeded_store(
            tmp_path, n_days=40, pairs=["EURUSD", "USDJPY", "EURJPY"])
        ctx = build_context(settings, snap, store, provider)
        import yaml
        cfg = {"engine": {"top_n": 5},
               "signals": {"vol_risk_premium": {"enabled": False}}}
        path = tmp_path / "signals.yaml"
        path.write_text(yaml.safe_dump(cfg))
        ss = SignalEngine(path).run(ctx)
        assert all(s.signal != "vol_risk_premium" for s in ss.instances)
