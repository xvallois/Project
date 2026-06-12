import { useEffect } from "react";
import { CommandPalette } from "./shell/CommandPalette";
import { DockHost } from "./shell/DockHost";
import { Rail } from "./shell/Rail";
import { StatusBar } from "./shell/StatusBar";
import { TopBar } from "./shell/TopBar";
import { useGlobalKeys } from "./shell/useKeyboard";
import { useFeed, useMarket } from "./state/stores";
import { useEngine } from "./state/engine";

export default function App() {
  useGlobalKeys();
  useEffect(() => { useEngine.getState().start(); }, []);
  // mock realtime: a "snap" every 20s ages freshness and re-runs Tier-1.
  useEffect(() => {
    const t = setInterval(() => {
      useMarket.setState({ asof: new Date().toISOString() });
      useFeed.getState().runCycle();
    }, 20_000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="app">
      <TopBar />
      <div className="main">
        <Rail />
        <div className="dockwrap"><DockHost /></div>
      </div>
      <StatusBar />
      <CommandPalette />
    </div>
  );
}
