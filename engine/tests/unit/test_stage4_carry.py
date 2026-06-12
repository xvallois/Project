"""Stage 4 tests.

Realized estimators are tested two ways:
  1. hand-calculated goldens on tiny deterministic frames (formula checks);
  2. statistical recovery on simulated GBM with KNOWN true vol — each
     estimator must land near truth, and the range-based estimators must
     have visibly lower sampling variance than close-close.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from volwatch.analytics.carry import carry_report
from volwatch.analytics.forward_vol import (
    forward_vol, forward_vol_at_moneyness, forward_vol_grid,
)
from volwatch.analytics.realized import (
    close_close, compute_realized, garman_klass, parkinson, yang_zhang,
)
from volwatch.core.models import Tenor

RNG = np.random.default_rng(123)


def simulate_ohlc(true_vol: float, n_days: int, steps: int = 200,
                  s0: float = 1.0, seed: int | None = None) -> pd.DataFrame:
    """GBM with intraday path of `steps` ticks -> honest OHLC per day."""
    rng = np.random.default_rng(seed) if seed is not None else RNG
    dt = (1.0 / 252.0) / steps
    rows, s = [], s0
    for _ in range(n_days):
        path = s * np.exp(np.cumsum(
            rng.normal(-0.5 * true_vol**2 * dt, true_vol * math.sqrt(dt),
                       steps)))
        rows.append({"open": s, "high": float(path.max()),
                     "low": float(path.min()), "close": float(path[-1])})
        s = float(path[-1])
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
class TestRealizedGoldens:
    def test_close_close_hand_calc(self) -> None:
        """closes 100,101,100: r = [ln1.01, -ln1.01];
        vol = sqrt(252 * mean(r^2))."""
        df = pd.DataFrame({"close": [100.0, 101.0, 100.0]})
        r = math.log(1.01)
        expected = math.sqrt(252.0 * (2 * r * r) / 2)
        assert close_close(df, 2) == pytest.approx(expected, abs=1e-14)

    def test_parkinson_hand_calc(self) -> None:
        """constant H/L = 1.02:
        vol = sqrt(252 * ln(1.02)^2 / (4 ln 2))."""
        df = pd.DataFrame({"high": [1.02] * 10, "low": [1.0] * 10})
        expected = math.sqrt(252.0 * math.log(1.02) ** 2 / (4 * math.log(2)))
        assert parkinson(df, 10) == pytest.approx(expected, abs=1e-14)

    def test_garman_klass_hand_calc(self) -> None:
        """O=C=1 (no body), H/L=1.02 straddling:
        var = 0.5*ln(1.02)^2 per day."""
        df = pd.DataFrame({"open": [1.0] * 10, "close": [1.0] * 10,
                           "high": [1.01] * 10, "low": [1.01 / 1.02] * 10})
        expected = math.sqrt(252.0 * 0.5 * math.log(1.02) ** 2)
        assert garman_klass(df, 10) == pytest.approx(expected, rel=1e-12)

    def test_insufficient_data_raises(self) -> None:
        df = pd.DataFrame({"close": [1.0, 1.01]})
        with pytest.raises(ValueError, match="clean rows"):
            close_close(df, 21)


class TestRealizedStatistical:
    TRUE = 0.10

    def test_all_estimators_recover_truth(self) -> None:
        df = simulate_ohlc(self.TRUE, n_days=2000, seed=7)
        for fn in (close_close, parkinson, garman_klass, yang_zhang):
            est = fn(df, 1990)
            # rel=0.08: range-based estimators are biased LOW a few percent
            # by discrete monitoring (200 ticks/day under-samples the true
            # range) — a property of the simulation, documented in the
            # estimator module, not an estimator bug.
            assert est == pytest.approx(self.TRUE, rel=0.08), fn.__name__

    def test_parkinson_more_efficient_than_close_close(self) -> None:
        """Sampling std of the 21d estimate across many independent windows
        must be materially lower for Parkinson (theory: ~sqrt(5) better)."""
        cc, pk = [], []
        for seed in range(40):
            df = simulate_ohlc(self.TRUE, n_days=21, seed=1000 + seed)
            cc.append(close_close(df, 20))
            pk.append(parkinson(df, 21))
        assert np.std(pk) < 0.7 * np.std(cc)

    def test_compute_realized_assembles(self) -> None:
        df = simulate_ohlc(self.TRUE, n_days=300, seed=3)
        rv = compute_realized("EURUSD", df)
        assert rv.get("yang_zhang", 21) == pytest.approx(self.TRUE, rel=0.30)
        assert rv.matched(Tenor.M1) == rv.get("yang_zhang", 21)
        assert rv.matched(Tenor.ON) == rv.get("yang_zhang", 5)
        assert 252 in rv.values["close_close"]


# --------------------------------------------------------------------------- #
class TestForwardVol:
    def test_hand_calc(self) -> None:
        """10% 3M, 12% 6M:
        fwd_var = (0.0144*0.5 - 0.01*0.25)/0.25 = 0.0188 -> 13.711%."""
        fv = forward_vol("EURUSD", Tenor.M3, Tenor.M6, 0.25, 0.5, 0.10, 0.12)
        assert fv.fwd_vol == pytest.approx(math.sqrt(0.0188), abs=1e-12)
        assert fv.premium_to_far == pytest.approx(math.sqrt(0.0188) - 0.12)

    def test_flat_curve_forward_equals_spot(self) -> None:
        fv = forward_vol("EURUSD", Tenor.M3, Tenor.M6, 0.25, 0.5, 0.10, 0.10)
        assert fv.fwd_vol == pytest.approx(0.10, abs=1e-12)

    def test_negative_forward_variance_flagged_not_raised(self) -> None:
        """Heavily inverted curve => negative fwd variance, returned flagged."""
        fv = forward_vol("EURUSD", Tenor.M1, Tenor.M2, 1 / 12, 2 / 12,
                         0.20, 0.10)
        assert not fv.valid and fv.fwd_vol is None
        assert fv.fwd_variance < 0

    def test_grid_counts(self) -> None:
        curve = {Tenor.M1: 0.07, Tenor.M3: 0.075, Tenor.M6: 0.08}
        ts = {Tenor.M1: 1 / 12, Tenor.M3: 0.25, Tenor.M6: 0.5}
        assert len(forward_vol_grid("EURUSD", curve, ts)) == 3
        assert len(forward_vol_grid("EURUSD", curve, ts,
                                    adjacent_only=True)) == 2

    def test_fixed_moneyness_variant(self) -> None:
        from volwatch.analytics.ssvi import SsviFit
        ssvi = SsviFit(pair="EURUSD", rho=-0.25, eta=0.9, gamma=0.45,
                       thetas={Tenor.M3: 0.10**2 * 0.25,
                               Tenor.M6: 0.11**2 * 0.5},
                       ts={Tenor.M3: 0.25, Tenor.M6: 0.5},
                       forwards={Tenor.M3: 1.10, Tenor.M6: 1.102},
                       rmse=0.0, butterfly_ok=True, calendar_ok=True)
        atm = forward_vol_at_moneyness(ssvi, Tenor.M3, Tenor.M6, 0.0)
        wing = forward_vol_at_moneyness(ssvi, Tenor.M3, Tenor.M6, -0.05)
        assert atm.valid and wing.valid
        assert wing.fwd_vol > atm.fwd_vol      # put wing richer, rho<0


# --------------------------------------------------------------------------- #
class TestCarry:
    def make_report(self):
        df = simulate_ohlc(0.07, n_days=300, seed=9)
        rv = compute_realized("EURUSD", df)
        curve = {Tenor.M1: 8.5, Tenor.M3: 9.0, Tenor.M6: 9.5}  # vol pts
        ts = {Tenor.M1: 1 / 12, Tenor.M3: 0.25, Tenor.M6: 0.5}
        return carry_report("EURUSD", curve, ts, rv)

    def test_iv_rv_spread_positive_when_implied_rich(self) -> None:
        rep = self.make_report()
        for tc in rep.tenors:               # implied 8.5-9.5 vs realized ~7
            assert tc.iv_rv_spread > 0
        assert rep.richest_vs_realized().tenor in (Tenor.M3, Tenor.M6,
                                                   Tenor.M1)

    def test_rolldown_sign_on_upward_curve(self) -> None:
        rep = self.make_report()
        assert rep.get(Tenor.M1).rolldown_1w is None    # shortest tenor
        assert rep.get(Tenor.M3).rolldown_1w > 0
        assert rep.get(Tenor.M6).rolldown_1w > 0

    def test_rolldown_total_variance_interpolation(self) -> None:
        """Hand-check the 3M point: w interp between 1M and 3M."""
        rep = self.make_report()
        t_target = 0.25 - 7 / 365
        w1, w3 = 8.5**2 / 12, 9.0**2 * 0.25
        w = w1 + (w3 - w1) * (t_target - 1 / 12) / (0.25 - 1 / 12)
        expected_roll = 9.0 - math.sqrt(w / t_target)
        assert rep.get(Tenor.M3).rolldown_1w == pytest.approx(
            expected_roll, abs=1e-9)

    def test_breakeven(self) -> None:
        rep = self.make_report()
        assert rep.get(Tenor.M3).breakeven_daily_pct == pytest.approx(
            9.0 / math.sqrt(252))


# --------------------------------------------------------------------------- #
class TestEndToEnd:
    def test_mock_universe_carry_and_forward_vol(self) -> None:
        from datetime import datetime, timedelta, timezone
        from volwatch.config import load_settings
        from volwatch.core.calendars import year_fractions
        from volwatch.data.provider import MockProvider

        u = load_settings("config/settings.yaml").universe
        p = MockProvider()
        snap = p.snapshot(u.all_pairs, u.tenors)
        yfs = year_fractions(snap.asof.date(), u.tenors)
        end = datetime.now(timezone.utc)
        for pair in u.all_pairs:
            curve = {t: v for t, v in snap.vols[pair].atm_curve().items()}
            grid = forward_vol_grid(pair, {t: v / 100 for t, v in
                                           curve.items()}, yfs,
                                    adjacent_only=True)
            assert all(fv.valid for fv in grid), pair
            ohlc = p.history_ohlc(pair, end - timedelta(days=500), end)
            rep = carry_report(pair, curve, yfs,
                               compute_realized(pair, ohlc))
            assert len(rep.tenors) == len(u.tenors)
