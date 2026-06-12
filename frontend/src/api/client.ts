/** Sidecar client: REST + one WS with seq tracking and auto-resync.
 *  If the sidecar is unreachable the app falls back to the Phase-0 mock
 *  feed — clearly labeled in the status bar; never silently. */
export const API: string =
  (import.meta as any).env?.VITE_API ?? "http://localhost:8787";

export interface ServerItem { label: string; value: string; provenance: string }
export interface ServerCard {
  id: string; type: string; pair: string; tenors: string[];
  headline: string; structure: string;
  band: "SPECULATIVE" | "WATCH" | "ACTIONABLE";
  confidence: { absZ: number; persistedCycles: number; dataQualityOk: boolean;
    modelsAgree: boolean; backtestPrior: { hitRate: number; n: number;
      placeholder?: boolean } | null };
  findings: string; evidence: ServerItem[]; supporting: ServerItem[];
  contradictions: ServerItem[]; invalidation_criteria: string[];
  similar_history_items: ServerItem[]; similar_history_note: string;
  status: string; created_at: string; updated_at: string; detected_at: string;
  dismissal: { reason: string; note?: string; at: string } | null;
  invalidation: { at: string; outcome: string } | null;
  analyst_rank?: number;            // alongside, never instead of band
  analyst_note?: string;
}

export interface BriefStatement { text: string; kind: string;
  cites: string[] }
export interface BriefEvidence { eid: string; label: string; value: string;
  provenance: string }
export interface ResearchBrief {
  card_id: string; depth: string; provider: string; model: string;
  units: number; status: "ok" | "degraded" | "rejected";
  sections: Record<string, BriefStatement[]>;
  evidence: BriefEvidence[]; dropped: string[]; created_at: string;
  refused?: string; error?: string;
  abstained?: boolean; reason?: string;     // abstention: event, not brief
}
export interface WsEnvelope { topic: string; type: "snapshot" | "delta";
  seq: number; ts: string; data: any }

export async function getFeed(): Promise<ServerCard[]> {
  const r = await fetch(`${API}/api/feed`);
  return (await r.json()).cards as ServerCard[];
}
export async function postTransition(id: string, status: string,
  reason?: string, note?: string): Promise<void> {
  await fetch(`${API}/api/feed/transition`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, status, reason, note }) });
}
export async function postBlotter(body: object): Promise<void> {
  await fetch(`${API}/api/blotter`, { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
}
export interface ServerBlotterRow {
  id: string; kind: string; status: string; pair: string; structure: string;
  direction: string; linked_opportunity_id: string | null;
  entry_thesis: string | null; size: string | null;
  pnl_volpts: number | null; pnl_ccy: number | null; notes: string | null;
  post_mortem: string | null; opened_at: string; closed_at: string | null;
}
export async function getBlotter(): Promise<ServerBlotterRow[]> {
  const r = await fetch(`${API}/api/blotter`);
  return (await r.json()).rows as ServerBlotterRow[];
}
export async function postBlotterClose(
  id: string, pnlVolPts: number, notes: string): Promise<void> {
  await fetch(`${API}/api/blotter/${encodeURIComponent(id)}/close`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pnl_volpts: pnlVolPts, notes }) });
}
export async function getHealth(): Promise<Record<string, unknown>> {
  const r = await fetch(`${API}/api/health`);
  return r.json();
}

export function connectWs(onMsg: (env: WsEnvelope) => void,
  onState: (up: boolean) => void): () => void {
  let ws: WebSocket | null = null;
  let stop = false;
  const seqs: Record<string, number> = {};
  const open = () => {
    ws = new WebSocket(`${API.replace("http", "ws")}/ws`);
    ws.onopen = () => onState(true);
    ws.onmessage = (e: MessageEvent) => {
      const env = JSON.parse(e.data as string) as WsEnvelope;
      const last = seqs[env.topic] ?? -1;
      if (env.type === "delta" && last >= 0 && env.seq > last + 1)
        getFeed().then((cards) => onMsg({ topic: "feed", type: "snapshot",
          seq: env.seq, ts: env.ts, data: { cards } }));
      seqs[env.topic] = env.seq;
      onMsg(env);
    };
    ws.onclose = () => { onState(false);
      if (!stop) setTimeout(open, 2000); };
    ws.onerror = () => ws?.close();
  };
  open();
  return () => { stop = true; ws?.close(); };
}

export async function postInvestigate(card_id: string,
  depth: "investigate" | "deep", workspace_brief: string):
  Promise<ResearchBrief> {
  const r = await fetch(`${API}/api/investigate`, { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ card_id, depth, workspace_brief }) });
  return r.json();
}
export async function getBriefs(card_id: string): Promise<ResearchBrief[]> {
  const r = await fetch(`${API}/api/briefs?card_id=${
    encodeURIComponent(card_id)}`);
  return (await r.json()).briefs;
}

/* ---- Phase 3: decision surfaces ---- */
export interface HeatRow { tenor: string;
  nodes: Record<string, { vol: number; d1: number; pct: number }>;
  provenance: string }
export interface SmileNode { node: string; vol: number; t5: number;
  p10: number; p90: number; pct: number }
export interface DriverSeries { card_id: string; pair: string;
  tenor: string; field: string;
  series: { date: string; value: number }[];
  detected_at: string; provenance: string }

export const getHeat = async (pair: string) =>
  (await fetch(`${API}/api/heat/${pair}`)).json() as
    Promise<{ pair: string; rows: HeatRow[]; history_days: number }>;
export const getSmile = async (pair: string, tenor: string) =>
  (await fetch(`${API}/api/smile/${pair}/${tenor}`)).json() as
    Promise<{ pair: string; tenor: string; nodes: SmileNode[];
      asof: string; t5_date: string; provenance: string }>;
export const getTerm = async (pair: string) =>
  (await fetch(`${API}/api/term/${pair}`)).json() as
    Promise<{ pair: string; field: string; provenance: string;
      series: Record<string, { tenor: string; atm: number }[]> }>;
export const getDriver = async (card_id: string) =>
  (await fetch(`${API}/api/driver`, { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ card_id }) })).json() as Promise<DriverSeries>;

/** Fire-and-forget surface telemetry (decision-latency dataset). */
export function postSurfaceOpen(surface: string, pair?: string,
  tenor?: string, card_id?: string): void {
  fetch(`${API}/api/telemetry/event`, { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event: "surface_open", card_id,
      payload: { surface, pair, tenor } }) }).catch(() => undefined);
}
