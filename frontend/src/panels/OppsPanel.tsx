/** OPPS — the hero panel. Deterministic feed (Phase 0: Tier-1 only).
 *  Keyboard on the focused feed: j/k move · Enter expand/seen ·
 *  W watch · B blotter · X dismiss (picklist modal) · I reserved (Phase 2).
 */
import { useMemo, useRef, useState } from "react";
import { DISMISSAL_REASONS, type Band, type DismissalReason,
  type OpportunityCard } from "../core/opportunities/types";
import type { PanelParams } from "../shell/DockHost";
import { useBlotter } from "../state/blotter";
import { useFeed, useWorkspaces } from "../state/stores";

const BANDS: (Band | "ALL")[] = ["ALL", "ACTIONABLE", "WATCH", "SPECULATIVE"];

export function OppsPanel({ params }: { params: PanelParams }) {
  const { feed, act, dismiss } = useFeed();
  const addBlot = useBlotter((s) => s.add);
  const ws = useWorkspaces();
  const [bandFilter, setBandFilter] = useState<Band | "ALL">("ALL");
  const [sel, setSel] = useState(0);
  const [dismissing, setDismissing] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const ids = useMemo(() => feed.order.filter((id) => {
    const c = feed.cards[id];
    if (bandFilter !== "ALL" && c.band !== bandFilter
      && !["invalidated"].includes(c.status)) return false;
    if (params.zMin && c.confidence.absZ < params.zMin) return false;
    return true;
  }), [feed, bandFilter, params.zMin]);

  const toBlotter = (c: OpportunityCard) => {
    addBlot({
      kind: "idea", status: "open", pair: c.pair, structure: c.structure,
      direction: c.type.toLowerCase(), linkedOpportunityId: c.id,
      entryThesis: `${c.headline} — ` + c.evidence.map((e) =>
        `${e.metric}=${e.value}${e.percentile ? ` (p${e.percentile})` : ""}`)
        .join("; "),
    });
    act(c.id, "acted");
  };

  const onKey = (e: React.KeyboardEvent) => {
    const id = ids[sel];
    const c = id ? feed.cards[id] : undefined;
    if (e.key === "j" || e.key === "ArrowDown")
      setSel((s) => Math.min(s + 1, ids.length - 1));
    else if (e.key === "k" || e.key === "ArrowUp")
      setSel((s) => Math.max(s - 1, 0));
    else if (!c) return;
    else if (e.key === "Enter") act(c.id, "seen");
    else if (e.key.toLowerCase() === "w") act(c.id, "watching");
    else if (e.key.toLowerCase() === "b") toBlotter(c);
    else if (e.key.toLowerCase() === "x") setDismissing(c.id);
    else if (e.key.toLowerCase() === "g")
      ws.dockApi?.openPanel({ kind: "SMIL", pair: c.pair,
        tenor: c.tenors[0] });
    else return;
    e.preventDefault();
  };

  const counts = useMemo(() => {
    const live = feed.order.map((i) => feed.cards[i])
      .filter((c) => !["dismissed", "invalidated", "expired"].includes(c.status));
    return { ALL: live.length,
      ACTIONABLE: live.filter((c) => c.band === "ACTIONABLE").length,
      WATCH: live.filter((c) => c.band === "WATCH").length,
      SPECULATIVE: live.filter((c) => c.band === "SPECULATIVE").length };
  }, [feed]);

  return (
    <>
      <div className="fchips">
        {BANDS.map((b) => (
          <button key={b} className={`fchip ${b === bandFilter ? "act" : ""}`}
            onClick={() => setBandFilter(b)}>
            {b} {counts[b as keyof typeof counts] ?? ""}
          </button>
        ))}
        <span className="fchip" style={{ marginLeft: "auto", border: "none" }}>
          j/k · ⏎ seen · W watch · B blotter · X dismiss
        </span>
      </div>
      <div className="feed" tabIndex={0} ref={listRef} onKeyDown={onKey}>
        {ids.map((id, i) => {
          const c = feed.cards[id];
          const dead = ["dismissed", "invalidated", "expired"]
            .includes(c.status);
          return (
            <div key={id}
              className={`card ${i === sel ? "sel" : ""} ${dead ? "dead" : ""}`}
              onClick={() => { setSel(i); act(c.id, "seen"); }}>
              <div className="crow">
                <span className={`band b-${c.band}`}>
                  {c.status === "invalidated" ? "INVALIDATED" : c.band}
                </span>
                <span className="ctype">{c.type.replace("_", " ")}</span>
                {c.status === "watching" &&
                  <span className="ctype" style={{ color: "var(--lA)" }}>◉ watching</span>}
                {c.status === "acted" &&
                  <span className="ctype" style={{ color: "var(--up)" }}>→ blotter</span>}
                <span className="cpair">{c.pair} · {c.tenors.join("/") || "—"}</span>
              </div>
              <div className="chead">{c.headline}</div>
              {c.status === "invalidated" && c.invalidation ? (
                <div className="cev">closed without action ·
                  {" "}{new Date(c.invalidation.at).toLocaleTimeString()} ·
                  {" "}<a href="#" className="mut" onClick={(e) => e.preventDefault()}>
                    original card</a></div>
              ) : (
                <>
                  <div className="cev">
                    {c.evidence.slice(0, 3).map((e, j) =>
                      <span key={j}>{j > 0 && " · "}{e.metric} {e.value}
                        {e.percentile != null && <b style={{ color: "#e0a0ac" }}
                          > p{e.percentile}</b>}</span>)}
                  </div>
                  <div className="cconf">
                    |z| {c.confidence.absZ.toFixed(1)} ·
                    {" "}{c.confidence.persistenceCycles} cycle
                    {c.confidence.persistenceCycles > 1 ? "s" : ""} ·
                    {" "}models {c.confidence.modelsAgree ? "agree" : "diverge"} ·
                    {" "}dq {c.confidence.dataQualityOk ? "✓" : "⚠"}
                    <span title="Confidence = evidence strength, never probability of profit."
                      style={{ marginLeft: 6, cursor: "help" }}>ⓘ</span>
                  </div>
                  {i === sel && !dead && (
                    <div className="cact">
                      <button className="btn pri"
                        title="Analyst deep-dive arrives in Phase 2 (10 units)"
                        disabled>Investigate I</button>
                      <button className="btn" onClick={() =>
                        ws.dockApi?.openPanel({ kind: "SMIL", pair: c.pair,
                          tenor: c.tenors[0] })}>Open G</button>
                      <button className="btn" onClick={() => toBlotter(c)}>
                        → Blotter B</button>
                      <button className="btn" onClick={() =>
                        act(c.id, "watching")}>Watch W</button>
                      <button className="btn" onClick={() =>
                        setDismissing(c.id)}>Dismiss X</button>
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}
        {!ids.length && <div className="phase-note">
          No opportunities at this filter. The feed re-scans every snap.
        </div>}
      </div>
      {dismissing && <DismissModal
        onPick={(reason, note) => { dismiss(dismissing, reason, note);
          setDismissing(null); listRef.current?.focus(); }}
        onCancel={() => { setDismissing(null); listRef.current?.focus(); }} />}
    </>
  );
}

/** Locked decision #1: required picklist + optional note. */
function DismissModal({ onPick, onCancel }: {
  onPick: (r: DismissalReason, note?: string) => void;
  onCancel: () => void;
}) {
  const [sel, setSel] = useState(0);
  const [note, setNote] = useState("");
  return (
    <>
      <div className="overlay" onClick={onCancel} />
      <div className="modal" role="dialog" aria-label="Dismiss opportunity"
        onKeyDown={(e) => {
          if (e.key === "Escape") onCancel();
          else if (e.key === "ArrowDown")
            setSel((s) => Math.min(s + 1, DISMISSAL_REASONS.length - 1));
          else if (e.key === "ArrowUp") setSel((s) => Math.max(s - 1, 0));
          else if (e.key === "Enter" && (e.target as HTMLElement).tagName
            !== "TEXTAREA")
            onPick(DISMISSAL_REASONS[sel], note || undefined);
        }}>
        <h3>Dismiss — reason required (feeds future ranking)</h3>
        {DISMISSAL_REASONS.map((r, i) => (
          <button key={r} className={`opt ${i === sel ? "sel" : ""}`}
            autoFocus={i === 0}
            onClick={() => onPick(r, note || undefined)}
            onMouseEnter={() => setSel(i)}>
            {i + 1}. {r}
          </button>
        ))}
        <textarea rows={2} placeholder="optional note" value={note}
          onChange={(e) => setNote(e.target.value)} />
      </div>
    </>
  );
}
