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
