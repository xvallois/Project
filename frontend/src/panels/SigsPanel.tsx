/** SIGS — raw observation monitor (the Tier-1 layer under the feed). */
import { useMemo } from "react";
import { detect } from "../mock/market";
import type { PanelParams } from "../shell/DockHost";
import { useMarket, useWorkspaces } from "../state/stores";

export function SigsPanel({ params }: { params: PanelParams }) {
  const history = useMarket((s) => s.history);
  const asof = useMarket((s) => s.asof);
  const ws = useWorkspaces();
  const rows = useMemo(() => detect(history, asof)
    .filter((o) => !params.zMin || Math.abs(o.zscore ?? 0) >= params.zMin)
    .sort((a, b) => Math.abs(b.zscore ?? 0) - Math.abs(a.zscore ?? 0)),
    [history, asof, params.zMin]);
  return (
    <div style={{ overflow: "auto", height: "100%" }}>
      <table>
        <thead><tr><th>type</th><th>pair</th><th>tenor</th>
          <th>metric</th><th>value</th><th>p</th><th>z</th></tr></thead>
        <tbody>
          {rows.map((o) => (
            <tr key={o.id} style={{ cursor: "pointer" }}
              onClick={() => ws.dockApi?.openPanel({ kind: "SMIL",
                pair: o.pair, tenor: o.tenor })}>
              <td>{o.type.replace("_", " ").toLowerCase()}</td>
              <td>{o.pair}</td><td>{o.tenor ?? "—"}</td>
              <td>{o.metric}</td><td>{o.value}</td>
              <td>{o.percentile ?? "—"}</td>
              <td className={Math.abs(o.zscore ?? 0) >= 2.5 ? "neg" : ""}>
                {o.zscore?.toFixed(2) ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {params.zMin != null &&
        <div className="cev" style={{ padding: 8 }}>
          filtered: |z| ≥ {params.zMin}</div>}
    </div>
  );
}
