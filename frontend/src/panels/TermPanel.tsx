/** TERM — term-structure evolution (Phase 3). Decision: "is the curve
 *  repricing at a point (kink → calendar trade) or in level (regime)?" */
import { useEffect, useState } from "react";
import { getTerm } from "../api/client";
import { postSurfaceOpen } from "../api/client";
import { usePanelContext, type PanelParams } from "../shell/DockHost";
import { useEngine } from "../state/engine";

const STYLES: Record<string, { c: string; d?: string }> = {
  today: { c: "#74a6d4" }, t1: { c: "#8B95A6", d: "4 3" },
  t5: { c: "#5b6575", d: "2 4" } };

export function TermPanel({ params }: { params: PanelParams }) {
  const { pair } = usePanelContext(params);
  const health = useEngine((s) => s.health);
  const [d, setD] = useState<Record<string,
    { tenor: string; atm: number }[]>>({});
  useEffect(() => { postSurfaceOpen("term", pair); }, [pair]);
  useEffect(() => { getTerm(pair).then((t) => setD(t.series))
    .catch(() => setD({})); }, [pair, health.last_cycle]);
  const today = d.today ?? [];
  if (!today.length) return <div className="phase-note">no history</div>;
  const all = Object.values(d).flat().map((p) => p.atm);
  const lo = Math.min(...all) - 0.15, hi = Math.max(...all) + 0.15;
  const X = (i: number) => 40 + (i * 490) / Math.max(1, today.length - 1);
  const Y = (v: number) => 145 - ((v - lo) / (hi - lo)) * 120;
  return (
    <div style={{ height: "100%", position: "relative" }}>
      <svg viewBox="0 0 540 170" width="100%" height="100%"
        preserveAspectRatio="none">
        {Object.entries(d).map(([k, pts]) => (
          <path key={k} fill="none" stroke={STYLES[k].c}
            strokeDasharray={STYLES[k].d} strokeWidth={k === "today" ? 1.8 : 1}
            d={pts.map((p, i) => `${i ? "L" : "M"}${X(i)} ${Y(p.atm)}`)
              .join(" ")} />))}
        {today.map((p, i) => (<g key={p.tenor}>
          <circle cx={X(i)} cy={Y(p.atm)} r="2.5" fill="#74a6d4" />
          <text x={X(i) - 8} y={162} fontFamily="monospace" fontSize="9"
            fill="#8B95A6">{p.tenor}</text></g>))}
      </svg>
      <span style={{ position: "absolute", left: 10, bottom: 4 }}
        className="cev"><span className="chip c-det">ENGINE</span>
        {pair} ATM curve · ─ today · ┄ T-1 · ⋯ T-5 — parallel shift =
        regime, point break = calendar</span>
    </div>
  );
}
