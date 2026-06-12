/** BLOT — the unified decision ledger (locked decision #4). */
import { useState } from "react";
import type { PanelParams } from "../shell/DockHost";
import { useBlotter } from "../state/blotter";

export function BlotPanel(_: { params: PanelParams }) {
  const { rows, close } = useBlotter();
  const [closing, setClosing] = useState<string | null>(null);
  const [pnl, setPnl] = useState("");
  const [note, setNote] = useState("");
  return (
    <div style={{ overflow: "auto", height: "100%" }}>
      <table>
        <thead><tr><th>kind</th><th>status</th><th>pair</th>
          <th>structure</th><th>opened</th><th>pnl vp</th><th /></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} title={r.entryThesis}>
              <td>{r.kind}</td>
              <td className={r.status === "open" ? "pos" : "mut"}>{r.status}</td>
              <td>{r.pair}</td>
              <td style={{ maxWidth: 180, overflow: "hidden",
                textOverflow: "ellipsis" }}>{r.structure}</td>
              <td>{r.openedAt.slice(5, 16).replace("T", " ")}</td>
              <td className={(r.pnlVolPts ?? 0) >= 0 ? "pos" : "neg"}>
                {r.pnlVolPts?.toFixed(2) ?? "—"}</td>
              <td>{r.status === "open" &&
                <button className="btn" onClick={() => setClosing(r.id)}>
                  close</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <div className="phase-note">
        Empty ledger. Send an opportunity here with B — its evidence is
        frozen as the entry thesis.</div>}
      {closing && (
        <>
          <div className="overlay" onClick={() => setClosing(null)} />
          <div className="modal">
            <h3>Close entry — outcome required (feeds post-mortems)</h3>
            <input placeholder="pnl in vol pts, e.g. -0.8" value={pnl}
              style={{ width: "100%", background: "var(--ink)",
                border: "1px solid var(--line)", borderRadius: 3,
                color: "var(--text)", padding: 6, font: "11px var(--mono)" }}
              onChange={(e) => setPnl(e.target.value)} />
            <textarea rows={2} placeholder="what happened" value={note}
              onChange={(e) => setNote(e.target.value)} />
            <button className="btn pri" style={{ marginTop: 8 }}
              onClick={() => { close(closing, parseFloat(pnl) || 0, note);
                setClosing(null); setPnl(""); setNote(""); }}>
              Save outcome</button>
          </div>
        </>
      )}
    </div>
  );
}
