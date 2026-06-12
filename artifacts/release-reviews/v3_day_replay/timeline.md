# v3 day replay — the full story

Workspace: G10 RV · 145 events · accelerated clock (3s snaps)

## What this day also found (replay as regression)
Run 1 FAILED replay → persistence was tracked but never fed
banding (bands frozen at detect-time). Fixed via band_fn in the
lifecycle merge. Run 2 STILL failed on percentile cards only →
np.float64 z-scores made the band score saturate at 1 (numpy
bool `+` is logical OR): every percentile card had been silently
SPECULATIVE since Phase 1. Fixed with boundary coercion + typed
regression test. Run 3: PASS — same decisions hold.

## Timeline
- `07:40:19` engine surfaced        triangle_correlation|EURGBP|3M triangle vs EUR 
- `07:40:19` engine surfaced        triangle_correlation|EURJPY|3M triangle vs EUR 
- `07:40:19` engine surfaced        term_structure_kink|USDJPY|ON/1W/2W calendar f 
- `07:40:19` engine surfaced        term_structure_kink|EURGBP|2W/1M/2M calendar f 
- `07:40:19` engine surfaced        term_structure_kink|EURGBP|3M/6M/9M calendar f 
- `07:40:19` engine surfaced        vol_risk_premium|AUDUSD|6M ATM (delta-hedged) 
- `07:40:19` engine surfaced        term_structure_kink|EURGBP|ON/1W/2W calendar f 
- `07:40:19` engine surfaced        vol_risk_premium|NZDUSD|3M ATM (delta-hedged) 
- `07:40:19` engine surfaced        ATM_PCTILE|AUDUSD|* 
- `07:40:19` engine surfaced        ATM_PCTILE|EURGBP|* 
- `07:40:19` engine surfaced        ATM_PCTILE|EURJPY|* 
- `07:40:19` engine surfaced        ATM_PCTILE|EURUSD|* 
- `07:40:19` engine surfaced        SKEW_PCTILE|NZDUSD|1M 
- `07:40:19` engine surfaced        ATM_PCTILE|USDJPY|* 
- `07:40:19` engine surfaced        SKEW_PCTILE|USDJPY|ON 
- `07:40:24` engine surfaced        vol_risk_premium|USDJPY|6M ATM (delta-hedged) 
- `07:40:24` engine surfaced        vol_risk_premium|USDJPY|3M ATM (delta-hedged) 
- `07:40:24` engine surfaced        term_structure_kink|GBPUSD|2M/3M/6M calendar f 
- `07:40:24` engine surfaced        term_structure_kink|GBPUSD|1M/2M/3M calendar f 
- `07:40:24` engine surfaced        vol_risk_premium|EURJPY|6M ATM (delta-hedged) 
- `07:40:24` engine surfaced        skew_richcheap|USDCAD|3M 25d risk reversal 
- `07:40:24` engine surfaced        SKEW_PCTILE|AUDUSD|9M 
- `07:40:24` engine surfaced        ATM_PCTILE|GBPUSD|3M 
- `07:40:24` engine surfaced        SKEW_PCTILE|GBPUSD|3M 
- `07:40:24` engine surfaced        SKEW_PCTILE|NZDUSD|ON 
- `07:40:24` engine surfaced        SKEW_PCTILE|USDCAD|3M 
- `07:40:24` engine surfaced        ATM_PCTILE|USDCAD|ON 
- `07:40:24` engine surfaced        SKEW_PCTILE|USDJPY|3M 
- `07:40:34` engine surfaced        vol_risk_premium|EURGBP|6M ATM (delta-hedged) 
- `07:40:34` engine surfaced        vol_risk_premium|EURUSD|3M ATM (delta-hedged) 
- `07:40:34` engine surfaced        term_structure_kink|NZDUSD|1W/2W/1M calendar f 
- `07:40:34` engine surfaced        skew_richcheap|EURGBP|1M 25d risk reversal 
- `07:40:34` engine surfaced        vol_risk_premium|GBPUSD|6M ATM (delta-hedged) 
- `07:40:34` engine surfaced        term_structure_kink|NZDUSD|2W/1M/2M calendar f 
- `07:40:34` engine surfaced        SKEW_PCTILE|EURGBP|1M 
- `07:40:34` engine surfaced        SKEW_PCTILE|EURGBP|ON 
- `07:40:34` engine surfaced        SKEW_PCTILE|EURUSD|2M 
- `07:40:34` engine surfaced        SKEW_PCTILE|NZDUSD|9M 
- `07:40:34` engine surfaced        SKEW_PCTILE|USDCAD|2W 
- `07:40:34` engine surfaced        SKEW_PCTILE|USDJPY|1Y 
- `07:40:34` invalidated (no action) term_structure_kink|USDJPY|ON/1W/2W calendar f 
- `07:40:34` invalidated (no action) term_structure_kink|EURGBP|2W/1M/2M calendar f 
- `07:40:34` invalidated (no action) term_structure_kink|EURGBP|3M/6M/9M calendar f 
- `07:40:34` invalidated (no action) vol_risk_premium|AUDUSD|6M ATM (delta-hedged) 
- `07:40:34` invalidated (no action) term_structure_kink|EURGBP|ON/1W/2W calendar f 
- `07:40:34` invalidated (no action) vol_risk_premium|NZDUSD|3M ATM (delta-hedged) 
- `07:40:34` invalidated (no action) SKEW_PCTILE|NZDUSD|1M 
- `07:40:45` engine surfaced        vol_risk_premium|EURGBP|3M ATM (delta-hedged) 
- `07:40:45` engine surfaced        term_structure_kink|USDJPY|2M/3M/6M calendar f 
- `07:40:45` engine surfaced        vol_risk_premium|AUDUSD|3M ATM (delta-hedged) 
- `07:40:45` engine surfaced        term_structure_kink|AUDUSD|3M/6M/9M calendar f 
- `07:40:45` engine surfaced        SKEW_PCTILE|EURGBP|* 
- `07:40:45` engine surfaced        SKEW_PCTILE|EURJPY|2M 
- `07:40:45` engine surfaced        SKEW_PCTILE|EURUSD|ON 
- `07:40:45` engine surfaced        SKEW_PCTILE|GBPUSD|1M 
- `07:40:45` engine surfaced        SKEW_PCTILE|GBPUSD|1W 

## Close of day
- generated 61 · acted 1 · ignored 27 · investigate_rate 0.033
- investigation_conversion 0.5 · abstain_rate 0.4 (healthy band 0.15-0.40)
- median investigate latency 27.4s · decision latency 27.4s
- replay: PASS · usefulness v3-rc1 recorded (anti-overfit baseline established)
- evidence: investigations/ (incl. an abstention), decisions.json, invalidations.json, postmortem.json, metrics_dashboard.json, surfaces.json
