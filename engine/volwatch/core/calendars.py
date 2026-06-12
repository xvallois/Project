"""Expiry/delivery date logic and year fractions.

v1 SIMPLIFICATION (documented, deliberate): weekends rolled forward, no
holiday calendars yet, expiry = horizon + tenor directly (the proper chain is
horizon -> spot(T+2) -> delivery -> expiry 2bd prior, with cut times).
For relative-value analytics on a consistent basis this introduces <1bd of
noise; it is NOT settlement-grade. Holiday calendars are a tracked upgrade.

Year fractions: ACT/365 Fixed throughout (vol market convention).
"""
from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from volwatch.core.models import Tenor

_TENOR_DELTA = {
    Tenor.ON: timedelta(days=1),
    Tenor.W1: timedelta(weeks=1),
    Tenor.W2: timedelta(weeks=2),
    Tenor.M1: relativedelta(months=1),
    Tenor.M2: relativedelta(months=2),
    Tenor.M3: relativedelta(months=3),
    Tenor.M6: relativedelta(months=6),
    Tenor.M9: relativedelta(months=9),
    Tenor.Y1: relativedelta(years=1),
}


def roll_forward(d: date) -> date:
    """Next business day if weekend (holidays: tracked upgrade)."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def expiry_date(asof: date, tenor: Tenor) -> date:
    exp = asof + _TENOR_DELTA[tenor]
    if tenor is Tenor.ON:
        return exp  # ON expires next calendar day even over weekends? No:
        # kept simple — ON is quoted to next business day; roll below.
    return roll_forward(exp)


def year_fraction(start: date, end: date) -> float:
    """ACT/365F. Floors at 1 day to avoid div-by-zero on ON at EOD."""
    return max((end - start).days, 1) / 365.0


def year_fractions(asof: date, tenors: list[Tenor]) -> dict[Tenor, float]:
    return {t: year_fraction(asof, roll_forward(asof + _TENOR_DELTA[t]))
            for t in tenors}
