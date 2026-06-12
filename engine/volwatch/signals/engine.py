"""Signal engine: builds the SignalContext from a snapshot + store, runs
every enabled signal from config/signals.yaml, returns a ranked SignalSet.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

# importing the signal modules populates the registry
import volwatch.signals.events  # noqa: F401
import volwatch.signals.relative_value  # noqa: F401
import volwatch.signals.richcheap  # noqa: F401
from volwatch.analytics.carry import carry_report
from volwatch.analytics.fit import CalibratedSurface, calibrate_surface
from volwatch.analytics.forward_vol import forward_vol_grid
from volwatch.analytics.realized import compute_realized
from volwatch.analytics.surface import build_surface
from volwatch.config import Settings
from volwatch.core.calendars import year_fractions
from volwatch.core.models import MarketSnapshot, Tenor
from volwatch.data.provider import MarketDataProvider
from volwatch.data.store import ParquetStore
from volwatch.signals.base import (
    REGISTRY, HistoryView, SignalContext, SignalInstance,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignalSet:
    asof: datetime
    instances: tuple[SignalInstance, ...]      # ranked by |score| desc

    def top(self, n: int) -> tuple[SignalInstance, ...]:
        return self.instances[:n]


def rf_curve_for(pair: str, rates, tenors: list[Tenor],
                 ts: dict[Tenor, float], default: float = 0.02
                 ) -> dict[Tenor, float]:
    """Base-ccy rate curve for strike solving (rf in GK is the BASE rate).

    Interpolates available RatePoints on year fraction; missing currencies
    fall back to `default` with a warning — visibly wrong is better than
    silently precise."""
    import numpy as np
    base_ccy = pair[:3]
    pts = rates.get(base_ccy, ())
    if not pts:
        log.warning("no %s rates in snapshot — rf default %.3f for %s",
                    base_ccy, default, pair)
        return {t: default for t in tenors}
    xs = [p_.tenor.nominal_year_fraction for p_ in pts]
    ys = [p_.rate for p_ in pts]
    order = np.argsort(xs)
    xs = [xs[i] for i in order]
    ys = [ys[i] for i in order]
    return {t: float(np.interp(ts[t], xs, ys)) for t in tenors}


def build_context(settings: Settings, snap: MarketSnapshot,
                  store: ParquetStore,
                  provider: MarketDataProvider | None = None,
                  history_days: int = 400,
                  ohlc_override: dict[str, pd.DataFrame] | None = None,
                  calibrate: bool = True,
                  history_cutoff=None,
                  history_view: HistoryView | None = None) -> SignalContext:
    """Build the per-cycle SignalContext.

    Replay mode (backtests): pass ohlc_override + history_cutoff and
    calibrate=False — no provider needed, no lookahead possible.
    """
    u = settings.universe
    ts = year_fractions(snap.asof.date(), u.tenors)

    ohlc: dict[str, pd.DataFrame] = {}
    realized, carry, calibrated, fwd = {}, {}, {}, {}
    end = snap.asof
    # iterate pairs PRESENT in the snapshot: partial snaps (provider
    # contract) must degrade gracefully, never kill the cycle
    for pair in [p_ for p_ in u.all_pairs if p_ in snap.vols]:
        if ohlc_override is not None:
            if pair not in ohlc_override:
                continue
            ohlc[pair] = ohlc_override[pair]
        else:
            try:
                ohlc[pair] = provider.history_ohlc(
                    pair, end - timedelta(days=history_days), end)
            except Exception as e:              # noqa: BLE001 — keep cycle alive
                log.error("history_ohlc failed %s: %s", pair, e)
                continue
        realized[pair] = compute_realized(pair, ohlc[pair])
        curve = snap.vols[pair].atm_curve()
        carry[pair] = carry_report(pair, curve, ts, realized[pair])
        fwd[pair] = forward_vol_grid(
            pair, {t: v / 100 for t, v in curve.items()}, ts,
            adjacent_only=True)
        if not calibrate:
            continue
        try:
            fmap = {f.tenor: f.outright for f in snap.forwards[pair]}
            fmap[Tenor.ON] = snap.spots[pair].mid
            rf = rf_curve_for(pair, snap.rates, u.tenors, ts)
            calibrated[pair] = calibrate_surface(
                build_surface(snap.vols[pair], fmap, ts, rf))
        except Exception as e:                  # noqa: BLE001
            log.error("calibration failed %s: %s — signals run without "
                      "model views for this pair", pair, e)

    return SignalContext(asof=snap.asof, snapshot=snap,
                         calibrated=calibrated, carry=carry, fwd_vols=fwd,
                         realized=realized, ohlc=ohlc,
                         history=history_view if history_view is not None
                         else HistoryView(store, cutoff=history_cutoff),
                         ts=ts)


class SignalEngine:
    def __init__(self, config_path: str | Path = "config/signals.yaml",
                 cfg: dict | None = None) -> None:
        if cfg is None:
            cfg = yaml.safe_load(Path(config_path).read_text())
        self.engine_cfg = cfg.get("engine", {})
        self.signal_cfg = cfg.get("signals", {})

    def run(self, ctx: SignalContext) -> SignalSet:
        instances: list[SignalInstance] = []
        for name, cls in REGISTRY.items():
            scfg = self.signal_cfg.get(name, {})
            if not scfg.get("enabled", False):
                continue
            try:
                found = cls(scfg).compute(ctx)
                log.info("signal %s: %d instances", name, len(found))
                instances.extend(found)
            except Exception:                   # noqa: BLE001
                log.exception("signal %s crashed — cycle continues, "
                              "signal skipped", name)
        instances.sort(key=lambda s: abs(s.score), reverse=True)
        top_n = int(self.engine_cfg.get("top_n", 20))
        return SignalSet(asof=ctx.asof, instances=tuple(instances[:top_n]))
