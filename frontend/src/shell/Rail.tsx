import { PHASE0_PANELS } from "../core/types";
import { useWorkspaces } from "../state/stores";

export function Rail() {
  const dockApi = useWorkspaces((s) => s.dockApi);
  return (
    <div className="rail">
      {PHASE0_PANELS.map((k) => (
        <button key={k} className="rico" title={k}
          onClick={() => dockApi?.openPanel({ kind: k })}>{k}</button>
      ))}
    </div>
  );
}
