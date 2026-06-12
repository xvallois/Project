# volwatch workstation — Phase 0

Frontend shell + docking + command grammar + deterministic opportunity
feed. Mock data, zero AI (by locked sequencing decision). 25 contract
tests green; 100KB gzipped.

## Run
    npm install
    npm run dev        # http://localhost:5173
    npm test           # contract tests (grammar, budget, feed lifecycle)
    npm run build

## Tour (keyboard only)
1. `Ctrl+K` → type `SMIL EURJPY 3M` → Enter (grammar is order-flexible)
2. In OPPS: `j/k` to move, `W` watch, `B` → blotter (thesis frozen),
   `X` → dismissal picklist (1-7), `G` fan out to SMIL
3. `L` in a focused VHEAT cycles LEVEL → ΔT-1 → %ILE lenses
4. `Ctrl+1..5` switch modes (MORN/ECB/NFP/G10RV/RISK) — layouts
   auto-snapshot; `Ctrl+S` saves explicitly
5. Click a panel's link chip to cycle its group (– A B C D);
   `Ctrl+K` → `USDJPY 1W` repoints group A and every A-linked panel follows
6. Status bar: analyst energy bar (hard budget engine live underneath),
   feed freshness, mock-data disclosure.

## What is deliberately absent (sequencing)
- Claude / Tier-2 synthesis (Phase 2 — after deterministic feed is stable)
- FastAPI sidecar + SQLite (Phase 1/4; localStorage stands in,
  store APIs already shaped like the future REST)
- Tauri shell + multi-window (Phase 5)
- Tailwind/shadcn (Phase 1, mapped onto the existing token system)
