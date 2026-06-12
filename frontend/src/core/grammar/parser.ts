/** Command-line grammar (design v1.1 §5.2).
 *
 * input := command | jump | search
 *  - tokens are ORDER-FLEXIBLE: "SMIL EURJPY 3M" == "EURJPY 3M SMIL"
 *  - bare pair => repoint focused panel (shift: whole link group)
 *  - "WS <mnemonic>" => switch workspace
 *  - "SIGS >2" / "OPPS >1.5" => open with z filter
 *  - anything unresolvable => fuzzy search fallthrough
 *
 * The parser is pure and shared (palette today, ASST later).
 */
import { PAIRS, PANEL_KINDS, TENORS, type Pair, type PanelKind,
  type Tenor } from "../types";

export type Command =
  | { kind: "open-panel"; panel: PanelKind; pair?: Pair; tenor?: Tenor;
      zMin?: number }
  | { kind: "repoint"; pair: Pair; tenor?: Tenor }
  | { kind: "workspace"; mnemonic: string }
  | { kind: "search"; query: string };

const PAIR_SET = new Set<string>(PAIRS);
const TENOR_SET = new Set<string>(TENORS);
const PANEL_SET = new Set<string>(PANEL_KINDS);

export function parse(raw: string): Command {
  const text = raw.trim();
  if (!text) return { kind: "search", query: "" };
  const tokens = text.toUpperCase().split(/\s+/);

  if (tokens[0] === "WS" && tokens[1])
    return { kind: "workspace", mnemonic: tokens[1] };

  let panel: PanelKind | undefined;
  let pair: Pair | undefined;
  let tenor: Tenor | undefined;
  let zMin: number | undefined;
  let unresolved = 0;

  for (const t of tokens) {
    if (PANEL_SET.has(t) && !panel) panel = t as PanelKind;
    else if (PAIR_SET.has(t) && !pair) pair = t as Pair;
    else if (TENOR_SET.has(t) && !tenor) tenor = t as Tenor;
    else if (/^>\d+(\.\d+)?$/.test(t)) zMin = parseFloat(t.slice(1));
    else unresolved++;
  }

  if (unresolved > 0 && !panel && !pair)
    return { kind: "search", query: text };
  if (panel) return { kind: "open-panel", panel, pair, tenor, zMin };
  if (pair) return { kind: "repoint", pair, tenor };
  return { kind: "search", query: text };
}

/** Pair prefix completion: "EURJ" -> EURJPY (unique prefix only). */
export function completePair(prefix: string): Pair | null {
  const up = prefix.toUpperCase();
  const hits = PAIRS.filter((p) => p.startsWith(up));
  return hits.length === 1 ? hits[0] : null;
}
