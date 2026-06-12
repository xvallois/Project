"""Forward volatility extraction.

Math:  total variance is additive under no calendar arbitrage, so the
implied forward vol between expiries T1 < T2 is

    sigma_fwd(T1,T2) = sqrt( (sigma2^2*T2 - sigma1^2*T1) / (T2 - T1) )

Intuition: sigma_fwd is what the surface charges for vol over the FUTURE
window [T1,T2] only — the market's term price of "vol later". It is the
fair strike (to first order) of a forward vol agreement (FVA) and the lens
for term-structure RV: a 3M6M forward vol far above both spot 3M vol and
realized is the curve paying up for a future window, which is either an
event premium (real) or a dislocation (tradeable).

Negative forward variance == calendar arbitrage in the inputs. We return it
flagged rather than raising: the consumer (signals, dashboard) must see it.

Two variants:
  * ATM forward vol — from the ATM term structure (the FVA market quotes
    against this, modulo conventions).
  * Fixed-moneyness forward vol — from SSVI total variance at log-moneyness
    k, showing how the forward vol premium varies across the smile.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from volwatch.analytics.ssvi import SsviFit, ssvi_total_variance
from volwatch.core.models import Tenor

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ForwardVol:
    pair: str
    near: Tenor
    far: Tenor
    t1: float
    t2: float
    spot_vol_near: float          # decimal
    spot_vol_far: float
    fwd_vol: float | None         # None iff fwd variance < 0
    fwd_variance: float           # signed — diagnostic even when negative

    @property
    def valid(self) -> bool:
        return self.fwd_vol is not None

    @property
    def premium_to_far(self) -> float | None:
        """fwd vol minus far spot vol — the 'kink' the curve charges."""
        return None if self.fwd_vol is None else self.fwd_vol - self.spot_vol_far


def forward_vol(pair: str, near: Tenor, far: Tenor, t1: float, t2: float,
                vol1: float, vol2: float) -> ForwardVol:
    if t2 <= t1:
        raise ValueError(f"need t2 > t1, got {t1=} {t2=}")
    fwd_var = (vol2 * vol2 * t2 - vol1 * vol1 * t1) / (t2 - t1)
    fv = math.sqrt(fwd_var) if fwd_var > 0 else None
    if fv is None:
        log.warning("negative forward variance %s %s->%s: %.6f "
                    "(calendar arb in inputs)", pair, near.value, far.value,
                    fwd_var)
    return ForwardVol(pair=pair, near=near, far=far, t1=t1, t2=t2,
                      spot_vol_near=vol1, spot_vol_far=vol2,
                      fwd_vol=fv, fwd_variance=fwd_var)


def forward_vol_grid(pair: str, atm_curve: dict[Tenor, float],
                     ts: dict[Tenor, float],
                     adjacent_only: bool = False) -> list[ForwardVol]:
    """All T1<T2 pairs (or adjacent only) from an ATM curve (decimal vols)."""
    tenors = sorted(atm_curve, key=lambda t: ts[t])
    out = []
    for i, near in enumerate(tenors):
        fars = tenors[i + 1:i + 2] if adjacent_only else tenors[i + 1:]
        for far in fars:
            out.append(forward_vol(pair, near, far, ts[near], ts[far],
                                   atm_curve[near], atm_curve[far]))
    return out


def forward_vol_at_moneyness(ssvi: SsviFit, near: Tenor, far: Tenor,
                             k: float) -> ForwardVol:
    """Forward vol at fixed log-moneyness k from the SSVI fit."""
    t1, t2 = ssvi.ts[near], ssvi.ts[far]
    w1 = ssvi_total_variance(k, ssvi.thetas[near], ssvi.rho, ssvi.eta,
                             ssvi.gamma)
    w2 = ssvi_total_variance(k, ssvi.thetas[far], ssvi.rho, ssvi.eta,
                             ssvi.gamma)
    return forward_vol(ssvi.pair, near, far, t1, t2,
                       math.sqrt(w1 / t1), math.sqrt(w2 / t2))
