import { useEffect, useState } from "react";
import { useUi, useWorkspaces } from "../state/stores";

const clock = (tz: string) =>
  new Date().toLocaleTimeString("en-GB", { timeZone: tz, hour: "2-digit",
    minute: "2-digit" });

export function TopBar() {
  const { all, activeId, dirty, switchTo } = useWorkspaces();
  const setPalette = useUi((s) => s.setPalette);
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((x) => x + 1), 30_000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="top">
      <span className="logo">VOLWATCH</span>
      {all.map((w) => (
        <button key={w.id}
          className={`wstab ${w.id === activeId ? "act" : ""}`}
          title={`${w.name} · Ctrl+${all.indexOf(w) + 1}`}
          onClick={() => switchTo(w.mnemonic)}>
          {w.mnemonic}
          {w.id === activeId && dirty && <span className="dirty"> *</span>}
        </button>
      ))}
      <button className="cmdslot" onClick={() => setPalette(true)}>
        <b>›</b><span>SMIL EURJPY 3M · SIGS &gt;2 · WS ECB …</span>
        <span style={{ marginLeft: "auto" }} className="kbd">Ctrl+K</span>
      </button>
      <div className="clocks">
        <span>NYC <b>{clock("America/New_York")}</b></span>
        <span>LDN <b>{clock("Europe/London")}</b></span>
        <span>TYO <b>{clock("Asia/Tokyo")}</b></span>
      </div>
    </div>
  );
}
