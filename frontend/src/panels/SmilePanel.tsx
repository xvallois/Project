/** SMIL v2 — smile with the historical p10-p90 cone (design v1.1 §2.4). */
import { useMemo } from "react";
import { NODES, type Node } from "../core/types";
import { percentile } from "../mock/market";
import { usePanelContext, type PanelParams } from "../shell/DockHost";
import { useMarket } from "../state/stores";

const X: Record<Node, number> = { "10P": 60, "25P": 165, ATM: 270,
  "25C": 375, "10C": 480 };

function nodeVol(p: { atm: number; rr25: number; bf25: number }, n: Node) {
  const m = n.startsWith("10") ? 1.85 : 1;
  const b = n.startsWith("10") ? 3.2 : 1;
  if (n === "ATM") return p.atm;
  const sign = n.endsWith("C") ? 1 : -1;
  return p.atm + p.bf25 * b + (sign * p.rr25 * m) / 2;
}
const q = (sorted: number[], f: number) =>
  sorted[Math.min(sorted.length - 1, Math.floor(f * sorted.length))];

export function SmilePanel({ params }: { params: PanelParams }) {
  const { pair, tenor } = usePanelContext(params);
  const history = useMarket((s) => s.history);

  const data = useMemo(() => {
    const s = history[pair][tenor];
    const cur = s.at(-1)!;
    return NODES.map((n) => {
      const hist = s.slice(0, -1).map((x) => nodeVol(x, n))
        .sort((a, b) => a - b);
      const v = nodeVol(cur, n);
      return { n, v, p10: q(hist, 0.1), p90: q(hist, 0.9),
        pct: percentile(hist, v) };
    });
  }, [history, pair, tenor]);

  const vals = data.flatMap((d) => [d.v, d.p10, d.p90]);
  const lo = Math.min(...vals) - 0.2, hi = Math.max(...vals) + 0.2;
  const Y = (v: number) => 150 - ((v - lo) / (hi - lo)) * 125;
  const path = (pts: [number, number][]) =>
    pts.map((p, i) => `${i ? "L" : "M"}${p[0]} ${p[1]}`).join(" ");
  const stretched = data.filter((d) => d.pct >= 95 || d.pct <= 5);

  return (
    <div style={{ height: "100%", position: "relative" }}>
      <svg viewBox="0 0 540 170" width="100%" height="100%"
        preserveAspectRatio="none">
        <path d={path(data.map((d) => [X[d.n], Y(d.p90)])) + " " +
          path([...data].reverse().map((d) => [X[d.n], Y(d.p10)]))
            .replace("M", "L") + " Z"}
          fill="#16202e" opacity="0.85" />
        <path d={path(data.map((d) => [X[d.n], Y(d.v)]))} fill="none"
          stroke="#74a6d4" strokeWidth="1.8" />
        {data.map((d) => (
          <g key={d.n}>
            <circle cx={X[d.n]} cy={Y(d.v)} r="2.8" fill="#74a6d4" />
            {(d.pct >= 95 || d.pct <= 5) &&
              <circle cx={X[d.n]} cy={Y(d.v)} r="5.5" fill="none"
                stroke="var(--amber)" strokeWidth="1.2" />}
            <text x={X[d.n] - 10} y={164} fontFamily="monospace"
              fontSize="9" fill="#8B95A6">{d.n}</text>
          </g>
        ))}
        <text x="8" y={Y(hi - 0.2) + 4} fontFamily="monospace" fontSize="9"
          fill="#8B95A6">{(hi - 0.2).toFixed(1)}</text>
        <text x="8" y={Y(lo + 0.2)} fontFamily="monospace" fontSize="9"
          fill="#8B95A6">{(lo + 0.2).toFixed(1)}</text>
      </svg>
      <span style={{ position: "absolute", left: 10, bottom: 4 }}
        className="cev">
        {pair} {tenor} · cone p10–p90 (1y) · today ●
        {stretched.length > 0 && <> · <b style={{ color: "var(--amber)" }}>
          {stretched.map((d) => `${d.n} p${Math.round(d.pct)}`).join(" · ")}
        </b></>}
      </span>
    </div>
  );
}
