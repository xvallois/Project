/** Global keyboard layer (design v1.1 §5). Panel-local keys (j/k, L, ...)
 *  live in their panels; this hook owns only app-level chords. */
import { useEffect } from "react";
import { useUi, useWorkspaces } from "../state/stores";

export function useGlobalKeys() {
  const setPalette = useUi((s) => s.setPalette);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const ws = useWorkspaces.getState();
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); setPalette(true);
      } else if ((e.ctrlKey || e.metaKey) && e.key === "`") {
        e.preventDefault(); setPalette(true);   // mode switcher = WS prefix
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault(); ws.saveActive();
      } else if ((e.ctrlKey || e.metaKey) && /^[1-9]$/.test(e.key)) {
        const w = ws.all[parseInt(e.key, 10) - 1];
        if (w) { e.preventDefault(); ws.switchTo(w.mnemonic); }
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [setPalette]);
}
