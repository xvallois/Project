"""Calibration orchestrator: StrikeSurface -> CalibratedSurface.

The CalibratedSurface is what signals and the dashboard consume: per-tenor
SABR fits, the global SSVI fit, the arb report, and cross-model diagnostics.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from volwatch.analytics.arbitrage import ArbReport, check_surface
from volwatch.analytics.sabr import SabrFit, calibrate_sabr
from volwatch.analytics.ssvi import SsviFit, calibrate_ssvi
from volwatch.analytics.surface import StrikeSurface
from volwatch.core.models import Tenor

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalibratedSurface:
    pair: str
    sabr: dict[Tenor, SabrFit]
    ssvi: SsviFit
    arb: ArbReport
    model_divergence: dict[Tenor, float]  # SABR-vs-SSVI rms, vol pts

    @property
    def worst_divergence(self) -> tuple[Tenor, float]:
        t = max(self.model_divergence, key=self.model_divergence.get)
        return t, self.model_divergence[t]


def calibrate_surface(surface: StrikeSurface,
                      beta: float = 1.0) -> CalibratedSurface:
    sabr_fits = {sm.tenor: calibrate_sabr(sm, beta=beta)
                 for sm in surface.smiles}
    ssvi_fit = calibrate_ssvi(surface)
    arb = check_surface(surface.pair, list(sabr_fits.values()))

    divergence: dict[Tenor, float] = {}
    for sm in surface.smiles:
        if sm.tenor not in ssvi_fit.ts:        # SSVI excludes short tenors
            continue
        sab = sabr_fits[sm.tenor]
        ks = sm.f * np.exp(np.linspace(-0.25, 0.25, 21))
        diff = [(sab.vol(k) - ssvi_fit.vol(k, sm.tenor)) * 100.0 for k in ks]
        divergence[sm.tenor] = float(np.sqrt(np.mean(np.square(diff))))
    return CalibratedSurface(pair=surface.pair, sabr=sabr_fits,
                             ssvi=ssvi_fit, arb=arb,
                             model_divergence=divergence)
