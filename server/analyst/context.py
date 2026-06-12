"""Evidence-pack assembly for an investigation (Phase 2).

The Analyst sees ONLY this pack: numbered deterministic items with
provenance, drawn from
  - the opportunity card itself,
  - related live cards (same pair / same type elsewhere),
  - contradicting signals (opposite direction, same pair),
  - engine health for the pair,
  - the DECISION LEDGER: past episodes of this opportunity, what the
    trader did, what it realized — institutional memory, deterministic,
    with ledger: provenance refs.

The pack is the boundary: nothing outside it may become a number in the
brief.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from server.analyst.schema import Evidence


def _ev(n: int, label: str, value: str, prov: str, tag: str) -> dict:
    return {**asdict(Evidence(f"E{n}", label, value, prov)), "tag": tag}


def ledger_memory(db, card: dict) -> list[dict]:
    """Past episodes of this opportunity family, from SQLite."""
    out = []
    kind_key = card["id"].split("|")[0]
    rows = db._con.execute(
        """SELECT c.id, c.status, c.payload,
                  b.pnl_volpts, b.notes, b.status AS bstatus
           FROM cards c LEFT JOIN blotter b
             ON b.linked_opportunity_id = c.id
           WHERE c.id LIKE ? AND c.id != ?
           ORDER BY c.updated_at DESC LIMIT 6""",
        (f"{kind_key}|%", card["id"])).fetchall()
    for r in rows:
        p = json.loads(r["payload"])
        outcome = (f"pnl {r['pnl_volpts']:+.2f}vp ({r['notes'] or 'no note'})"
                   if r["pnl_volpts"] is not None
                   else (p.get("dismissal") or {}).get("reason")
                   or r["status"])
        out.append({"id": r["id"], "pair": p["pair"],
                    "status": r["status"], "outcome": outcome})
    return out


def funnel_stats(db, opp_type: str) -> dict:
    row = db._con.execute(
        """SELECT
             sum(CASE WHEN event='generated' THEN 1 ELSE 0 END) gen,
             sum(CASE WHEN event='acted' THEN 1 ELSE 0 END) acted,
             sum(CASE WHEN event='dismissed' THEN 1 ELSE 0 END) dis,
             sum(CASE WHEN event='invalidated' THEN 1 ELSE 0 END) inv
           FROM events WHERE card_id LIKE ?""",
        (f"{opp_type}|%",)).fetchone()
    return {k: row[k] or 0 for k in ("gen", "acted", "dis", "inv")}


def build_pack(card: dict, all_cards: list[dict], packet: dict,
               db, workspace_brief: str = "") -> dict:
    ev: list[dict] = []
    n = 0

    def add(label: str, value: str, prov: str, tag: str) -> None:
        nonlocal n
        n += 1
        ev.append(_ev(n, label, value, prov, tag))

    for it in card.get("evidence", []):
        add(it["label"], it["value"], it["provenance"], "supporting")
    for it in card.get("supporting", []):
        add(it["label"], it["value"], it["provenance"], "supporting")
    for it in card.get("contradictions", []):
        add(it["label"], it["value"], it["provenance"], "contradiction")

    live = [c for c in all_cards
            if c["status"] in ("new", "seen", "watching", "acted")
            and c["id"] != card["id"]]
    for c in live:
        if c["pair"] == card["pair"]:
            add(f"co-signal {c['type']}", c["headline"],
                f"derived:card({c['id']})", "supporting")
        elif c["type"] == card["type"]:
            add(f"same family elsewhere ({c['pair']})", c["headline"],
                f"derived:card({c['id']})", "context")
    ph = packet.get("health", {}).get(card["pair"], {})
    div = (ph.get("model_divergence_worst") or {}).get("volpts")
    if div is not None:
        add("SABR/SSVI worst divergence", f"{div:.2f}vp",
            f"packet.health.{card['pair']}.model_divergence_worst.volpts",
            "contradiction" if div >= 4.0 else "supporting")

    # ---- institutional memory --------------------------------------------
    for ep in ledger_memory(db, card):
        add(f"prior episode {ep['id']}",
            f"{ep['status']} → {ep['outcome']}",
            f"ledger:card({ep['id']})", "ledger")
    fs = funnel_stats(db, card["id"].split("|")[0])
    if fs["gen"]:
        add(f"{card['type']} funnel to date",
            f"{fs['gen']} generated / {fs['acted']} acted / "
            f"{fs['dis']} dismissed / {fs['inv']} invalidated",
            f"ledger:funnel({card['id'].split('|')[0]})", "ledger")

    return {"card_id": card["id"], "headline": card["headline"],
            "pair": card["pair"], "band": card["band"],
            "findings": card["findings"],
            "invalidation": card["invalidation_criteria"],
            "workspace_brief": workspace_brief,
            "evidence": ev}


from pathlib import Path as _P

_PROMPT_FILE = _P(__file__).resolve().parents[2] / "prompts" / "analyst_system.md"
SYSTEM_PROMPT = "\n".join(
    l for l in _PROMPT_FILE.read_text().splitlines()
    if not l.startswith("<!--") and not l.endswith("-->"))



def user_prompt(pack: dict) -> str:
    return ("Write the note for this opportunity.\n"
            f"Workspace standing brief: {pack['workspace_brief'] or '—'}\n"
            "EVIDENCE_JSON:\n" + json.dumps(pack))
