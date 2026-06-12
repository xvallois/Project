/** HLTH — trust panel: feed freshness, budget, store stats (mocked feed). */
import { remaining, totalFor, TRIAGE_RESERVE } from "../core/budget/engine";
import type { PanelParams } from "../shell/DockHost";
import { useBudget, useFeed, useMarket } from "../state/stores";

export function HlthPanel(_: { params: PanelParams }) {
  const asof = useMarket((s) => s.asof);
  const budget = useBudget((s) => s.state);
  const refusedAt = useBudget((s) => s.refusedAt);
  const feed = useFeed((s) => s.feed);
  const cards = Object.values(feed.cards);
  const cell = (label: string, value: string, warn = false) => (
    <div style={{ background: "var(--panel)", padding: "6px 8px",
      fontSize: 10 }}>
      <span style={{ display: "inline-block", width: 6, height: 6,
        borderRadius: "50%", marginRight: 5,
        background: warn ? "var(--amber)" : "var(--up)" }} />
      {label}
      <b className="num" style={{ display: "block", fontSize: 11 }}>{value}</b>
    </div>
  );
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)",
      gap: 1, background: "var(--line)", height: "100%",
      gridAutoRows: "min-content" }}>
      {cell("FEED", `${Math.round((Date.now() - Date.parse(asof)) / 1000)}s · mock`)}
      {cell("ANALYST BUDGET",
        `${remaining(budget)}/${totalFor(budget)}u · reserve ${TRIAGE_RESERVE}u`,
        remaining(budget) < 25)}
      {cell("BUDGET REFUSALS", refusedAt
        ? new Date(refusedAt).toLocaleTimeString() : "none", !!refusedAt)}
      {cell("CARDS", `${cards.length} total · ${
        cards.filter((c) => c.status === "invalidated").length} invalidated`)}
      {cell("STORE", "localStorage · sidecar Phase 1", true)}
      {cell("ANALYST", "deterministic only · Claude Phase 2", true)}
      {cell("WINDOWS", "single · Tauri multi-window Phase 5", true)}
      {cell("SCHEMA", "workspaces v1 · blotter v1")}
    </div>
  );
}
