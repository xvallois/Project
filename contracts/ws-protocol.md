# WS topic protocol — v1

One socket, `GET /ws`. Server pushes; client text frames are ignored
(keepalive only).

Envelope:
```json
{"topic":"feed|health|brief","type":"snapshot|delta","seq":42,
 "ts":"ISO-8601","data":{}}
```
- per-topic monotonically increasing `seq`
- on connect: a `snapshot` per known topic
- client rule: if a `delta` arrives with `seq > last+1` → REST resync
  (`GET /api/feed`) — implemented in `frontend/src/api/client.ts`
- `feed.data = {cards: Card[], changed: [ids]}` (full list today; the
  envelope already permits true deltas later — ROADMAP phase 3)
- `brief.data = ResearchBrief`
