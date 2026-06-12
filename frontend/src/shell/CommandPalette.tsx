/** Command palette — the front door (design v1.1 §5.2).
 *  The grammar parser is pure & shared; this component only renders
 *  candidate actions and executes the chosen one.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { parse, type Command } from "../core/grammar/parser";
import { PHASE0_PANELS, type PanelKind } from "../core/types";
import { useFeed, useUi, useWorkspaces } from "../state/stores";

interface Item { mn: string; label: string; hint: string; run: () => void }

export function CommandPalette() {
  const open = useUi((s) => s.paletteOpen);
  const setPalette = useUi((s) => s.setPalette);
  const setLink = useUi((s) => s.setLink);
  const ws = useWorkspaces();
  const feed = useFeed((s) => s.feed);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) { setQ(""); setSel(0); setTimeout(() => inputRef.current?.focus()); }
  }, [open]);

  const items = useMemo<Item[]>(() => {
    const cmd: Command = parse(q);
    const out: Item[] = [];
    const openPanel = (kind: PanelKind, pair?: any, tenor?: any, zMin?: number) =>
      ws.dockApi?.openPanel({ kind, pair, tenor, zMin });

    if (cmd.kind === "open-panel") {
      const phase0 = PHASE0_PANELS.includes(cmd.panel);
      out.push({
        mn: cmd.panel,
        label: `${cmd.panel}${cmd.pair ? ` · ${cmd.pair}` : ""}` +
          `${cmd.tenor ? ` ${cmd.tenor}` : ""}` +
          `${cmd.zMin ? ` · |z| > ${cmd.zMin}` : ""}`,
        hint: phase0 ? "open · Enter" : "mnemonic reserved (later phase)",
        run: () => phase0 && openPanel(cmd.panel, cmd.pair, cmd.tenor, cmd.zMin),
      });
      if (cmd.pair) out.push({
        mn: "LINK", label: `Repoint link group A → ${cmd.pair}` +
          `${cmd.tenor ? ` ${cmd.tenor}` : ""}`,
        hint: "Shift+Enter",
        run: () => setLink("A", { pair: cmd.pair!, ...(cmd.tenor
          ? { tenor: cmd.tenor } : {}) }),
      });
    } else if (cmd.kind === "repoint") {
      out.push({
        mn: "LINK", label: `Repoint link group A → ${cmd.pair}` +
          `${cmd.tenor ? ` ${cmd.tenor}` : ""}`,
        hint: "Enter",
        run: () => setLink("A", { pair: cmd.pair, ...(cmd.tenor
          ? { tenor: cmd.tenor } : {}) }),
      });
    } else if (cmd.kind === "workspace") {
      const hit = ws.all.find((w) => w.mnemonic === cmd.mnemonic);
      out.push({
        mn: "WS", label: hit ? `Switch to ${hit.name}` : `No mode ${cmd.mnemonic}`,
        hint: hit ? "Enter" : "",
        run: () => hit && ws.switchTo(hit.mnemonic),
      });
    }
    // fuzzy fallthrough: modes + open opportunity cards + panels
    const needle = q.trim().toLowerCase();
    if (needle) {
      for (const w of ws.all)
        if (w.name.toLowerCase().includes(needle) ||
            w.mnemonic.toLowerCase().includes(needle))
          out.push({ mn: "WS", label: w.name, hint: w.mnemonic,
            run: () => ws.switchTo(w.mnemonic) });
      for (const id of feed.order.slice(0, 30)) {
        const c = feed.cards[id];
        if (["dismissed", "invalidated", "expired"].includes(c.status)) continue;
        if (`${c.pair} ${c.headline}`.toLowerCase().includes(needle))
          out.push({ mn: "OPPS", label: `${c.pair} · ${c.headline}`,
            hint: c.band, run: () => ws.dockApi?.openPanel({ kind: "OPPS" }) });
      }
    } else {
      for (const k of PHASE0_PANELS)
        out.push({ mn: k, label: `Open ${k}`, hint: "panel",
          run: () => openPanel(k) });
    }
    return out.slice(0, 9);
  }, [q, ws, feed, setLink]);

  if (!open) return null;
  const exec = (i: number) => { items[i]?.run(); setPalette(false); };

  return (
    <>
      <div className="overlay" onClick={() => setPalette(false)} />
      <div className="palette" role="dialog" aria-label="Command line">
        <div className="pin"><b>›</b>
          <input ref={inputRef} value={q} spellCheck={false}
            placeholder="SMIL EURJPY 3M · SIGS >2 · WS ECB · or search"
            onChange={(e) => { setQ(e.target.value); setSel(0); }}
            onKeyDown={(e) => {
              if (e.key === "Escape") setPalette(false);
              else if (e.key === "ArrowDown")
                setSel((s) => Math.min(s + 1, items.length - 1));
              else if (e.key === "ArrowUp") setSel((s) => Math.max(s - 1, 0));
              else if (e.key === "Enter") exec(sel);
            }} />
        </div>
        <div>
          {items.map((it, i) => (
            <button key={i} className={`pitem ${i === sel ? "sel" : ""}`}
              onMouseEnter={() => setSel(i)} onClick={() => exec(i)}>
              <span className="pm">{it.mn}</span>{it.label}
              <span className="pd">{it.hint}</span>
            </button>
          ))}
        </div>
        <div className="pfoot"><span>Enter run</span><span>↑↓ select</span>
          <span>Esc close</span><span>grammar: MNEMONIC PAIR TENOR, any order</span>
        </div>
      </div>
    </>
  );
}
