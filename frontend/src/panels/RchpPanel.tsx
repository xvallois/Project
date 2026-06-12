/** RCHP — rich/cheap decomposition: WHERE does richness live. */
import { useMemo } from "react";
import { percentile } from "../mock/market";
import { usePanelContext, type PanelParams } from "../shell/DockHost";
import { useMarket } from "../state/stores";

export function RchpPanel({ params }: { params: PanelParams }) {
  const { pair, tenor } = usePanelContext(params);
  const history = useMarket((s) => s.history);

  const rows = useMemo(() => {
    const s = history[pair][tenor];
    const cur = s.at(-1)!;
    const past = s.slice(0, -1);
    const mk = (label: string, vals: number[], v: number, fmt = 2) => ({
      label, v, pct: percentile(vals, v), txt: v.toFixed(fmt) });
    return [
      mk("ATM level", past.map((x) => x.atm), cur.atm),
      mk("SKEW rr25", past.map((x) => x.rr25), cur.rr25),
      mk("CONVEX bf25", past.map((x) => x.bf25), cur.bf25),
    ];
  }, [history, pair, tenor]);

  return (
    <div className="rch">
      {rows.map((r) => {
        const dev = r.pct - 50;                    // -50..+50
        const rich = dev > 0;
        return (
          <div key={r.label} className="rrow">
            <span className="lab">{r.label}</span>
            <div className="bar"><span className="mid" />
              <i style={{
                [rich ? "left" : "right"]: "50%",
                width: `${Math.abs(dev)}%`,
                background: rich ? "#a23a4d" : "#2c5a4d",
                opacity: 0.35 + Math.abs(dev) / 80 }} />
            </div>
            <span style={{ color: Math.abs(dev) > 40
              ? (rich ? "#e0a0ac" : "#86c7ab") : "var(--muted)" }}>
              {r.txt} p{Math.round(r.pct)}
            </span>
          </div>
        );
      })}
      <div className="rrow"><span className="lab mut">{pair} {tenor}</span>
        <span className="mut" style={{ fontSize: 9 }}>
          bars = percentile vs own 1y · mid = p50</span><span /></div>
    </div>
  );
}
