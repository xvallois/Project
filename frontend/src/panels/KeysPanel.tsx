/** KEYS — the searchable shortcut map. The UI teaches its own language. */
import type { PanelParams } from "../shell/DockHost";

const MAP: [string, string][] = [
  ["Ctrl+K", "Command line (grammar: MNEMONIC PAIR TENOR, any order)"],
  ["Ctrl+1..5", "Switch workspace mode"],
  ["Ctrl+`", "Mode switcher (palette pre-filled WS)"],
  ["Ctrl+S", "Save active workspace (layout + links + filters)"],
  ["j / k", "OPPS: move selection"],
  ["Enter", "OPPS: mark seen / expand"],
  ["W", "OPPS: watch"],
  ["B", "OPPS: send to blotter (thesis frozen)"],
  ["X", "OPPS: dismiss (reason picklist, 1-7 to pick)"],
  ["G", "OPPS: fan out to SMIL at the card's node"],
  ["I", "OPPS: Analyst investigate — Phase 2"],
  ["L", "VHEAT: cycle lens LEVEL → ΔT-1 → %ILE"],
  ["click link chip", "Cycle panel link group – → A → B → C → D"],
];

export function KeysPanel(_: { params: PanelParams }) {
  return (
    <div style={{ overflow: "auto", height: "100%" }}>
      <table><tbody>
        {MAP.map(([k, v]) => (
          <tr key={k}><td style={{ width: 110 }}>
            <span className="kbd">{k}</span></td>
            <td style={{ textAlign: "left", fontFamily: "var(--sans)" }}>
              {v}</td></tr>
        ))}
      </tbody></table>
    </div>
  );
}
