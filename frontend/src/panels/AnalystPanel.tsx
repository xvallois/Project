/** ASST — the Analyst panel (Phase 2). Renders the latest Research Brief
 *  with the locked trust separation: ANALYST statements are visually and
 *  structurally distinct from DETERMINISTIC evidence; every number in
 *  analyst prose traces to a cited engine item (hover shows the ref). */
import { useMemo } from "react";
import type { BriefEvidence, BriefStatement, ResearchBrief }
  from "../api/client";
import type { PanelParams } from "../shell/DockHost";
import { useEngine } from "../state/engine";

const TITLES: [string, string][] = [
  ["finding", "FINDING"], ["supporting", "SUPPORTING EVIDENCE"],
  ["contradictory", "CONTRADICTORY EVIDENCE"], ["why_now", "WHY NOW"],
  ["invalidation", "WHAT WOULD INVALIDATE THIS"],
  ["historical", "SIMILAR HISTORICAL EPISODES"],
  ["next_investigation", "SUGGESTED NEXT INVESTIGATION"]];

function Cite({ e }: { e: BriefEvidence }) {
  return (
    <span className="cite" title={`ENGINE · ${e.provenance}`}>
      {e.label} <b className="num">{e.value}</b>
    </span>
  );
}

function Line({ st, ev }: { st: BriefStatement;
  ev: Map<string, BriefEvidence> }) {
  return (
    <div className={st.kind === "analyst" ? "ana" : "det"}>
      <span className={`chip ${st.kind === "analyst" ? "c-ana" : "c-det"}`}>
        {st.kind === "analyst" ? "ANALYST" : "ENGINE"}</span>
      <span>{st.text}</span>
      {st.cites.length > 0 && (
        <span className="cites">
          {st.cites.map((c) => { const e = ev.get(c);
            return e ? <Cite key={c} e={e} /> : null; })}
        </span>
      )}
    </div>
  );
}

export function AnalystPanel(_: { params: PanelParams }) {
  const brief = useEngine((s) => s.brief);
  const investigating = useEngine((s) => s.investigating);
  const health = useEngine((s) => s.health);
  const ev = useMemo(() => new Map(
    (brief?.evidence ?? []).map((e) => [e.eid, e])), [brief]);

  if (investigating) return (
    <div className="phase-note">Investigating {investigating} —
      assembling evidence pack, running capped analysis…</div>);
  if (!brief) return (
    <div className="phase-note" style={{ padding: 16, textAlign: "center" }}>
      No brief yet. Select a card in OPPS and press I (3 units) —
      the note arrives here.<br /><br />
      <span className="mut">Analyst: {health.analyst ?? "—"} ·
        budget {health.budget?.remaining ?? "—"}u remaining</span>
    </div>);
  if (brief.refused) return (
    <div className="phase-note">Budget refusal: {brief.refused}.
      Deterministic feed unaffected — the engine keeps running.</div>);
  if (brief.error || brief.status === "rejected") return (
    <div className="phase-note" style={{ color: "var(--down)" }}>
      Brief rejected by the provenance gate
      ({brief.dropped?.slice(0, 2).join("; ") ?? brief.error}).
      Nothing ungated reaches this panel.</div>);

  return (
    <div style={{ overflow: "auto", height: "100%", padding: "8px 12px" }}>
      <div className="crow" style={{ marginBottom: 8 }}>
        <span className={`chip ${brief.provider === "claude"
          ? "c-ana" : "c-stub"}`}>
          ANALYST · {brief.provider.toUpperCase()}</span>
        <span className="ctype">{brief.depth} · {brief.units}u ·
          {" "}{brief.model}</span>
        {brief.status === "degraded" &&
          <span className="ctype" style={{ color: "var(--amber)" }}>
            {brief.dropped.length} statement{brief.dropped.length > 1 ?
              "s" : ""} dropped by the numeric gate</span>}
        <span className="cpair">{brief.card_id.split("|")[1] ?? ""}</span>
      </div>
      <div className="cev" style={{ marginBottom: 10 }}>{brief.card_id}</div>
      {TITLES.map(([key, title]) => (
        <div key={key} style={{ marginBottom: 10 }}>
          <div className="ctype" style={{ marginBottom: 3 }}>{title}</div>
          {(brief.sections[key] ?? []).map((st, i) =>
            <Line key={i} st={st} ev={ev} />)}
          {!(brief.sections[key] ?? []).length &&
            <div className="mut" style={{ fontSize: 10 }}>—</div>}
        </div>
      ))}
      <div className="cev" style={{ borderTop: "1px solid var(--line)",
        paddingTop: 6 }}>
        Every number above cites engine evidence; hover a citation for its
        provenance ref. Confidence bands remain the engine's alone.
      </div>
    </div>
  );
}
