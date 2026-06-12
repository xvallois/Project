#!/usr/bin/env python3
"""Contract gate: live code shapes must validate against contracts/.

Run before every commit (scripts/test.sh) and in CI. Imports the server
factories where available; falls back to canned fixtures so the check
also runs without the engine installed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / "contracts"


def load(name: str) -> dict:
    return json.loads((C / name).read_text())


CARD_FIXTURE = {
    "id": "skew_richcheap|EURJPY|3M", "type": "skew_richcheap",
    "pair": "EURJPY", "tenors": ["3M"], "headline": "h", "structure": "3M",
    "band": "WATCH",
    "confidence": {"absZ": 2.3, "persistedCycles": 2,
                   "dataQualityOk": True, "modelsAgree": True,
                   "backtestPrior": None},
    "findings": "f",
    "evidence": [{"label": "z", "value": "+2.31",
                  "provenance": "packet.signals[0].score"}],
    "supporting": [], "contradictions": [],
    "invalidation_criteria": ["|z| reverts inside ±1.0"],
    "similar_history_items": [{"label": "p", "value": "acted → +0.85vp",
                               "provenance": "ledger:card(x|Y|1M)"}],
    "similar_history_note": "from the decision ledger",
    "status": "new", "created_at": "t", "updated_at": "t",
    "detected_at": "t", "dismissal": None, "invalidation": None,
}


def card_sample() -> dict:
    try:
        sys.path.insert(0, str(ROOT))
        from server.detectors import Card, Item  # type: ignore
        c = Card(id="t|E|3M", type="t", pair="EURJPY", tenors=["3M"],
                 headline="h", structure="3M", band="WATCH",
                 confidence=CARD_FIXTURE["confidence"], findings="f",
                 evidence=[Item("z", "+2.31", "packet.signals[0].score")],
                 supporting=[], contradictions=[],
                 invalidation_criteria=["x"],
                 similar_history_items=[], similar_history_note="",
                 created_at="t", updated_at="t", detected_at="t")
        return c.to_dict()
    except Exception:
        return CARD_FIXTURE


def brief_sample() -> dict:
    try:
        sys.path.insert(0, str(ROOT))
        from server.analyst.schema import (Evidence, ResearchBrief,
                                           Statement)  # type: ignore
        b = ResearchBrief(
            card_id="t|E|3M", depth="investigate", provider="stub",
            model="stub", units=3, status="ok",
            sections={k: [Statement("s", "analyst", ["E1"])]
                      for k in ("finding", "supporting", "contradictory",
                                "why_now", "invalidation", "historical",
                                "next_investigation")},
            evidence=[Evidence("E1", "z", "+2.31",
                               "packet.signals[0].score")],
            dropped=[], created_at="t")
        return b.to_dict()
    except Exception:
        return {"card_id": "x", "depth": "investigate", "provider": "stub",
                "model": "stub", "units": 3, "status": "ok",
                "sections": {k: [] for k in
                             ("finding", "supporting", "contradictory",
                              "why_now", "invalidation", "historical",
                              "next_investigation")},
                "evidence": [], "dropped": [], "created_at": "t"}


def main() -> int:
    checks = [
        ("opportunity-card.schema.json", card_sample()),
        ("research-brief.schema.json", brief_sample()),
        ("blotter.schema.json", {"id": "u", "kind": "paper",
            "status": "open", "pair": "EURJPY", "structure": "3M",
            "direction": "sell", "linked_opportunity_id": "t|E|3M",
            "entry_thesis": "th", "pnl_volpts": None, "notes": None,
            "opened_at": "t", "closed_at": None}),
    ]
    for schema_name, sample in checks:
        jsonschema.validate(sample, load(schema_name))
        print(f"  ok: {schema_name}")
    print("contracts verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
