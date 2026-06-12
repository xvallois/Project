# ADR 0005 — Feed lifecycle rules
**Status** accepted (Phase 0, server-authoritative Phase 1) · **Decision**
dedup by `type|pair|structure`; 12h dismissal cooldown OVERRIDDEN by band
escalation; acted/watching sticky; disappearance debounced (2 consecutive
missing cycles) then `invalidated`; detector hysteresis (enter p95/z1.5,
hold p90/z1.2); broad drifts cluster to ONE surface card; midrank
percentile (ties are not extremes); dq flags can never be ACTIONABLE.
**Why** each rule earned by a measured failure (churn 88%→76% on mock).
