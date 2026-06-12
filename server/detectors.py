"""Tier-1 detectors over REAL volwatch analytics (Phase 1 §1).

Sources, in order of authority:
  1. the engine's SignalEngine output (already z-scored, documented,
     with edge estimates) — mapped 1:1 into observations with refs into
     the cycle packet;
  2. surface percentile scans over store history (rich/cheap context the
     signal library doesn't z-score directly).

Every numeric carries a provenance ref (see provenance.py). Cards are
ANALYST-SHAPED from day one: findings / evidence / supporting /
contradictions / invalidation_criteria / similar_history. The
deterministic placeholders are labeled as such — Phase 2 swaps content,
never schema.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

BAND_RANK = {"SPECULATIVE": 0, "WATCH": 1, "ACTIONABLE": 2}

# Placeholder priors until real backtest history accumulates (labeled).
_PRIOR = {"skew_richcheap": (0.61, 42), "term_structure_kink": (0.55, 37),
          "vol_risk_premium": (0.52, 64), "triangle_correlation": (0.58, 21),
          "event_vol": (0.57, 18)}


@dataclass
class Item:                          # one numeric claim, one ref
    label: str
    value: str
    provenance: str


@dataclass
class Card:
    id: str
    type: str
    pair: str
    tenors: list[str]
    headline: str
    structure: str
    band: str
    confidence: dict[str, Any]
    findings: str
    evidence: list[Item]
    supporting: list[Item]
    contradictions: list[Item]
    invalidation_criteria: list[str]
    similar_history_items: list[Item]
    similar_history_note: str
    status: str = "new"
    created_at: str = ""
    updated_at: str = ""
    detected_at: str = ""
    dismissal: dict | None = None
    invalidation: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def band_for(absz: float, persisted: int, dq_ok: bool, models_agree: bool,
             prior_ok: bool) -> str:
    # COERCE: numpy scalars leak in from the percentile pipeline, and
    # numpy's `+` on np.bool_ is logical OR — the evidence score would
    # silently saturate at 1 and band everything SPECULATIVE. Found by
    # decision-session replay (production-only; unit tests passed floats).
    absz = float(absz)
    if not dq_ok:
        return "SPECULATIVE"            # flags can never be actionable
    score = int(absz >= 1.5) + int(absz >= 2.5) + int(persisted >= 2) \
        + int(bool(models_agree)) + int(bool(prior_ok))
    return "ACTIONABLE" if score >= 4 else "WATCH" if score >= 2 \
        else "SPECULATIVE"


_INVALIDATION = {
    "skew_richcheap": ["|z| reverts inside ±1.0",
                       "RR percentile crosses p50",
                       "spot-vol beta regime breaks (delivered follows implied)"],
    "term_structure_kink": ["kink residual < 0.05vp",
                            "neighbouring tenor repriced (kink migrates)"],
    "vol_risk_premium": ["IV-RV gap inside ±0.5vp",
                         "realized vol regime shift (YZ 10d vs 60d)"],
    "triangle_correlation": ["implied-realized corr gap < 0.15",
                             "leg correlation regime shift"],
    "event_vol": ["event passes (bucket rolls)",
                  "premium ratio inside [0.8, 1.3]"],
}


def detect(packet: dict, store, settings,
           live_ids: set[str] | None = None) -> list[Card]:
    """Build analyst-shaped cards from the live cycle packet + store.

    `live_ids`: ids currently live in the feed — percentile detectors use
    hysteresis (enter p95/p5, persist to p90/p10) so cards don't churn
    invalidate/regenerate while a metric breathes around the threshold."""
    live_ids = live_ids or set()
    cards: list[Card] = []
    now = _now()
    health = packet.get("health", {})

    # ---- source 1: the engine's own signals, packet-referenced ----------
    for i, sig in enumerate(packet.get("signals", [])):
        z = sig.get("score")
        if z is None:
            continue
        pair, name = sig["pair"], sig["signal"]
        cid = f"{name}|{pair}|{sig.get('structure', '')}"
        if abs(z) < (1.2 if cid in live_ids else 1.5):
            continue                       # hysteresis vs threshold flicker
        tenors = [t for t in str(sig.get("structure", "")).replace("/", " ")
                  .split() if t in ("ON", "1W", "2W", "1M", "2M", "3M",
                                    "6M", "9M", "1Y")]
        ph = health.get(pair, {})
        models_agree = (ph.get("model_divergence_worst", {})
                        .get("volpts", 0) or 0) < 4.0
        dq_ok = not sig.get("data_flags")
        prior = _PRIOR.get(name)
        b = band_for(abs(z), 1, dq_ok, models_agree,
                     bool(prior and prior[0] >= 0.55 and prior[1] >= 20))
        contradictions: list[Item] = []
        if not models_agree:
            contradictions.append(Item(
                "model disagreement",
                f"SABR/SSVI diverge {ph['model_divergence_worst']['volpts']:.1f}vp",
                f"packet.health.{pair}.model_divergence_worst.volpts"))
        ev = [Item("z-score", f"{z:+.2f}", f"packet.signals[{i}].score"),
              Item("edge estimate",
                   f"{sig.get('edge_estimate_volpts', 0):+.2f}vp",
                   f"packet.signals[{i}].edge_estimate_volpts")]
        cards.append(Card(
            id=cid,
            type=name, pair=pair, tenors=tenors,
            headline=f"{sig.get('structure', name)}: "
                     f"{sig.get('direction', '')} z {z:+.1f}",
            structure=sig.get("structure", ""),
            band=b,
            confidence={"absZ": abs(z), "persistedCycles": 1,
                        "dataQualityOk": dq_ok, "modelsAgree": models_agree,
                        "backtestPrior": {"hitRate": prior[0], "n": prior[1],
                                          "placeholder": True} if prior
                        else None},
            findings=str(sig.get("intuition", ""))[:240],
            evidence=ev,
            supporting=[],
            contradictions=contradictions,
            invalidation_criteria=_INVALIDATION.get(name,
                ["|z| reverts inside ±1.0"]),
            similar_history_items=[Item(
                "prior hit rate (placeholder)",
                f"{prior[0]:.0%} (n={prior[1]})" if prior else "no prior",
                f"prior:{name}")],
            similar_history_note="placeholder prior — real episode search "
                                 "ships with the backtest dataset",
            created_at=now, updated_at=now, detected_at=now))

    # ---- source 2: surface percentile scans over store history ----------
    hist = store.query(
        'SELECT pair, tenor, "asof", atm, rr25, bf25 FROM vol '
        "WHERE status = 0")
    if not hist.empty:
        hist["date"] = pd.to_datetime(hist["asof"]).dt.date
        daily = (hist.sort_values("asof")
                 .groupby(["pair", "tenor", "date"], as_index=False).last())
        breaches: dict[tuple[str, str, int], list[dict]] = {}
        for (pair, tenor), g in daily.groupby(["pair", "tenor"]):
            if len(g) < 40:
                continue                       # not enough history to rank
            for fld in ("atm", "rr25"):
                series = g[fld].to_numpy()
                cur, past = series[-1], series[:-1]
                pct = 100.0 * ((past < cur).sum()
                               + 0.5 * (past == cur).sum()) / len(past)
                kind = "SKEW_PCTILE" if fld == "rr25" else "ATM_PCTILE"
                already_live = (f"{kind}|{pair}|{tenor}" in live_ids
                                or f"{kind}|{pair}|*" in live_ids)
                enter = pct >= 95 or pct <= 5
                hold = already_live and (pct >= 90 or pct <= 10)
                if not (enter or hold):
                    continue
                sd = past.std()
                z = 0.0 if sd < 1e-12 else (cur - past.mean()) / sd
                breaches.setdefault((pair, fld, 1 if pct >= 50 else -1),
                                    []).append(dict(
                    tenor=tenor, cur=cur, pct=pct, z=z, n=len(past)))
        for (pair, fld, sign), hits in breaches.items():
            kind = "SKEW_PCTILE" if fld == "rr25" else "ATM_PCTILE"
            if len(hits) >= 3:
                # ONE surface-level card, not N tenor cards: a broad drift
                # is one event. Tenor detail stays in evidence.
                lead = max(hits, key=lambda h: abs(h["z"]))
                tenors = [h["tenor"] for h in hits]
                rich = sign > 0
                cards.append(Card(
                    id=f"{kind}|{pair}|*",
                    type=f"SURFACE_{'RICH' if rich else 'CHEAP'}",
                    pair=pair, tenors=tenors,
                    headline=f"{fld} {'rich' if rich else 'cheap'} across "
                             f"{len(hits)} tenors (lead {lead['tenor']} "
                             f"p{lead['pct']:.0f})",
                    structure=f"{fld} curve",
                    band=band_for(abs(lead["z"]), 1, True, True, False),
                    confidence={"absZ": round(abs(lead["z"]), 2),
                                "persistedCycles": 1, "dataQualityOk": True,
                                "modelsAgree": True, "backtestPrior": None},
                    findings=f"Broad {fld} repricing — one event, "
                             f"{len(hits)} tenors at extremes; trade the "
                             f"curve, not a node.",
                    evidence=[Item(
                        f"{h['tenor']} {fld}",
                        f"{h['cur']:.3f} (p{h['pct']:.0f})",
                        f"derived:percentile(store://vol/{pair}/"
                        f"{h['tenor']}/{fld})") for h in hits[:6]],
                    supporting=[Item("lead z", f"{lead['z']:+.2f}",
                        f"derived:zscore(store://vol/{pair}/"
                        f"{lead['tenor']}/{fld})")],
                    contradictions=[Item(
                        "single driver",
                        "tenor breaches share one underlying drift — not "
                        "independent confirmations",
                        f"derived:count(store://vol/{pair}/"
                        f"{lead['tenor']}/{fld})")],
                    invalidation_criteria=[
                        f"fewer than 3 tenors beyond p90/p10",
                        f"lead tenor {fld} crosses p50"],
                    similar_history_items=[Item(
                        "prior (placeholder)", "no prior",
                        f"prior:surface_{fld}")],
                    similar_history_note="placeholder — episode search "
                                         "ships with backtest dataset",
                    created_at=now, updated_at=now, detected_at=now))
                continue
            for h in hits:
                tenor, cur, pct, z = h["tenor"], h["cur"], h["pct"], h["z"]
                b = band_for(abs(z), 1, True, True, False)
                store_ref = f"store://vol/{pair}/{tenor}/{fld}"
                cards.append(Card(
                    id=f"{kind}|{pair}|{tenor}",
                    type=kind, pair=pair, tenors=[tenor],
                    headline=f"{tenor} {fld} at p{pct:.0f} of stored history",
                    structure=f"{tenor} "
                              f"{'25d risk reversal' if fld == 'rr25' else 'ATM'}",
                    band=b,
                    confidence={"absZ": round(abs(z), 2),
                                "persistedCycles": 1, "dataQualityOk": True,
                                "modelsAgree": True, "backtestPrior": None},
                    findings=f"{fld} at the {'rich' if pct > 50 else 'cheap'}"
                             f" extreme of everything this store has seen "
                             f"({h['n']}d).",
                    evidence=[
                        Item(fld, f"{cur:.3f}", store_ref),
                        Item("percentile", f"p{pct:.0f}",
                             f"derived:percentile({store_ref})"),
                        Item("z-score", f"{z:+.2f}",
                             f"derived:zscore({store_ref})")],
                    supporting=[Item("history depth", f"{h['n']}d",
                                     f"derived:count({store_ref})")],
                    contradictions=[] if h['n'] >= 120 else [Item(
                        "shallow history",
                        f"only {h['n']}d — percentile unstable",
                        f"derived:count({store_ref})")],
                    invalidation_criteria=[f"{fld} crosses p50",
                                           "history depth < 40d after a "
                                           "data-quality purge"],
                    similar_history_items=[Item(
                        "prior (placeholder)", "no prior",
                        f"prior:{kind.lower()}")],
                    similar_history_note="placeholder — episode search "
                                         "ships with backtest dataset",
                    created_at=now, updated_at=now, detected_at=now))
    return cards
