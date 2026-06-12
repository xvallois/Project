"""Research packet assembly.

The ResearchPacket is the single source of truth handed to ANY researcher
(template engine today, Anthropic/local LLM later). Design rules:

  * Everything quantitative a write-up may state MUST exist in the packet.
    The packet is stored alongside every write-up — full audit trail, and
    later the literal prompt payload.
  * The packet is plain dict/JSON-serializable: no domain objects leak
    through, so the researcher layer has zero coupling to analytics.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from volwatch.signals.base import REGISTRY, SignalContext, SignalInstance
from volwatch.signals.engine import SignalSet

log = logging.getLogger(__name__)

PACKET_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ResearchPacket:
    asof: datetime
    schema_version: int
    signals: list[dict[str, Any]]          # instance + its signal docs
    market: dict[str, Any]                 # per-pair carry / curve / skew
    arb: dict[str, Any]                    # margins + violations per pair
    health: dict[str, Any]                 # fit rmse, divergence, flags

    def to_json(self) -> str:
        d = asdict(self)
        d["asof"] = self.asof.isoformat()
        return json.dumps(d, default=str, indent=2)


def assemble_packet(ctx: SignalContext, signals: SignalSet,
                    top_n: int = 8) -> ResearchPacket:
    sig_rows = []
    for s in signals.top(top_n):
        cls = REGISTRY[s.signal]
        sig_rows.append({
            "signal": s.signal, "pair": s.pair, "structure": s.structure,
            "direction": s.direction.value, "score": round(s.score, 3),
            "value": round(s.value, 4),
            "edge_estimate_volpts": round(s.edge_estimate, 3),
            "tenors": [t.value for t in s.tenors],
            "details": _round(s.details),
            "docs": {"math": cls.math, "intuition": cls.intuition,
                     "edge": cls.edge, "failure_modes": cls.failure_modes},
        })

    market: dict[str, Any] = {}
    for pair, rep in ctx.carry.items():
        surf = ctx.snapshot.vols[pair]
        market[pair] = {
            "spot": ctx.snapshot.spots[pair].mid,
            "atm_curve": {t.value: round(v, 3)
                          for t, v in surf.atm_curve().items()},
            "rr25": {q.tenor.value: round(q.rr25, 3) for q in surf},
            "bf25": {q.tenor.value: round(q.bf25, 3) for q in surf},
            "carry": [{
                "tenor": tc.tenor.value, "implied": round(tc.implied, 3),
                "realized": round(tc.realized_matched, 3),
                "iv_rv": round(tc.iv_rv_spread, 3),
                "rolldown_1w": None if tc.rolldown_1w is None
                else round(tc.rolldown_1w, 4),
                "breakeven_daily_pct": round(tc.breakeven_daily_pct, 4),
            } for tc in rep.tenors],
            "fwd_vols": [{
                "pair": fv.near.value + "->" + fv.far.value,
                "fwd_vol": None if fv.fwd_vol is None
                else round(fv.fwd_vol * 100, 3),
                "kink_to_far": None if fv.premium_to_far is None
                else round(fv.premium_to_far * 100, 3),
            } for fv in ctx.fwd_vols.get(pair, [])],
        }

    arb: dict[str, Any] = {}
    health: dict[str, Any] = {}
    for pair, cs in ctx.calibrated.items():
        arb[pair] = {
            "violations": list(cs.arb.violations),
            "min_butterfly_g": round(min(b.min_g for b in cs.arb.butterfly), 5)
            if cs.arb.butterfly else None,
            "min_calendar_dw": round(min(c.min_dw for c in cs.arb.calendar), 6)
            if cs.arb.calendar else None,
        }
        worst_t, worst_d = cs.worst_divergence
        health[pair] = {
            "sabr_rmse_max": round(max(f.rmse for f in cs.sabr.values()), 4),
            "ssvi_rmse": round(cs.ssvi.rmse, 4),
            "model_divergence_worst": {"tenor": worst_t.value,
                                       "volpts": round(worst_d, 4)},
            "ssvi_no_arb": cs.ssvi.butterfly_ok and cs.ssvi.calendar_ok,
        }

    return ResearchPacket(asof=ctx.asof,
                          schema_version=PACKET_SCHEMA_VERSION,
                          signals=sig_rows, market=market, arb=arb,
                          health=health)


def _round(d: dict[str, Any], nd: int = 4) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = round(v, nd)
        elif isinstance(v, dict):
            out[k] = _round(v, nd)
        else:
            out[k] = v
    return out
