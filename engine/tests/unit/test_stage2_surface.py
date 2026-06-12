"""Stage 2 tests.

The golden values here are computed BY HAND from the closed-form identities,
independently of the library code paths they test. If a refactor moves them,
the refactor is wrong.
"""
from __future__ import annotations

import math
from datetime import date

import pytest
from scipy.stats import norm

from volwatch.analytics import black
from volwatch.analytics.surface import (
    SmileBuilder, build_surface, strike_from_delta,
)
from volwatch.core.calendars import expiry_date, year_fraction, year_fractions
from volwatch.core.conventions import REGISTRY, DeltaType
from volwatch.core.models import Tenor, VolQuote, utcnow

F, T, VOL, RD, RF = 1.1000, 0.25, 0.10, 0.045, 0.02


# --------------------------------------------------------------------------- #
class TestBlack:
    def test_put_call_parity(self) -> None:
        k = 1.08
        c = black.price(F, k, VOL, T, RD, +1)
        p = black.price(F, k, VOL, T, RD, -1)
        assert c - p == pytest.approx(math.exp(-RD * T) * (F - k), abs=1e-12)

    def test_forward(self) -> None:
        assert black.forward(1.0850, RD, RF, T) == pytest.approx(
            1.0850 * math.exp(0.025 * 0.25))

    def test_spot_delta_hand_calc(self) -> None:
        """Hand: K=F => d1 = 0.5σ√T = 0.025; Δ = e^{-r_f T}·N(0.025)."""
        expected = math.exp(-RF * T) * norm.cdf(0.025)
        got = black.delta(F, F, VOL, T, RF, +1, DeltaType.SPOT, False)
        assert got == pytest.approx(expected, abs=1e-12)

    def test_pa_delta_hand_calc(self) -> None:
        """Hand: K=F => d2 = -0.025; Δ_pa = e^{-r_f T}·1·N(-0.025)."""
        expected = math.exp(-RF * T) * norm.cdf(-0.025)
        got = black.delta(F, F, VOL, T, RF, +1, DeltaType.SPOT, True)
        assert got == pytest.approx(expected, abs=1e-12)

    def test_atm_dns_strikes(self) -> None:
        k_u = black.atm_dns_strike(F, VOL, T, premium_adjusted=False)
        k_pa = black.atm_dns_strike(F, VOL, T, premium_adjusted=True)
        assert k_u == pytest.approx(F * math.exp(0.5 * VOL**2 * T))
        assert k_pa == pytest.approx(F * math.exp(-0.5 * VOL**2 * T))

    def test_dns_strike_zeroes_straddle_delta(self) -> None:
        """The defining property, both conventions: Δ_call + Δ_put = 0."""
        for pa in (False, True):
            k = black.atm_dns_strike(F, VOL, T, pa)
            tot = sum(black.delta(F, k, VOL, T, RF, w, DeltaType.SPOT, pa)
                      for w in (+1, -1))
            assert tot == pytest.approx(0.0, abs=1e-12)


# --------------------------------------------------------------------------- #
class TestStrikeFromDelta:
    @pytest.mark.parametrize("omega,target", [(+1, 0.25), (+1, 0.10),
                                              (-1, -0.25), (-1, -0.10)])
    @pytest.mark.parametrize("dtype", [DeltaType.SPOT, DeltaType.FORWARD])
    @pytest.mark.parametrize("pa", [False, True])
    def test_round_trip(self, omega: int, target: float,
                        dtype: DeltaType, pa: bool) -> None:
        k = strike_from_delta(target, F, VOL, T, RF, omega, dtype, pa)
        back = black.delta(F, k, VOL, T, RF, omega, dtype, pa)
        assert back == pytest.approx(target, abs=1e-9)

    def test_unadjusted_closed_form_hand_calc(self) -> None:
        """25d call, forward delta, rf irrelevant:
        d1 = N^{-1}(0.25); K = F·exp(-d1·σ√T + σ²T/2)."""
        d1 = norm.ppf(0.25)
        expected = F * math.exp(-d1 * VOL * math.sqrt(T) + 0.5 * VOL**2 * T)
        got = strike_from_delta(0.25, F, VOL, T, RF, +1,
                                DeltaType.FORWARD, False)
        assert got == pytest.approx(expected, rel=1e-12)

    def test_pa_call_takes_right_branch(self) -> None:
        """The PA-call root must lie ABOVE the delta-maximum strike, and
        delta must be decreasing there (the market branch)."""
        k = strike_from_delta(0.25, F, VOL, T, RF, +1, DeltaType.SPOT, True)
        eps = 1e-5
        d_lo = black.delta(F, k - eps, VOL, T, RF, +1, DeltaType.SPOT, True)
        d_hi = black.delta(F, k + eps, VOL, T, RF, +1, DeltaType.SPOT, True)
        assert d_lo > d_hi                      # decreasing => right branch

    def test_pa_call_strike_below_unadjusted(self) -> None:
        """For the same 25d, PA strike < unadjusted strike (premium effect)."""
        k_pa = strike_from_delta(0.25, F, VOL, T, RF, +1, DeltaType.SPOT, True)
        k_u = strike_from_delta(0.25, F, VOL, T, RF, +1, DeltaType.SPOT, False)
        assert k_pa < k_u

    def test_unattainable_pa_delta_raises(self) -> None:
        with pytest.raises(ValueError, match="unattainable"):
            strike_from_delta(0.95, F, VOL, T, RF, +1, DeltaType.SPOT, True)


# --------------------------------------------------------------------------- #
class TestSmileBuilder:
    def make_smile(self, pair: str, f: float):
        q = VolQuote(pair=pair, tenor=Tenor.M3, atm=10.0, rr25=-1.5,
                     bf25=0.30, rr10=-2.8, bf10=1.0, ts=utcnow())
        return SmileBuilder(REGISTRY.get(pair)).build(q, f=f, t=0.25, rf=RF)

    def test_strike_ordering_eurusd(self) -> None:
        s = self.make_smile("EURUSD", 1.10)
        labels = [n.label for n in s.nodes]
        assert labels == ["10P", "25P", "ATM", "25C", "10C"]

    def test_strike_ordering_usdjpy_premium_adjusted(self) -> None:
        s = self.make_smile("USDJPY", 155.0)
        labels = [n.label for n in s.nodes]
        assert labels == ["10P", "25P", "ATM", "25C", "10C"]

    def test_interpolation_reproduces_nodes(self) -> None:
        s = self.make_smile("EURUSD", 1.10)
        for n in s.nodes:
            assert s.vol_at_strike(n.strike) == pytest.approx(n.vol, abs=1e-10)
        assert s.vol_at_delta(0.25) == pytest.approx(
            next(n.vol for n in s.nodes if n.label == "25C"))

    def test_skew_direction(self) -> None:
        """RR < 0 => put-wing vols above call-wing at same |delta|."""
        s = self.make_smile("EURUSD", 1.10)
        v = {n.label: n.vol for n in s.nodes}
        assert v["25P"] > v["25C"] and v["10P"] > v["10C"]


# --------------------------------------------------------------------------- #
class TestCalendars:
    def test_weekend_roll(self) -> None:
        # 2026-06-12 is a Friday; +1W = Friday 19th (no roll needed);
        # 2026-06-13 Sat +1W = Sat 20th -> Mon 22nd
        assert expiry_date(date(2026, 6, 13), Tenor.W1) == date(2026, 6, 22)

    def test_year_fraction_act365(self) -> None:
        assert year_fraction(date(2026, 1, 1), date(2027, 1, 1)) == \
            pytest.approx(365 / 365)

    def test_on_floor(self) -> None:
        yf = year_fractions(date(2026, 6, 10), [Tenor.ON])[Tenor.ON]
        assert yf >= 1 / 365


# --------------------------------------------------------------------------- #
class TestEndToEnd:
    def test_mock_snapshot_to_strike_surfaces(self) -> None:
        """Every pair in the universe builds a clean strike surface."""
        from volwatch.config import load_settings
        from volwatch.data.provider import MockProvider

        settings = load_settings("config/settings.yaml")
        u = settings.universe
        snap = MockProvider().snapshot(u.all_pairs, u.tenors)
        yfs = year_fractions(snap.asof.date(), u.tenors)

        for pair in u.all_pairs:
            fwd_map = {f.tenor: f.outright for f in snap.forwards[pair]}
            # ON forward not snapped: approximate with spot for the test
            fwd_map[Tenor.ON] = snap.spots[pair].mid
            rf_curve = {t: 0.02 for t in u.tenors}
            ss = build_surface(snap.vols[pair], fwd_map, yfs, rf_curve)
            assert len(ss.smiles) == len(u.tenors)
            for sm in ss.smiles:
                ks = [n.strike for n in sm.nodes]
                assert ks == sorted(ks)
