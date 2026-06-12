# Bloomberg / BQL bring-up smoke checklist (manual, desk-only)

Manual artifact — no Bloomberg dependency exists in CI; CI exercises the
identical pipeline via the mock provider. Run this once per desk host
before trusting `VW_PROVIDER=bbg|bql`. Derived from the engine's
bring-up runbook (stage 9); budget ~half a day including entitlements.

## 0. Prerequisites
- [ ] Terminal running and logged in on the host (`bbg`), or running
      inside BQuant (`bql` — it does NOT work elsewhere).
- [ ] `pip install blpapi --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/`
      (bbg) or the `bql` package available (BQuant/SAPI license).
- [ ] Mock baseline green on this host first:
      `./scripts/setup.sh && python3 -m pytest engine/tests server/tests -q`.

## 1. Ticker templates (no Terminal needed)
- [ ] Eyeball `engine/config/bloomberg.yaml` templates against the
      terminal (`EURUSDV1M BGN Curncy <GO>`). If the desk prices off
      CMPN or another source, edit the templates ONCE — every ticker in
      the system derives from them.
- [ ] Verify the rate (OIS) tickers explicitly. The shipped
      GBP/JPY/CHF/CAD/AUD/NZD variants are best-effort and MUST be
      checked per setup; until then the engine logs a warning and uses
      the default rate (visible, not silent).

## 2. First live snap through the sidecar
    VW_PROVIDER=bbg VW_DATA=./bringup-data uvicorn server.app:app --port 8787
- [ ] Sidecar boots; `/api/health` shows `provider: bbg`, a fresh
      `last_snap`, and per-pair `engine_health` populated.
- [ ] Expected on snap 1: validation flags (no jump baseline yet);
      they should quiet down by the second snap.

Common first failures, in order of likelihood:
| Symptom | Cause | Fix |
|---|---|---|
| boot fails at provider import | blpapi missing / Terminal API port | install blpapi; Terminal up; default port 8194; firewall |
| vols missing | BGN entitlement | try `CMPN` in templates, or market-data team |
| rates missing | OIS ticker variants | verify each on terminal, edit `bloomberg.yaml` |

## 3. Data sanity (check the data, not the code)
After ~12 snaps (one hour at `VW_SNAP_S=300`):
- [ ] ATMs within a tick of the terminal at 1M for 3 pairs.
- [ ] RR signs right (USDJPY 25d RR negative).
- [ ] `status=0` on current quotes; no stuck validation flags.
- [ ] `/api/feed`: signals SILENT or thin is CORRECT — z-scores refuse
      to fire with <20 days of history, by design. The health payload is
      what matters on day one.

## 4. BQL variant
Same checks, `VW_PROVIDER=bql`, run inside BQuant only. One bulk request
per snap server-side; on missing `bql` package the provider fails loudly
at boot — that is the intended behavior, not a smoke failure.

## 5. Accumulation gate
- [ ] 60+ business days of history before trusting any z-scored signal
      live; record the go-live date in the decision ledger.
- [ ] Record one real desk session (`scripts/record_session.py`) and
      commit it under `review/decision_session/` as the bbg acceptance
      replay for future releases.
