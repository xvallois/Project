#!/usr/bin/env python3
"""Export a decision session from the ledger db -> review/decision_session/."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/workstation.db")
    ap.add_argument("--name", required=True)
    ap.add_argument("--workspace", default="default")
    ap.add_argument("--packet", default=None,
                    help="path to a saved /api/packet json")
    a = ap.parse_args()
    from server.db import Db
    db = Db(ROOT / a.db)
    ev = [dict(r) for r in db._con.execute(
        "SELECT ts, card_id, event, payload FROM events ORDER BY ts")]
    cards = {c["id"]: c for c in db.all_cards()}
    briefs = {cid: db.briefs_for(cid)
              for cid in {e["card_id"] for e in ev
                          if e["event"] == "analyst_brief" and e["card_id"]}}
    session = {
        "name": a.name, "workspace": a.workspace,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "opportunities_seen": [e for e in ev if e["event"] in
                               ("generated", "seen", "watching")],
        "investigations_opened": [e for e in ev if e["event"] in
                                  ("analyst_brief", "analyst_abstain")],
        "surfaces_opened": [e for e in ev if e["event"] == "surface_open"],
        "blotter_actions": [e for e in ev if e["event"].startswith(
            "blotter_")] + db.blotter_all(),
        "outcome_stub": db.decision_metrics(),
        "cards": cards,
        "briefs": {k: v for k, v in briefs.items()},
        "packet": json.loads(Path(a.packet).read_text())
        if a.packet else None,
        "event_log": ev,
    }
    out = ROOT / "review" / "decision_session" / f"{a.name}.json"
    out.write_text(json.dumps(session, indent=1))
    print(f"recorded {out} · {len(ev)} events · {len(cards)} cards · "
          f"{sum(len(v) for v in briefs.values())} briefs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
