#!/usr/bin/env python3
"""Replay a decision session against CURRENT code (the highest-value
regression). Exit 1 if any decision precondition no longer holds."""
from __future__ import annotations
import json, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(path: str) -> int:
    from server.analyst.engine import abstain_or_brief
    from server.analyst.provider import StubProvider
    from server.detectors import band_for
    from server.db import Db
    from server.provenance import ProvenanceVerifier
    s = json.loads(Path(path).read_text())
    fails = []

    # 1. provenance still holds for every card the trader saw
    if s.get("packet"):
        keys = {f"ledger:card({cid})" for cid in s["cards"]}
        keys |= {f"ledger:funnel({cid.split('|')[0]})"
                 for cid in s["cards"]}
        fields = {(c["pair"], t, f) for c in s["cards"].values()
                  for t in (c["tenors"] or ["3M"])
                  for f in ("atm", "rr25", "bf25")}
        v = ProvenanceVerifier(s["packet"], fields, keys)
        for cid, c in s["cards"].items():
            bad = v.verify_card(c)
            if bad:
                fails.append(f"provenance drift {cid}: {bad[0].reason}")

    # 2. banding identical on stored confidence inputs
    for cid, c in s["cards"].items():
        cf = c["confidence"]
        prior = cf.get("backtestPrior")
        b = band_for(cf["absZ"], cf["persistedCycles"],
                     cf["dataQualityOk"], cf["modelsAgree"],
                     bool(prior and prior.get("hitRate", 0) >= 0.55
                          and prior.get("n", 0) >= 20))
        if b != c["band"]:
            fails.append(f"band drift {cid}: {c['band']} -> {b}")

    # 3. lifecycle replay over the stored event order
    with tempfile.TemporaryDirectory() as t:
        db = Db(Path(t) / "r.db")
        gen_order = [e["card_id"] for e in s["event_log"]
                     if e["event"] == "generated"]
        db.apply_cycle([s["cards"][cid] | {"status": "new",
                                           "invalidation": None}
                        for cid in gen_order if cid in s["cards"]])
        for e in s["event_log"]:
            if e["event"] in ("seen", "watching", "acted", "dismissed") \
                    and e["card_id"] in s["cards"]:
                db.transition(e["card_id"], e["event"],
                              json.loads(e["payload"]) or None)
        replayed = {c["id"]: c["status"] for c in db.all_cards()}
        for cid, c in s["cards"].items():
            want = c["status"] if c["status"] != "invalidated" else None
            if want and cid in replayed and replayed[cid] != want:
                fails.append(f"lifecycle drift {cid}: "
                             f"{want} -> {replayed[cid]}")

    # 4. investigations re-run through live prompts/gate
    rerun_ok = 0
    for cid, blist in s.get("briefs", {}).items():
        for b in blist:
            pack = {"card_id": cid, "headline": b["card_id"],
                    "pair": s["cards"][cid]["pair"],
                    "band": s["cards"][cid]["band"],
                    "findings": s["cards"][cid]["findings"],
                    "invalidation":
                    s["cards"][cid]["invalidation_criteria"],
                    "workspace_brief": s["workspace"],
                    "evidence": [{"eid": e["eid"], "label": e["label"],
                                  "value": e["value"],
                                  "provenance": e["provenance"],
                                  "tag": "supporting"}
                                 for e in b["evidence"]]}
            out = abstain_or_brief(pack, b["depth"], StubProvider())
            ok = out.get("abstained") or \
                out.get("brief") and out["brief"].status in ("ok",
                                                             "degraded")
            if not ok:
                fails.append(f"investigation drift {cid}")
            else:
                rerun_ok += 1

    print(f"replay {s['name']}: {len(s['cards'])} cards · "
          f"{rerun_ok} investigations re-run · "
          f"{'PASS — same decisions hold' if not fails else 'FAIL'}")
    for f in fails[:8]:
        print("  ", f)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
