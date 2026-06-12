# evaluation/ — the long-term moat

Frozen evidence packs + structural expectations, run against the LIVE
prompts/provider seam to catch schema drift, prompt regressions, and
quality regressions BEFORE they reach the desk.

| Dir | Contents |
|---|---|
| `evidence_packs/` | frozen real packs (captured from live runs) — the Analyst's inputs |
| `expected_briefs/` | structural expectations per pack: status, required nonempty sections, max gate drops, must-cite-ledger flags |
| `regressions/` | known-bad provider outputs that MUST be rejected/degraded (fabricated numbers, missing sections) |
| `metrics/` | `run_eval.py` output history — compare across prompt versions before moving `prompts/current` |

Run: `python3 scripts/run_eval.py` (stub provider — structure & gate
behavior). With `ANTHROPIC_API_KEY` + `EVAL_PROVIDER=claude` it
benchmarks the live model: text differs, STRUCTURE must not.
