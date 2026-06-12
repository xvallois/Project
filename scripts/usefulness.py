#!/usr/bin/env python3
"""Usefulness — the institutional KPI (release directive #3).

usefulness_score = weighted(investigate_rate .20, blotter_rate .25,
                            survival .20, manual_score .25,
                            dismissal_quality .10)

  survival           = 1 - ignored/generated (cards that earned attention)
  dismissal_quality  = dismissals carrying a reason / dismissals
                       (structurally 1.0 today via the picklist; the slot
                       is reserved for re-escalation-rate refinement)
  manual_score       = 0..1 from the signed release review (top-10
                       usefulness ratio), passed via --manual

Stored per (release, prompt_version, workspace, signal_family) under
evaluation/metrics/usefulness/. ANTI-OVERFITTING GATE (directive #4):
vs the previous release record, action rate (blotter_rate) may not rise
while usefulness falls — 'pretty UI creates fake conviction' fails here.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
W = {"investigate_rate": .20, "blotter_rate": .25, "survival": .20,
     "manual_score": .25, "dismissal_quality": .10}
OUT = ROOT / "evaluation" / "metrics" / "usefulness"


def components(db, manual: float) -> dict:
    m = db.decision_metrics()
    gen = m["generated"] or 1
    dis = db._con.execute(
        "SELECT count(*) n, sum(CASE WHEN payload LIKE '%reason%' THEN 1 "
        "ELSE 0 END) r FROM events WHERE event='dismissed'").fetchone()
    return {"investigate_rate": m["investigate_rate"] or 0.0,
            "blotter_rate": m["blotter_rate"] or 0.0,
            "survival": round(1 - (m["ignored"] / gen), 3),
            "manual_score": manual,
            "dismissal_quality": round((dis["r"] or 0) / dis["n"], 3)
            if dis["n"] else 1.0}


def score(c: dict) -> float:
    return round(sum(W[k] * c[k] for k in W), 4)


def by_family(db, manual: float) -> dict:
    fams = {r["card_id"].split("|")[0] for r in db._con.execute(
        "SELECT DISTINCT card_id FROM events WHERE card_id LIKE '%|%'")}
    out = {}
    for fam in sorted(fams):
        rows = db._con.execute(
            "SELECT card_id, event FROM events WHERE card_id LIKE ?",
            (f"{fam}|%",)).fetchall()
        ids = {r["card_id"] for r in rows}
        ev = lambda e: len({r["card_id"] for r in rows if r["event"] == e})
        g = ev("generated") or 1
        out[fam] = {"generated": g,
                    "investigate_rate": round(ev("analyst_brief") / g, 3),
                    "blotter_rate": round(ev("blotter_open") / g, 3)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/workstation.db")
    ap.add_argument("--manual", type=float, required=True,
                    help="0..1 from the signed review (useful/10)")
    ap.add_argument("--release", required=True)
    ap.add_argument("--workspace", default="default")
    a = ap.parse_args()
    from server.db import Db
    db = Db(ROOT / a.db)
    prompt_v = (ROOT / "prompts" / "current").resolve().name
    c = components(db, a.manual)
    rec = {"ts": datetime.now(timezone.utc).isoformat(),
           "release": a.release, "prompt_version": prompt_v,
           "workspace": a.workspace, "components": c,
           "usefulness_score": score(c),
           "decision_metrics": db.decision_metrics(),
           "by_signal_family": by_family(db, a.manual)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.release}.json").write_text(json.dumps(rec, indent=2))
    print(json.dumps({k: rec[k] for k in
                      ("release", "prompt_version", "usefulness_score")},
                     indent=1))
    # ---- anti-overfitting gate vs previous release -----------------------
    prev = sorted(p for p in OUT.glob("*.json")
                  if p.stem != a.release)
    if prev:
        last = json.loads(prev[-1].read_text())
        act_up = (c["blotter_rate"]
                  > last["components"]["blotter_rate"] + 1e-9)
        use_down = rec["usefulness_score"] < last["usefulness_score"] - 1e-9
        if act_up and use_down:
            print(f"ANTI-OVERFIT GATE FAILED vs {last['release']}: action "
                  "rate rose while usefulness fell — surfaces are creating "
                  "conviction, not insight.")
            return 1
        print(f"anti-overfit gate vs {last['release']}: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
