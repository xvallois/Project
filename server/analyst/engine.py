"""Analyst orchestrator (Phase 2).

investigate(): Opportunity -> evidence pack -> capped model loop ->
numeric gate -> persisted ResearchBrief. Budget-gated server-side; a
refusal is a typed result and never touches the deterministic feed.

triage(): one cheap pass per cycle ranking live cards with a one-line
desk note each. Writes analyst_rank/analyst_note ALONGSIDE the
deterministic fields — never over them.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from server.analyst.context import SYSTEM_PROMPT, build_pack, user_prompt
from server.analyst.provider import AnalystProvider, MODEL_FOR
from server.analyst.schema import (Evidence, ResearchBrief, Statement,
                                   gate_brief)

log = logging.getLogger("analyst")

UNITS = {"triage": 1, "investigate": 3, "deep": 10}

from pathlib import Path as _P
from server.analyst.context import _prompt_dir
_TRIAGE_PROMPT = "\n".join(
    l for l in (_prompt_dir() / "analyst_triage.md")
    .read_text().splitlines() if not l.startswith("<!--"))
MAX_LOOP = 2                       # capped analysis loop


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(raw: str) -> dict | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        a, b = raw.find("{"), raw.rfind("}")
        if a >= 0 and b > a:
            try:
                return json.loads(raw[a:b + 1])
            except json.JSONDecodeError:
                return None
    return None


def brief_from_pack(pack: dict, depth: str,
                    provider: AnalystProvider) -> ResearchBrief | None:
    """Pack -> gated brief. Shared by live investigations and the
    evaluation harness (frozen packs). Returns None if unparseable
    after the capped loop."""
    evidence = {e["eid"]: Evidence(e["eid"], e["label"], e["value"],
                                   e["provenance"])
                for e in pack["evidence"]}
    sections_raw = None
    for attempt in range(MAX_LOOP):
        raw = provider.complete(depth, SYSTEM_PROMPT, user_prompt(pack))
        sections_raw = _parse(raw)
        if sections_raw is not None:
            break
        log.warning("analyst returned unparseable output (attempt %d)",
                    attempt + 1)
    if sections_raw is None:
        return None
    sections = {k: [Statement(s.get("text", ""), "analyst",
                              list(s.get("cites", [])))
                    for s in v] for k, v in sections_raw.items()
                if isinstance(v, list)}
    clean, dropped, status = gate_brief(sections, evidence)
    # The engine's own invalidation criteria ALWAYS reach the brief as
    # deterministic statements (they are engine text, outside the analyst
    # gate); the model may add color but can never displace them.
    if status != "rejected":
        det = [Statement(t, "deterministic", [])
               for t in pack.get("invalidation", [])[:3]]
        clean["invalidation"] = det + [
            st for st in clean.get("invalidation", [])
            if st.text not in {d.text for d in det}]
    return ResearchBrief(
        card_id=pack["card_id"], depth=depth, provider=provider.name,
        model=MODEL_FOR[depth] if provider.name == "claude" else "stub",
        units=UNITS[depth], status=status,
        sections={k: v for k, v in clean.items()},
        evidence=list(evidence.values()), dropped=dropped,
        created_at=_now())


def investigate(card_id: str, depth: str, workspace_brief: str,
                db, packet: dict, provider: AnalystProvider) -> dict:
    cards = db.all_cards()
    card = next((c for c in cards if c["id"] == card_id), None)
    if card is None:
        return {"error": "unknown card", "card_id": card_id}

    spend = db.budget_spend("analysis" if depth == "investigate"
                            else "deep" if depth == "deep" else "triage",
                            UNITS[depth])
    if not spend["ok"]:
        db.record("analyst_refused", card_id,
                  {"reason": spend["reason"], "depth": depth})
        return {"refused": spend["reason"], "budget": db.budget_state(),
                "card_id": card_id}

    pack = build_pack(card, cards, packet, db, workspace_brief)
    brief = brief_from_pack(pack, depth, provider)
    if brief is None:
        db.record("analyst_rejected", card_id, {"reason": "unparseable"})
        return {"error": "analyst output unparseable after capped retries",
                "card_id": card_id}
    d = brief.to_dict()
    db.brief_add(d)
    db.record("analyst_brief", card_id,
              {"depth": depth, "status": brief.status,
               "units": UNITS[depth], "dropped": len(brief.dropped),
               "provider": provider.name})
    if brief.status == "rejected":
        log.error("brief REJECTED for %s: %s", card_id, brief.dropped[:3])
    return d


def triage(db, packet: dict, provider: AnalystProvider,
           limit: int = 8) -> dict | None:
    """Cheap per-cycle pass: rank live cards, one-liner each. Optional —
    skipped silently when the budget (or its triage reserve) is gone;
    the deterministic feed is untouched either way."""
    live = [c for c in db.all_cards()
            if c["status"] in ("new", "seen", "watching")][:limit]
    if not live:
        return None
    spend = db.budget_spend("triage", UNITS["triage"])
    if not spend["ok"]:
        return None
    menu = [{"id": c["id"], "headline": c["headline"], "band": c["band"],
             "absZ": c["confidence"]["absZ"],
             "persisted": c["confidence"]["persistedCycles"]} for c in live]
    raw = provider.complete("triage", _TRIAGE_PROMPT, json.dumps(menu))
    parsed = _parse(raw) or {}
    ranked = parsed.get("ranked", [])
    known = {c["id"] for c in live}
    out = [r for r in ranked if r.get("id") in known][:limit]
    for rank, r in enumerate(out):
        db.set_analyst_rank(r["id"], rank, str(r.get("note", ""))[:140])
    db.record("analyst_triage", None,
              {"ranked": len(out), "provider": provider.name})
    return {"ranked": out}
