# prompts/

Versioned, reviewable, rollbackable — treat a prompt edit like a model
upgrade.

- `vN/` — immutable once a release tag points at it; changes go to vN+1
- `current` — symlink selecting the live version (loader falls back to
  the highest vN/ if symlinks are unavailable, e.g. Windows without
  developer mode)
- CI gate: `scripts/verify_prompts.py` (contract elements present + stub
  investigation through live prompts succeeds)
- Benchmarking: `scripts/run_eval.py` runs the evaluation set against
  `current`; compare `evaluation/metrics/` across versions before
  switching the symlink.
