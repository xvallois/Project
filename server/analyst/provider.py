"""Analyst model providers behind one seam.

AnthropicProvider — the real thing (needs ANTHROPIC_API_KEY; on the desk).
StubProvider     — deterministic, built from the evidence pack; used when
                   no key is present and in tests. Always labeled 'stub'
                   in the brief and in the UI. Never pretends to be Claude.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod

MODEL_FOR = {"triage": os.environ.get("VW_MODEL_TRIAGE",
                                      "claude-haiku-4-5-20251001"),
             "investigate": os.environ.get("VW_MODEL_INVESTIGATE",
                                           "claude-sonnet-4-6"),
             "deep": os.environ.get("VW_MODEL_DEEP", "claude-opus-4-8")}


class AnalystProvider(ABC):
    name = "abstract"

    @abstractmethod
    def complete(self, depth: str, system: str, user: str) -> str: ...


class AnthropicProvider(AnalystProvider):
    name = "claude"

    def __init__(self) -> None:
        import anthropic                       # hard dep only on this path
        self._client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY

    def complete(self, depth: str, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=MODEL_FOR[depth],
            max_tokens=1800 if depth == "deep" else 1200,
            system=system,
            messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in msg.content if b.type == "text")


class StubProvider(AnalystProvider):
    """Deterministic brief assembled from the evidence pack itself.

    Exists so the seam (schema, gate, budget, persistence, UI) is fully
    exercisable without a key. Its prose is templated; its citations are
    real; the numeric gate applies to it identically.
    """
    name = "stub"

    def complete(self, depth: str, system: str, user: str) -> str:
        if "EVIDENCE_JSON:" not in user:           # triage menu
            menu = json.loads(user)
            order = sorted(menu, key=lambda m: (-{"ACTIONABLE": 2,
                "WATCH": 1, "SPECULATIVE": 0}[m["band"]], -m["absZ"]))
            return json.dumps({"ranked": [
                {"id": m["id"], "note": f"{m['band'].lower()} · holds "
                 "attention while the driver persists"} for m in order]})
        payload = json.loads(user.split("EVIDENCE_JSON:\n", 1)[1])
        ev = payload["evidence"]
        by_tag = lambda t: [e["eid"] for e in ev if e["tag"] == t]
        sup, con, led = by_tag("supporting"), by_tag("contradiction"), \
            by_tag("ledger")
        first = lambda ids: ids[:2]
        sec = {
            "finding": [{"text": f"{payload['pair']} "
                         f"{payload['band'].lower()}-band dislocation — "
                         "evidence-led read below.",
                         "cites": first(sup) or [ev[0]["eid"]]}],
            "supporting": [{"text": f"{e['label']} stands at {e['value']}.",
                            "cites": [e["eid"]]} for e in ev
                           if e["tag"] == "supporting"][:3],
            "contradictory": ([{"text": f"Counterpoint: {e['label']} "
                                f"({e['value']}).", "cites": [e["eid"]]}
                               for e in ev if e["tag"] == "contradiction"][:2]
                              or [{"text": "No deterministic contradiction "
                                   "registered this cycle.", "cites": []}]),
            "why_now": [{"text": "The trigger is fresh this cycle and the "
                         "structure has not yet mean-reverted.",
                         "cites": first(sup)}],
            "invalidation": [{"text": "Watch for the driving metric "
                              "mean-reverting or the regime breaking.",
                              "cites": []}],
            "historical": ([{"text": f"Ledger: {e['label']} — {e['value']}.",
                             "cites": [e["eid"]]} for e in ev
                            if e["tag"] == "ledger"][:2]
                           or [{"text": "No prior episodes in the ledger "
                                "yet — this brief becomes the first one.",
                                "cites": []}]),
            "next_investigation": [{"text": "Open the smile panel at the "
                                    "driving tenor and compare realized "
                                    "beta before sizing.", "cites": []}],
        }
        return json.dumps(sec)
