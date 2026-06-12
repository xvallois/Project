"""Stage 3 tests: calibration property tests and arb-engine verification.

Core philosophy: a calibrator must RECOVER parameters from a surface it
generated itself (round-trip), and the arb engine must FIRE on surfaces
constructed to violate, and stay quiet on clean ones.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from volwatch.analytics.arbitrage import (
    butterfly_margin, calendar_margins, check_surface,
)
from volwatch.analytics.fit import calibrate_surface
from volwatch.analytics.sabr import SabrFit, calibrate_sabr, hagan_vol
from volwatch.analytics.ssvi import calibrate_ssvi, ssvi_total_variance
from volwatch.analytics.surface import SmileNode, StrikeSmile, StrikeSurface
from volwatch.core.models import Tenor

F, T = 1.10, 0.25


def smile_from_sabr(alpha: float, rho: float, nu: float,
                    tenor: Tenor = Tenor.M3, t: float = T,
                    f: float = F) -> StrikeSmile:
    """Generate a 5-node smile from known SABR params (beta=1)."""
    deltas = [("10P", -1.2816), ("25P", -0.6745), ("ATM", 0.0),
              ("25C", 0.6745), ("10C", 1.2816)]   # ~N^{-1} spacings
    nodes = []
    for label, z in deltas:
        k = f * math.exp(-z * alpha * math.sqrt(t))   # rough strike ladder
        nodes.append(SmileNode(label, 0.0, k,
                               hagan_vol(f, k, t, alpha, 1.0, rho, nu)))
    nodes.sort(key=lambda n: n.strike)
    return StrikeSmile(pair="EURUSD", tenor=tenor, t=t, f=f,
                       nodes=tuple(nodes))


# --------------------------------------------------------------------------- #
class TestHagan:
    def test_atm_limit_continuous(self) -> None:
        """vol(K->F) must approach vol(K=F) — the z/x(z) limit."""
        v_atm = hagan_vol(F, F, T, 0.10, 1.0, -0.3, 0.8)
        v_near = hagan_vol(F, F * (1 + 1e-9), T, 0.10, 1.0, -0.3, 0.8)
        assert v_near == pytest.approx(v_atm, abs=1e-8)

    def test_atm_hand_calc_beta1(self) -> None:
        """beta=1, K=F: sigma = alpha*(1 + (rho*nu*alpha/4
        + (2-3rho^2)*nu^2/24)*T)."""
        a, r, n = 0.10, -0.3, 0.8
        expected = a * (1 + (r * n * a / 4 + (2 - 3 * r * r) / 24 * n * n) * T)
        assert hagan_vol(F, F, T, a, 1.0, r, n) == pytest.approx(
            expected, abs=1e-14)

    def test_rho_controls_skew(self) -> None:
        lo = hagan_vol(F, F * 0.95, T, 0.10, 1.0, -0.5, 0.8)
        hi = hagan_vol(F, F * 1.05, T, 0.10, 1.0, -0.5, 0.8)
        assert lo > hi                       # negative rho => put skew


# --------------------------------------------------------------------------- #
class TestSabrCalibration:
    @pytest.mark.parametrize("alpha,rho,nu", [
        (0.10, -0.30, 0.80), (0.075, 0.15, 1.20), (0.12, -0.60, 0.50)])
    def test_round_trip_recovers_params(self, alpha, rho, nu) -> None:
        fit = calibrate_sabr(smile_from_sabr(alpha, rho, nu))
        assert fit.alpha == pytest.approx(alpha, rel=2e-3)
        assert fit.rho == pytest.approx(rho, abs=5e-3)
        assert fit.nu == pytest.approx(nu, rel=2e-2)
        assert fit.rmse < 1e-4               # vol pts; essentially exact

    def test_fit_quality_on_market_style_smile(self) -> None:
        """Build via the real pipeline from a quote vector; SABR should fit
        a typical G10 smile to within a few hundredths of a vol pt."""
        from volwatch.analytics.surface import SmileBuilder
        from volwatch.core.conventions import REGISTRY
        from volwatch.core.models import VolQuote, utcnow
        q = VolQuote(pair="EURUSD", tenor=Tenor.M3, atm=7.5, rr25=-0.40,
                     bf25=0.20, rr10=-0.78, bf10=0.70, ts=utcnow())
        sm = SmileBuilder(REGISTRY.get("EURUSD")).build(q, f=1.10, t=T,
                                                        rf=0.02)
        fit = calibrate_sabr(sm)
        assert fit.rmse < 0.05
        assert fit.rho < 0                   # matches RR sign

    def test_atm_anchored(self) -> None:
        fit = calibrate_sabr(smile_from_sabr(0.10, -0.3, 0.8))
        assert fit.vol(F) == pytest.approx(
            hagan_vol(F, F, T, 0.10, 1.0, -0.3, 0.8), abs=2e-5)


# --------------------------------------------------------------------------- #
class TestSsvi:
    def surface_from_ssvi(self, rho=-0.25, eta=0.9, gamma=0.45):
        smiles = []
        for tenor, t, atm in [(Tenor.M1, 1 / 12, 0.072), (Tenor.M3, 0.25, 0.075),
                              (Tenor.M6, 0.5, 0.078), (Tenor.Y1, 1.0, 0.082)]:
            theta = atm * atm * t
            nodes = []
            for label, k in [("10P", -0.10), ("25P", -0.05), ("ATM", 0.0),
                             ("25C", 0.05), ("10C", 0.10)]:
                w = ssvi_total_variance(k, theta, rho, eta, gamma)
                nodes.append(SmileNode(label, 0.0, F * math.exp(k),
                                       math.sqrt(w / t)))
            smiles.append(StrikeSmile(pair="EURUSD", tenor=tenor, t=t, f=F,
                                      nodes=tuple(sorted(nodes,
                                                  key=lambda n: n.strike))))
        return StrikeSurface(pair="EURUSD", smiles=tuple(smiles))

    def test_round_trip(self) -> None:
        fit = calibrate_ssvi(self.surface_from_ssvi())
        # rho is well identified; eta/gamma are collinear over a narrow
        # theta range, so assert SURFACE recovery, not parameter identity
        assert fit.rho == pytest.approx(-0.25, abs=1e-3)
        assert fit.eta == pytest.approx(0.9, rel=5e-2)
        assert fit.gamma == pytest.approx(0.45, abs=5e-2)
        assert fit.rmse < 0.02   # volpts; eta/gamma collinearity floor
        for k in (-0.08, -0.03, 0.04, 0.09):
            w_true = ssvi_total_variance(k, fit.thetas[Tenor.M3], -0.25,
                                         0.9, 0.45)
            w_fit = ssvi_total_variance(k, fit.thetas[Tenor.M3], fit.rho,
                                        fit.eta, fit.gamma)
            assert w_fit == pytest.approx(w_true, rel=2e-3)
        assert fit.calendar_ok and fit.butterfly_ok

    def test_theta_interpolation_monotone(self) -> None:
        fit = calibrate_ssvi(self.surface_from_ssvi())
        ts = np.linspace(1 / 12, 1.0, 50)
        th = [fit.theta_at(t) for t in ts]
        assert all(b >= a for a, b in zip(th, th[1:]))

    def test_atm_matched_by_construction(self) -> None:
        fit = calibrate_ssvi(self.surface_from_ssvi())
        assert fit.vol(F, Tenor.M3) == pytest.approx(0.075, abs=1e-12)


# --------------------------------------------------------------------------- #
class TestArbEngine:
    def clean_fit(self, tenor=Tenor.M3, t=T, alpha=0.10) -> SabrFit:
        return SabrFit(pair="EURUSD", tenor=tenor, t=t, f=F, alpha=alpha,
                       beta=1.0, rho=-0.3, nu=0.8, rmse=0.0, n_nodes=5)

    def test_clean_smile_positive_margin(self) -> None:
        m = butterfly_margin(self.clean_fit())
        assert m.min_g > 0

    def test_extreme_nu_compresses_margin(self) -> None:
        """Distance-to-arb must be continuous: cranking convexity toward the
        degenerate region shrinks min_g monotonically."""
        margins = [butterfly_margin(
            SabrFit(pair="EURUSD", tenor=Tenor.M3, t=T, f=F, alpha=0.10,
                    beta=1.0, rho=-0.3, nu=nu, rmse=0.0, n_nodes=5)).min_g
            for nu in (0.5, 2.0, 4.0, 6.0)]
        assert all(b < a for a, b in zip(margins, margins[1:]))
        assert margins[-1] < 0               # pushed into violation

    def test_calendar_violation_constructed(self) -> None:
        """Far tenor with LOWER total variance => negative margin."""
        near = self.clean_fit(Tenor.M1, t=1 / 12, alpha=0.12)
        far = self.clean_fit(Tenor.M3, t=0.25, alpha=0.05)  # w2 < w1 at ATM
        cms = calendar_margins([near, far])
        assert cms[0].min_dw < 0
        rep = check_surface("EURUSD", [near, far])
        assert not rep.clean
        assert any("calendar" in v for v in rep.violations)

    def test_clean_term_structure_passes(self) -> None:
        fits = [self.clean_fit(Tenor.M1, 1 / 12, 0.10),
                self.clean_fit(Tenor.M3, 0.25, 0.105),
                self.clean_fit(Tenor.M6, 0.5, 0.11)]
        assert check_surface("EURUSD", fits).clean


# --------------------------------------------------------------------------- #
class TestEndToEnd:
    def test_mock_universe_calibrates(self) -> None:
        from volwatch.analytics.surface import build_surface
        from volwatch.config import load_settings
        from volwatch.core.calendars import year_fractions
        from volwatch.data.provider import MockProvider

        settings = load_settings("config/settings.yaml")
        u = settings.universe
        snap = MockProvider().snapshot(u.all_pairs, u.tenors)
        yfs = year_fractions(snap.asof.date(), u.tenors)
        for pair in u.all_pairs:
            fwd = {f.tenor: f.outright for f in snap.forwards[pair]}
            fwd[Tenor.ON] = snap.spots[pair].mid
            ss = build_surface(snap.vols[pair], fwd, yfs,
                               {t: 0.02 for t in u.tenors})
            cs = calibrate_surface(ss)
            assert all(f.rmse < 0.15 for f in cs.sabr.values()), pair
            assert cs.arb.clean, (pair, cs.arb.violations)
            assert cs.ssvi.calendar_ok, pair
