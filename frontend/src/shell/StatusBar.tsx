import { budgetPct, useBudget, useFeed, useMarket } from "../state/stores";
import { remaining, totalFor } from "../core/budget/engine";

export function StatusBar() {
  const asof = useMarket((s) => s.asof);
  const feed = useFeed((s) => s.feed);
  const budget = useBudget((s) => s.state);
  const live = Object.values(feed.cards).filter((c) =>
    ["new", "seen", "watching"].includes(c.status)).length;
  const ageS = Math.max(0,
    Math.round((Date.now() - Date.parse(asof)) / 1000));
  return (
    <div className="status">
      <span className="live">● FEED LIVE</span>
      <span>snap {ageS}s</span>
      <span>{live} open opportunities</span>
      <span className="energy" title={
        `Analyst budget: ${remaining(budget)}/${totalFor(budget)} units. ` +
        "Triage 1u · analysis 3u · deep 10u. Triage reserve 12u. " +
        "Resets daily, 20% carryover."}>
        analyst
        <span className="ebar"><i style={{ width: `${budgetPct(budget)}%` }} /></span>
        <span>{remaining(budget)}u</span>
      </span>
      <span className="sp" />
      <span>Ctrl+K command · Ctrl+1..5 modes · Ctrl+S save layout</span>
      <span className="mut">v0.1 phase-0 · mock data</span>
    </div>
  );
}
