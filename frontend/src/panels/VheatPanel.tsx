/** VHEAT — primary surface view (design v1.1 §2.1). Three lenses,
 *  `L` cycles when the panel is focused. %ILE is the default: the
 *  rich/cheap map at a glance. 3D intentionally absent until Phase 3+.
 */
import { useMemo, useState } from "react";
import { NODES, TENORS, type Node, type Tenor } from "../core/types";
import { percentile } from "../mock/market";
import { usePanelContext, type PanelParams } from "../shell/DockHost";
import { useMarket, useWorkspaces } from "../state/stores";

type Lens = "LEVEL" | "ΔT-1" | "%ILE";
const LENSES: Lens[] = ["LEVEL", "ΔT-1", "%ILE"];

/** Smile reconstruction from the quote vector (mirrors the engine). */
function nodeVol(p: { atm: number; rr25: number; bf25: number },
                 node: Node): number {
  switch (node) {
    case "ATM": return p.atm;
    case "25P": return p.atm + p.bf25 - p.rr25 / 2;
    case "25C": return p.atm + p.bf25 + p.rr25 / 2;
    case "10P": return p.atm + p.bf25 * 3.2 - (p.rr25 * 1.85) / 2;
    case "10C": return p.atm + p.bf25 * 3.2 + (p.rr25 * 1.85) / 2;
  }
}

const pctColor = (p: number) => {
  const t = (p - 50) / 50;                       // -1 cheap .. +1 rich
  return t >= 0
    ? `rgb(${17 + 130 * t},${21 + 28 * t},${29 + 48 * t})`
    : `rgb(${17 + 14 * -t},${21 + 90 * -t},${29 + 63 * -t})`;
};
const dColor = (d: number) => pctColor(50 + Math.max(-1, Math.min(1, d / 0.4)) * 50);

export function VheatPanel({ params }: { params: PanelParams }) {
  const { pair } = usePanelContext(params);
  const history = useMarket((s) => s.history);
  const ws = useWorkspaces();
  const [lens, setLens] = useState<Lens>("%ILE");

  const grid = useMemo(() => TENORS.map((tenor) => {
    const s = history[pair][tenor];
    const cur = s.at(-1)!; const prev = s.at(-2)!;
    return NODES.map((node) => {
      const v = nodeVol(cur, node);
      const hist = s.slice(0, -1).map((x) => nodeVol(x, node));
      return { tenor, node, vol: v, d1: v - nodeVol(prev, node),
        pct: percentile(hist, v) };
    });
  }), [history, pair]);

  return (
    <div style={{ height: "100%" }} tabIndex={0}
      onKeyDown={(e) => {
        if (e.key.toLowerCase() === "l")
          setLens(LENSES[(LENSES.indexOf(lens) + 1) % LENSES.length]);
      }}>
      <div className="fchips">
        <span className="ctype">{pair}</span>
        <div className="lens">
          {LENSES.map((l) => (
            <button key={l} className={`tog ${l === lens ? "act" : ""}`}
              onClick={() => setLens(l)}>{l}</button>
          ))}
          <span className="tog" title="3D mode ships in Phase 3"
            style={{ opacity: 0.4 }}>3D</span>
        </div>
      </div>
      <div className="pb">
        <div className="hwrap"
          style={{ gridTemplateRows: `18px repeat(${TENORS.length},1fr)`,
            inset: "40px 10px 22px 10px", position: "absolute" }}>
          <div className="hlabel" />
          {NODES.map((n) => <div key={n} className="hlabel">{n}</div>)}
          {grid.map((row) => (
            <RowCells key={row[0].tenor} row={row} lens={lens}
              onPick={(tenor) => ws.dockApi?.openPanel(
                { kind: "SMIL", pair, tenor })} />
          ))}
        </div>
        <div className="legend">
          {lens === "%ILE" && <><span>cheap p0</span><div className="lbar" />
            <span>rich p100 · vs own 1y</span></>}
          {lens === "ΔT-1" && <><span>−0.4vp</span><div className="lbar" />
            <span>+0.4vp vs yesterday</span></>}
          {lens === "LEVEL" && <span>vol points</span>}
          <span style={{ marginLeft: 12 }}>L cycles lens · click cell → SMIL</span>
        </div>
      </div>
    </div>
  );
}

function RowCells({ row, lens, onPick }: {
  row: { tenor: Tenor; node: Node; vol: number; d1: number; pct: number }[];
  lens: Lens; onPick: (t: Tenor) => void;
}) {
  return (
    <>
      <div className="hlabel">{row[0].tenor}</div>
      {row.map((c) => {
        const [bg, txt] = lens === "LEVEL"
          ? [pctColor(c.pct * 0.4 + 30), c.vol.toFixed(1)]
          : lens === "ΔT-1"
            ? [dColor(c.d1), (c.d1 >= 0 ? "+" : "") + c.d1.toFixed(2)]
            : [pctColor(c.pct), String(Math.round(c.pct))];
        const hot = lens === "%ILE" && (c.pct >= 95 || c.pct <= 5);
        return (
          <button key={c.node} className="cell"
            style={{ background: bg,
              outline: hot ? "1.5px solid var(--amber)" : undefined }}
            title={`${row[0].tenor} ${c.node} · ${c.vol.toFixed(2)} vol · p${
              Math.round(c.pct)} · Δ${c.d1.toFixed(2)}`}
            onClick={() => onPick(c.tenor)}>{txt}</button>
        );
      })}
    </>
  );
}
