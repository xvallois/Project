/** OPPS over the LIVE engine — the product surface (Phase 1 §2).
 *  Expanded cards show the analyst-shaped sections; every number renders
 *  with its provenance ref on hover (the chain ends at the screen). */
import { useEffect, useMemo, useState } from "react";
import { getDriver, postSurfaceOpen, type DriverSeries, type ServerCard,
  type ServerItem } from "../api/client";
import { useUi } from "../state/stores";
import { DISMISSAL_REASONS, type DismissalReason }
  from "../core/opportunities/types";
import type { PanelParams } from "../shell/DockHost";
import { useEngine } from "../state/engine";

const Ref = ({ i }: { i: ServerItem }) => (
  <span title={`source: ${i.provenance}`}
    style={{ borderBottom: "1px dotted #3a4d6b", cursor: "help" }}>
    {i.label} <b className="num">{i.value}</b>
    {i.provenance.startsWith("prior:") &&
      <em className="mut"> (placeholder)</em>}
  </span>
);

function Driver({ id }: { id: string }) {
  const [d, setD] = useState<DriverSeries | null>(null);
  useEffect(() => { getDriver(id).then(setD).catch(() => null);
    postSurfaceOpen("driver", undefined, undefined, id); }, [id]);
  if (!d || !d.series.length) return null;
  const vs = d.series.map((p) => p.value);
  const lo = Math.min(...vs), hi = Math.max(...vs) || lo + 1;
  const X = (i: number) => (i * 200) / Math.max(1, d.series.length - 1);
  const Y = (v: number) => 26 - ((v - lo) / (hi - lo || 1)) * 24;
  const det = d.detected_at.slice(0, 10);
  const di = d.series.findIndex((p) => p.date >= det);
  return (
    <div style={{ marginTop: 4 }} title={d.provenance}>
      <span className="ctype">DRIVER · {d.tenor} {d.field} </span>
      <svg width="204" height="28" style={{ verticalAlign: "middle" }}>
        <path fill="none" stroke="#74a6d4" strokeWidth="1"
          d={d.series.map((p, i) =>
            `${i ? "L" : "M"}${X(i)} ${Y(p.value)}`).join(" ")} />
        {di >= 0 && <circle cx={X(di)} cy={Y(d.series[di].value)} r="2.5"
          fill="var(--amber)" />}
      </svg>
      <span className="cev"> ● detection · {d.series.length}d</span>
    </div>
  );
}

const age = (iso: string) => {
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  return s < 90 ? `${s | 0}s` : s < 5400 ? `${(s / 60) | 0}m`
    : `${(s / 3600) | 0}h`;
};

export function OppsLivePanel({ params }: { params: PanelParams }) {
  const { cards, transition, toBlotter, investigate, investigating }
    = useEngine();
  const [sortAnalyst, setSortAnalyst] = useState(false);
  const [sel, setSel] = useState(0);
  const [dismissing, setDismissing] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const selectedCard = useUi((s) => s.selectedCard);
  const setSelectedCard = useUi((s) => s.setSelectedCard);

  const rank: Record<ServerCard["band"], number> =
    { ACTIONABLE: 2, WATCH: 1, SPECULATIVE: 0 };
  const live = useMemo(() => cards
    .filter((c) => ["new", "seen", "watching", "acted"].includes(c.status))
    .filter((c) => !params.zMin || c.confidence.absZ >= params.zMin)
    .sort((a, b) => sortAnalyst
      ? (a.analyst_rank ?? 99) - (b.analyst_rank ?? 99)
      : (rank[b.band] - rank[a.band])
        || b.confidence.absZ - a.confidence.absZ),
    [cards, params.zMin, sortAnalyst]);
  // heatmap → card routing (decision surfaces select into the feed)
  useEffect(() => {
    if (!selectedCard) return;
    const i = live.findIndex((c) => c.id === selectedCard);
    if (i >= 0) setSel(i);
    setSelectedCard(null);
  }, [selectedCard, live, setSelectedCard]);

  const dead = useMemo(() => cards
    .filter((c) => c.status === "invalidated")
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 5), [cards]);

  const onKey = (e: React.KeyboardEvent) => {
    const c = live[sel];
    if (e.key === "j" || e.key === "ArrowDown")
      setSel((s) => Math.min(s + 1, live.length - 1));
    else if (e.key === "k" || e.key === "ArrowUp")
      setSel((s) => Math.max(s - 1, 0));
    else if (!c) return;
    else if (e.key === "Enter") transition(c.id, "seen");
    else if (e.key.toLowerCase() === "w") transition(c.id, "watching");
    else if (e.key.toLowerCase() === "b") toBlotter(c);
    else if (e.key.toLowerCase() === "x") setDismissing(c.id);
    else if (e.key.toLowerCase() === "i") investigate(c.id);
    else return;
    e.preventDefault();
  };

  return (
    <>
      <div className="fchips">
        <span className="fchip act">LIVE ENGINE · {live.length}</span>
        <span className="fchip">invalidated {
          cards.filter((c) => c.status === "invalidated").length}</span>
        <button className={`fchip ${sortAnalyst ? "act" : ""}`}
          title="order by the Analyst's triage — bands stay the engine's"
          onClick={() => setSortAnalyst((v) => !v)}>
          SORT: {sortAnalyst ? "ANALYST" : "ENGINE"}</button>
        <span className="fchip" style={{ marginLeft: "auto", border: "none" }}>
          j/k · ⏎ · W · B · X</span>
      </div>
      <div className="feed" tabIndex={0} onKeyDown={onKey}>
        {live.map((c, i) => (
          <div key={c.id} className={`card ${i === sel ? "sel" : ""}`}
            onClick={() => { setSel(i);
              if (c.status === "new") transition(c.id, "seen"); }}>
            <div className="crow">
              <span className={`band b-${c.band}`}>{c.band}</span>
              <span className="ctype">{c.type.replace(/_/g, " ")}</span>
              {c.status === "watching" && <span className="ctype"
                style={{ color: "var(--lA)" }}>◉</span>}
              {c.status === "acted" && <span className="ctype"
                style={{ color: "var(--up)" }}>→ blotter</span>}
              <span className="ctype" title={`detected ${c.detected_at}`}>
                {age(c.detected_at)}</span>
              <span className="cpair">{c.pair} · {
                c.tenors.slice(0, 3).join("/") || "—"}</span>
            </div>
            <div className="chead">{c.headline}</div>
            {c.analyst_note && <div className="anote">
              <span className="chip c-ana">ANALYST</span>
              {c.analyst_note}</div>}
            <div className="cev">
              {c.evidence.slice(0, 3).map((it: ServerItem, j: number) =>
                <span key={j}>{j > 0 && " · "}<Ref i={it} /></span>)}
            </div>
            <div className="cconf">
              |z| {c.confidence.absZ.toFixed(1)} ·
              {" "}{c.confidence.persistedCycles} cycles ·
              {" "}models {c.confidence.modelsAgree ? "agree" : "diverge"} ·
              {" "}dq {c.confidence.dataQualityOk ? "✓" : "⚠"}
            </div>
            {i === sel && (
              <div style={{ marginTop: 6, fontSize: 11 }}>
                <div><span className="ctype">WHY TRIGGERED · </span>
                  <span className="mut">{c.findings}</span></div>
                {c.contradictions.length > 0 && (
                  <div style={{ marginTop: 3 }}>
                    <span className="ctype" style={{ color: "#caa45c" }}>
                      CONTRADICTIONS · </span>
                    {c.contradictions.map((it: ServerItem, j: number) =>
                      <span key={j} className="mut">{j > 0 && "; "}
                        <Ref i={it} /></span>)}</div>)}
                <div style={{ marginTop: 3 }}>
                  <span className="ctype">INVALIDATES · </span>
                  <span className="mut">{
                    c.invalidation_criteria.join(" · ")}</span></div>
                <Driver id={c.id} />
                <div style={{ marginTop: 3 }}>
                  <span className="ctype">SIMILAR · </span>
                  {c.similar_history_items.map((it: ServerItem, j: number) =>
                    <span key={j} className="mut"><Ref i={it} /></span>)}
                </div>
                <div className="cact">
                  <button className="btn pri"
                    disabled={investigating !== null}
                    title="Research brief from the Analyst · 3 units"
                    onClick={() => investigate(c.id)}>
                    {investigating === c.id ? "Investigating…"
                      : "Investigate I · 3u"}</button>
                  <button className="btn"
                    disabled={investigating !== null}
                    title="Deep dive · 10 units"
                    onClick={() => investigate(c.id, "deep")}>Deep · 10u
                  </button>
                  <button className="btn"
                    onClick={() => toBlotter(c)}>→ Blotter B</button>
                  <button className="btn" onClick={() =>
                    transition(c.id, "watching")}>Watch W</button>
                  <button className="btn" onClick={() =>
                    setDismissing(c.id)}>Dismiss X</button>
                </div>
              </div>
            )}
          </div>
        ))}
        {dead.length > 0 && <div className="fchips"
          style={{ borderTop: "1px solid var(--line)" }}>
          <span className="fchip">recent invalidations</span></div>}
        {dead.map((c) => (
          <div key={c.id} className="card dead">
            <div className="crow"><span className="band b-SPECULATIVE">
              INVALIDATED</span>
              <span className="ctype">{c.type.replace(/_/g, " ")}</span>
              <span className="cpair">{c.pair}</span></div>
            <div className="cev">{c.headline} · closed without action ·
              {" "}{age(c.invalidation?.at ?? c.updated_at)} ago</div>
          </div>
        ))}
      </div>
      {dismissing && (
        <>
          <div className="overlay" onClick={() => setDismissing(null)} />
          <div className="modal">
            <h3>Dismiss — reason required (recorded for ranking)</h3>
            {DISMISSAL_REASONS.map((r: DismissalReason) => (
              <button key={r} className="opt" onClick={() => {
                transition(dismissing, "dismissed", r, note || undefined);
                setDismissing(null); setNote(""); }}>{r}</button>))}
            <textarea rows={2} placeholder="optional note" value={note}
              onChange={(e) => setNote(e.target.value)} />
          </div>
        </>
      )}
    </>
  );
}
