#!/usr/bin/env python3
"""Prompt compatibility gate (CI + release).

1. prompts/current resolves and contains both prompt files.
2. The system prompt still carries every CONTRACT element: strict JSON,
   the 7 sections, the cites protocol, the no-invented-numbers rule.
3. A stub investigation routed through the LIVE prompts produces an
   ok/degraded brief (the parse→gate path accepts the prompt's framing).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REQUIRED = ["finding", "supporting", "contradictory", "why_now",
            "invalidation", "historical", "next_investigation",
            "cites", "JSON", "never invent", "evidence"]


def main() -> int:
    from server.analyst.context import SYSTEM_PROMPT, _prompt_dir
    d = _prompt_dir()
    assert (d / "analyst_system.md").exists(), "system prompt missing"
    assert (d / "analyst_triage.md").exists(), "triage prompt missing"
    low = SYSTEM_PROMPT.lower()
    missing = [t for t in REQUIRED if t.lower() not in low]
    assert not missing, f"prompt lost contract elements: {missing}"

    # live-prompt smoke through the real pipeline (stub provider)
    from server.analyst.engine import investigate
    from server.analyst.provider import StubProvider
    from server.db import Db
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        db = Db(Path(t) / "e.db")
        card = {"id": "skew_richcheap|EURJPY|3M", "type": "skew_richcheap",
                "pair": "EURJPY", "tenors": ["3M"], "headline": "3M RR z +2.3",
                "structure": "3M", "band": "WATCH",
                "confidence": {"absZ": 2.3, "persistedCycles": 2,
                               "dataQualityOk": True, "modelsAgree": True,
                               "backtestPrior": None},
                "findings": "f", "evidence": [
                    {"label": "z-score", "value": "+2.31",
                     "provenance": "packet.signals[0].score"}],
                "supporting": [], "contradictions": [],
                "invalidation_criteria": ["reverts"],
                "similar_history_items": [], "similar_history_note": "",
                "status": "new", "created_at": "t", "updated_at": "t",
                "detected_at": "t", "dismissal": None, "invalidation": None}
        db.apply_cycle([card])
        out = investigate(card["id"], "investigate", "", db,
                          {"signals": [{"score": 2.31}], "health": {}},
                          StubProvider())
        assert out["status"] in ("ok", "degraded"), out
    print(f"prompts ok: {d.name} · contract elements present · "
          f"live-prompt investigation {out['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
