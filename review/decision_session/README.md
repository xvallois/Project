# Decision sessions — decisions are the regression unit

`scripts/record_session.py` exports a trader session from the ledger db:
workspace, opportunities_seen, investigations_opened, surfaces_opened,
blotter_actions, outcome_stub, plus the packets/packs needed to replay.

`scripts/replay_session.py` answers "would the same decisions still
happen?" against CURRENT code, deterministically:
  1. every card the trader saw still passes the provenance verifier
  2. banding on the stored confidence inputs is byte-identical
  3. the lifecycle replayed over the stored event order reaches the
     same terminal statuses
  4. every investigation's stored pack re-runs through the live
     prompts/gate within its recorded expectation (status, abstention)

Honest boundary: this replays the DECISION LOGIC. Market re-detection
replay (same snapshots → same cards) requires the engine's snapshot
ReplayCache and is the planned v4 extension.
