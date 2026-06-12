#!/usr/bin/env python3
"""Evaluation harness: frozen packs -> live prompts/provider -> gate ->
structural comparison vs expected_briefs/. Writes metrics/<ts>.json and
metrics/latest.json. Exit 1 on any failure (CI/release gate)."""
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
E = ROOT / "evaluation"


def provider():
    if os.environ.get("EVAL_PROVIDER") == "claude":
        from server.analyst.provider import AnthropicProvider
        return AnthropicProvider()
    from server.analyst.provider import StubProvider
    return StubProvider()


def main() -> int:
    from server.analyst.engine import brief_from_pack, _parse
    from server.analyst.schema import Evidence, Statement, gate_brief
    prov = provider()
    results, failures = [], []

    for f in sorted((E / "evidence_packs").glob("*.json")):
        pack = json.loads(f.read_text())
        exp = json.loads((E / "expected_briefs" / f.name).read_text())
        brief = brief_from_pack(pack, exp.get("depth", "investigate"), prov)
        ok, why = True, []
        if brief is None:
            ok, why = False, ["unparseable"]
        else:
            d = brief.to_dict()
            if d["status"] not in exp["allowed_status"]:
                ok = False; why.append(f"status {d['status']}")
            for sec in exp.get("nonempty_sections", []):
                if not d["sections"].get(sec):
                    ok = False; why.append(f"empty {sec}")
            if len(d["dropped"]) > exp.get("max_dropped", 0):
                ok = False; why.append(f"drops {len(d['dropped'])}")
            if exp.get("must_cite_ledger") and not any(
                    e["provenance"].startswith("ledger:")
                    for st in sum(d["sections"].values(), [])
                    for e in d["evidence"] if e["eid"] in st["cites"]):
                ok = False; why.append("no ledger citation")
        results.append({"case": f.stem, "pass": ok, "why": why,
                        "dropped": len(brief.dropped) if brief else None,
                        "status": brief.status if brief else None})
        if not ok:
            failures.append(f.stem)

    # counterexamples (anti-overfitting set): dramatic/conflicting/
    # repeated/stale packs — abstention is a PASS where expected
    from server.analyst.engine import abstain_or_brief
    for f in sorted((E / "counterexamples").glob("*.json")):
        case = json.loads(f.read_text())
        out = abstain_or_brief(case["pack"], "investigate", prov)
        exp = case["expect"]
        ok, why = True, []
        if out.get("abstained"):
            if not (exp.get("abstain_required") or exp.get("abstain_ok")):
                ok, why = False, ["unexpected abstention"]
        else:
            if exp.get("abstain_required"):
                ok, why = False, ["should have abstained"]
            elif "if_brief" in exp:
                d = out["brief"].to_dict()
                ib = exp["if_brief"]
                if d["status"] not in ib["allowed_status"]:
                    ok = False; why.append(f"status {d['status']}")
                for sec in ib.get("nonempty_sections", []):
                    if not d["sections"].get(sec):
                        ok = False; why.append(f"empty {sec}")
        results.append({"case": f"counter:{f.stem}", "pass": ok,
                        "why": why,
                        "abstained": bool(out.get("abstained"))})
        if not ok:
            failures.append(f.stem)

    # regressions: raw provider outputs that MUST be stopped by the gate
    for f in sorted((E / "regressions").glob("*.json")):
        case = json.loads(f.read_text())
        sections_raw = _parse(json.dumps(case["provider_output"]))
        ev = {e["eid"]: Evidence(e["eid"], e["label"], e["value"],
                                 e["provenance"])
              for e in case["pack"]["evidence"]}
        sections = {k: [Statement(s.get("text", ""), "analyst",
                                  list(s.get("cites", [])))
                        for s in v] for k, v in sections_raw.items()}
        _, dropped, status = gate_brief(sections, ev)
        ok = status == case["expected_status"]
        results.append({"case": f"regression:{f.stem}", "pass": ok,
                        "why": [] if ok else
                        [f"gate said {status}, expected "
                         f"{case['expected_status']}"],
                        "status": status, "dropped": len(dropped)})
        if not ok:
            failures.append(f.stem)

    metrics = {"ts": datetime.now(timezone.utc).isoformat(),
               "provider": prov.name,
               "prompt_version": os.readlink(ROOT / "prompts" / "current")
               if (ROOT / "prompts" / "current").is_symlink() else "v?",
               "cases": len(results),
               "passed": sum(r["pass"] for r in results),
               "abstain_count": sum(1 for r in results
                                    if r.get("abstained")),
               "results": results}
    (E / "metrics" / "latest.json").write_text(json.dumps(metrics, indent=2))
    (E / "metrics" / f"{metrics['ts'][:19].replace(':', '')}.json"
     ).write_text(json.dumps(metrics, indent=2))
    for r in results:
        print(f"  {'PASS' if r['pass'] else 'FAIL'} {r['case']}"
              + (f" — {'; '.join(r['why'])}" if r["why"] else ""))
    print(f"eval: {metrics['passed']}/{metrics['cases']} "
          f"(provider={prov.name}, prompts={metrics['prompt_version']})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
