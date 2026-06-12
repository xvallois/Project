"""Snapshot validation.

Philosophy: the validator FLAGS, it never repairs or drops. Flagged data is
stored with its flags; analytics decide what to trust. Silent repair is how
trading systems develop haunted history.

Checks:
  * Staleness   — quote ts vs snapshot asof beyond a limit
  * Bounds      — ATM/RR/BF/spot inside sanity ranges
  * Jump        — change vs the previous *good* value beyond a limit
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import timedelta

from volwatch.core.models import (
    MarketSnapshot, QuoteStatus, SpotQuote, VolQuote, VolSurface,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ValidationLimits:
    staleness: timedelta = timedelta(minutes=30)
    atm_min: float = 0.5            # vol pts
    atm_max: float = 60.0
    abs_rr_max: float = 15.0
    abs_bf_max: float = 10.0
    atm_jump_max: float = 3.0       # vol pts between consecutive snaps
    spot_jump_max_pct: float = 2.0  # percent between consecutive snaps


@dataclass
class ValidationReport:
    snapshot_id: str
    flagged: list[str] = field(default_factory=list)   # human-readable issues

    @property
    def clean(self) -> bool:
        return not self.flagged

    def add(self, msg: str) -> None:
        self.flagged.append(msg)
        log.warning("validation: %s", msg)


class SnapshotValidator:
    """Stateful: remembers last good values to detect jumps."""

    def __init__(self, limits: ValidationLimits | None = None) -> None:
        self.limits = limits or ValidationLimits()
        self._last_atm: dict[tuple[str, str], float] = {}
        self._last_spot: dict[str, float] = {}

    def validate(self, snap: MarketSnapshot) -> tuple[MarketSnapshot, ValidationReport]:
        rep = ValidationReport(snapshot_id=snap.snapshot_id)
        lim = self.limits

        spots = {p: self._check_spot(s, snap, rep) for p, s in snap.spots.items()}
        vols = {p: VolSurface(pair=p, asof=surf.asof,
                              quotes=tuple(self._check_vol(q, snap, rep)
                                           for q in surf))
                for p, surf in snap.vols.items()}

        out = MarketSnapshot(asof=snap.asof, spots=spots,
                             forwards=snap.forwards, vols=vols,
                             rates=snap.rates, snapshot_id=snap.snapshot_id,
                             schema_version=snap.schema_version,
                             git_sha=snap.git_sha)
        return out, rep

    # ------------------------------------------------------------------ #
    def _check_spot(self, s: SpotQuote, snap: MarketSnapshot,
                    rep: ValidationReport) -> SpotQuote:
        status = s.status
        if snap.asof - s.ts > self.limits.staleness:
            status |= QuoteStatus.STALE
            rep.add(f"{s.pair} spot stale ({snap.asof - s.ts})")
        prev = self._last_spot.get(s.pair)
        if prev is not None and abs(s.mid / prev - 1) * 100 > self.limits.spot_jump_max_pct:
            status |= QuoteStatus.OUTLIER
            rep.add(f"{s.pair} spot jump {prev}->{s.mid}")
        if status == QuoteStatus.OK:
            self._last_spot[s.pair] = s.mid
        return replace(s, status=status)

    def _check_vol(self, q: VolQuote, snap: MarketSnapshot,
                   rep: ValidationReport) -> VolQuote:
        lim, status = self.limits, q.status
        key = (q.pair, q.tenor.value)
        if snap.asof - q.ts > lim.staleness:
            status |= QuoteStatus.STALE
            rep.add(f"{q.pair} {q.tenor.value} vol stale")
        if not (lim.atm_min <= q.atm <= lim.atm_max):
            status |= QuoteStatus.OUTLIER
            rep.add(f"{q.pair} {q.tenor.value} ATM out of bounds: {q.atm}")
        if abs(q.rr25) > lim.abs_rr_max or abs(q.bf25) > lim.abs_bf_max:
            status |= QuoteStatus.OUTLIER
            rep.add(f"{q.pair} {q.tenor.value} RR/BF out of bounds")
        prev = self._last_atm.get(key)
        if prev is not None and abs(q.atm - prev) > lim.atm_jump_max:
            status |= QuoteStatus.OUTLIER
            rep.add(f"{q.pair} {q.tenor.value} ATM jump {prev}->{q.atm}")
        if status == QuoteStatus.OK:
            self._last_atm[key] = q.atm
        return replace(q, status=status)
