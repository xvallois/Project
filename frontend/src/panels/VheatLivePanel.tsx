/** VHEAT over the live store (Phase 3). Decision: "where is rich/cheap,
 *  and is an opportunity already open there?" Cells with live cards get
 *  the amber ring; clicking one selects the card in OPPS and fans out
 *  the smile — the heatmap is a router into the flow, not a picture. */
import { useEffect, useState } from "react";
import { getHeat, type HeatRow } from "../api/client";
import { usePanelContext, type PanelParams } from "../shell/DockHost";
import { useEngine } from "../state/engine";
import { useUi, useWorkspaces } from "../state/stores";

type Lens = "LEVEL" | "ΔT-1" | "%ILE";
const LENSES: Lens[] = ["LEVEL", "ΔT-1", "%ILE"];
const pctColor = (p: number) => { const t = (p - 50) / 50;
  return t >= 0 ? `rgb(${17 + 130 * t},${21 + 28 * t},${29 + 48 * t})`
    : `rgb(${17 + 14 * -t},${21 + 90 * -t},${29 + 63 * -t})`; };

export function VheatLivePanel({ params }: { params: PanelParams }) {
  const { pair } = usePanelContext(params);
  const cards = useEngine((s) => s.cards);
  const health = useEngine((s) => s.health);
  const ws = useWorkspaces();
  const setSelectedCard = useUi((s) => s.setSelectedCard);
  const [rows, setRows] = useState<HeatRow[]>([]);
  const [days, setDays] = useState(0);
  const [lens, setLens] = useState<Lens>("%ILE");
  useEffect(() => { getHeat(pair).then((h) => { setRows(h.rows);
    setDays(h.history_days); }).catch(() => setRows([])); },
    [pair, health.last_cycle]);

  const liveAt = (tenor: string) => cards.find((c) =>
    c.pair === pair && c.tenors.includes(tenor) &&
    ["new", "seen", "watching"].includes(c.status));

  return (
    <div style={{ height: "100%" }} tabIndex={0} onKeyDown={(e) => {
      if (e.key.toLowerCase() === "l")
        setLens(LENSES[(LENSES.indexOf(lens) + 1) % LENSES.length]); }}>
      <div className="fchips">
        <span className="ctype">{pair} · {days}d store ·
          <span className="chip c-det" style={{ marginLeft: 6 }}>ENGINE</span>
        </span>
        <div className="lens">{LENSES.map((l) => (
          <button key={l} className={`tog ${l === lens ? "act" : ""}`}
            onClick={() => setLens(l)}>{l}</button>))}</div>
      </div>
      <div className="pb">
        <div className="hwrap" style={{
          gridTemplateRows: `18px repeat(${rows.length},1fr)`,
          inset: "40px 10px 22px 10px", position: "absolute" }}>
          <div className="hlabel" />
          {["10P", "25P", "ATM", "25C", "10C"].map((n) =>
            <div key={n} className="hlabel">{n}</div>)}
          {rows.map((r) => {
            const card = liveAt(r.tenor);
            return (<RowK key={r.tenor} r={r} lens={lens} hasCard={!!card}
              onPick={() => {
                if (card) { setSelectedCard(card.id);
                  ws.dockApi?.openPanel({ kind: "OPPS" }); }
                ws.dockApi?.openPanel({ kind: "SMIL", pair,
                  tenor: r.tenor as never });
              }} />);
          })}
        </div>
        <div className="legend">
          <span>cheap</span><div className="lbar" /><span>rich · vs {days}d</span>
          <span style={{ marginLeft: 10, color: "var(--amber)" }}>
            ◯ live opportunity — click routes to card + smile</span>
        </div>
      </div>
    </div>
  );
}

function RowK({ r, lens, hasCard, onPick }: { r: HeatRow; lens: Lens;
  hasCard: boolean; onPick: () => void }) {
  return (<>
    <div className="hlabel">{r.tenor}</div>
    {["10P", "25P", "ATM", "25C", "10C"].map((n) => {
      const c = r.nodes[n];
      const [bg, txt] = lens === "LEVEL"
        ? [pctColor(c.pct * 0.4 + 30), c.vol.toFixed(1)]
        : lens === "ΔT-1"
          ? [pctColor(50 + Math.max(-1, Math.min(1, c.d1 / 0.4)) * 50),
             (c.d1 >= 0 ? "+" : "") + c.d1.toFixed(2)]
          : [pctColor(c.pct), String(Math.round(c.pct))];
      const hot = lens === "%ILE" && (c.pct >= 95 || c.pct <= 5);
      return (<button key={n} className="cell" onClick={onPick}
        title={`${r.tenor} ${n} · ${c.vol} vol · p${c.pct} · Δ${c.d1}\n${
          r.provenance}`}
        style={{ background: bg, outline: hasCard
          ? "1.5px solid var(--amber)"
          : hot ? "1px dotted var(--amber)" : undefined }}>{txt}</button>);
    })}
  </>);
}
