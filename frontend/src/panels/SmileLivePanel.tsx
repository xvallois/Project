/** SMIL over the live store (Phase 3). Decision: "is the smile itself
 *  dislocated or just ATM — and has it actually moved vs a week ago?"
 *  Cone = own 1y p10-p90; dashed overlay = the smile 5 sessions back. */
import { useEffect, useState } from "react";
import { getSmile, type SmileNode } from "../api/client";
import { postSurfaceOpen } from "../api/client";
import { usePanelContext, type PanelParams } from "../shell/DockHost";
import { useEngine } from "../state/engine";

const X: Record<string, number> = { "10P": 60, "25P": 165, ATM: 270,
  "25C": 375, "10C": 480 };

export function SmileLivePanel({ params }: { params: PanelParams }) {
  const { pair, tenor } = usePanelContext(params);
  const health = useEngine((s) => s.health);
  const [d, setD] = useState<{ nodes: SmileNode[]; asof?: string;
    t5_date?: string; provenance?: string }>({ nodes: [] });
  useEffect(() => { postSurfaceOpen("smile", pair, tenor); }, [pair,tenor]);
  useEffect(() => { getSmile(pair, tenor).then(setD)
    .catch(() => setD({ nodes: [] })); }, [pair, tenor, health.last_cycle]);
  if (!d.nodes.length) return <div className="phase-note">
    no store history yet for {pair} {tenor}</div>;
  const vals = d.nodes.flatMap((n) => [n.vol, n.p10, n.p90, n.t5]);
  const lo = Math.min(...vals) - 0.2, hi = Math.max(...vals) + 0.2;
  const Y = (v: number) => 150 - ((v - lo) / (hi - lo)) * 125;
  const path = (pts: [number, number][]) =>
    pts.map((p, i) => `${i ? "L" : "M"}${p[0]} ${p[1]}`).join(" ");
  const stretched = d.nodes.filter((n) => n.pct >= 95 || n.pct <= 5);
  return (
    <div style={{ height: "100%", position: "relative" }}
      title={d.provenance}>
      <svg viewBox="0 0 540 170" width="100%" height="100%"
        preserveAspectRatio="none">
        <path d={path(d.nodes.map((n) => [X[n.node], Y(n.p90)])) + " " +
          path([...d.nodes].reverse().map((n) => [X[n.node], Y(n.p10)]))
            .replace("M", "L") + " Z"} fill="#16202e" opacity="0.85" />
        <path d={path(d.nodes.map((n) => [X[n.node], Y(n.t5)]))}
          fill="none" stroke="#8B95A6" strokeWidth="1"
          strokeDasharray="4 3" />
        <path d={path(d.nodes.map((n) => [X[n.node], Y(n.vol)]))}
          fill="none" stroke="#74a6d4" strokeWidth="1.8" />
        {d.nodes.map((n) => (<g key={n.node}>
          <circle cx={X[n.node]} cy={Y(n.vol)} r="2.8" fill="#74a6d4" />
          {(n.pct >= 95 || n.pct <= 5) &&
            <circle cx={X[n.node]} cy={Y(n.vol)} r="5.5" fill="none"
              stroke="var(--amber)" strokeWidth="1.2" />}
          <text x={X[n.node] - 10} y={164} fontFamily="monospace"
            fontSize="9" fill="#8B95A6">{n.node}</text></g>))}
      </svg>
      <span style={{ position: "absolute", left: 10, bottom: 4 }}
        className="cev">
        <span className="chip c-det">ENGINE</span>
        {pair} {tenor} · ─ today ({d.asof}) · ┄ {d.t5_date} · cone p10-p90
        {stretched.length > 0 && <> · <b style={{ color: "var(--amber)" }}>
          {stretched.map((n) => `${n.node} p${Math.round(n.pct)}`)
            .join(" · ")}</b></>}
      </span>
    </div>
  );
}
