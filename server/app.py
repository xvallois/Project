"""volwatch workstation sidecar (Phase 1).

Imports the engine DIRECTLY (zero IPC inside analytics). One asyncio loop
drives snaps + cycles; detectors run on the real packet/store; every card
passes the provenance verifier or is rejected; the WS fan-out pushes
snapshot+delta with seq numbers per topic.

Provider selection mirrors the engine CLI: VW_PROVIDER=mock|bbg|bql.
On the desk: bbg. In this container: mock (identical code path).

Run:  uvicorn server.app:app --port 8787
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from server.analyst.context import ledger_memory
from server.analyst.engine import investigate as run_investigation
from server.analyst.engine import triage as run_triage
from server.analyst.provider import AnthropicProvider, StubProvider
from server.db import Db
from server.detectors import detect
from server.provenance import ProvenanceVerifier

from volwatch.ai.context import assemble_packet
from volwatch.config import load_settings
from volwatch.data.pipeline import SnapPipeline
from volwatch.data.store import ParquetStore
from volwatch.signals.engine import SignalEngine, build_context

log = logging.getLogger("sidecar")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

SNAP_S = float(os.environ.get("VW_SNAP_S", "20"))
CYCLE_EVERY = int(os.environ.get("VW_CYCLE_EVERY", "3"))   # cycles per N snaps
SEED_DAYS = int(os.environ.get("VW_SEED_DAYS", "120"))


# ---------------------------------------------------------------- ws hub
class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._seq: dict[str, int] = {}
        self.snapshots: dict[str, dict] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        for topic, data in self.snapshots.items():       # resync on connect
            await ws.send_text(json.dumps(self._env(topic, "snapshot", data)))

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    def _env(self, topic: str, type_: str, data: dict) -> dict:
        return {"topic": topic, "type": type_, "seq": self._seq.get(topic, 0),
                "ts": datetime.now(timezone.utc).isoformat(), "data": data}

    async def publish(self, topic: str, data: dict) -> None:
        self._seq[topic] = self._seq.get(topic, 0) + 1
        self.snapshots[topic] = data
        msg = json.dumps(self._env(topic, "delta", data))
        dead = []
        for c in self._clients:
            try:
                await c.send_text(msg)
            except Exception:
                dead.append(c)
        for c in dead:
            self.disconnect(c)


hub = Hub()


# ------------------------------------------------------------- the engine
class EngineState:
    analyst = None                # AnalystProvider
    settings = None
    store: ParquetStore | None = None
    pipeline: SnapPipeline | None = None
    db: Db | None = None
    packet: dict = {}
    last_snap: str = ""
    last_cycle: str = ""
    cycle_ms: float = 0.0
    rejected_cards: int = 0
    snaps: int = 0


S = EngineState()


def _store_fields(store: ParquetStore) -> set[tuple[str, str, str]]:
    df = store.query("SELECT DISTINCT pair, tenor FROM vol")
    return {(r.pair, r.tenor, f) for r in df.itertuples()
            for f in ("atm", "rr25", "bf25")}


def run_cycle_sync() -> list[dict]:
    """One full analytic cycle on the live engine. Returns changed cards."""
    t0 = datetime.now()
    snap, _report = S.pipeline.run_once()  # validated + stored
    ctx = build_context(S.settings, snap, S.store, S.pipeline.provider)
    signals = SignalEngine().run(ctx)
    S.packet = json.loads(assemble_packet(ctx, signals).to_json())

    live = {c["id"] for c in S.db.all_cards()
            if c["status"] in ("new", "seen", "watching")}
    cards = [c.to_dict()
             for c in detect(S.packet, S.store, S.settings, live_ids=live)]
    ledger_keys = {f"ledger:card({c['id']})" for c in S.db.all_cards()}
    ledger_keys |= {f"ledger:funnel({c['id'].split('|')[0]})"
                    for c in S.db.all_cards()}
    verifier = ProvenanceVerifier(S.packet, _store_fields(S.store),
                                  ledger_keys)
    clean = []
    for c in cards:
        violations = verifier.verify_card(c)
        if violations:
            S.rejected_cards += 1
            S.db.record("card_rejected", c["id"],
                        {"violations": [v.reason for v in violations]})
            log.error("PROVENANCE REJECT %s: %s", c["id"],
                      violations[0].reason)
            continue
        clean.append(c)
    # deterministic institutional memory: real ledger episodes replace
    # the placeholder similar-history on every card that has priors
    for c in clean:
        eps = ledger_memory(S.db, c)
        if eps:
            c["similar_history_items"] = [
                {"label": f"prior {e['id']}",
                 "value": f"{e['status']} → {e['outcome']}",
                 "provenance": f"ledger:card({e['id']})"} for e in eps[:4]]
            c["similar_history_note"] = "from the decision ledger"
    changed = S.db.apply_cycle(clean)
    if S.analyst is not None:
        try:
            run_triage(S.db, S.packet, S.analyst)
        except Exception:
            log.exception("triage failed; feed unaffected")
    S.last_cycle = datetime.now(timezone.utc).isoformat()
    S.cycle_ms = (datetime.now() - t0).total_seconds() * 1000
    return changed


async def engine_loop() -> None:
    while True:
        try:
            S.snaps += 1
            if S.snaps % CYCLE_EVERY == 1:
                changed = await asyncio.to_thread(run_cycle_sync)
                await hub.publish("feed", {"cards": S.db.all_cards(),
                                           "changed": [c["id"] for c in
                                                       changed]})
            else:
                await asyncio.to_thread(S.pipeline.run_once)  # stores itself
            S.last_snap = datetime.now(timezone.utc).isoformat()
            await hub.publish("health", health_payload())
        except Exception:
            log.exception("engine loop iteration failed; continuing")
        await asyncio.sleep(SNAP_S)


def health_payload() -> dict:
    return {"last_snap": S.last_snap, "last_cycle": S.last_cycle,
            "cycle_ms": round(S.cycle_ms, 1),
            "provider": os.environ.get("VW_PROVIDER", "mock"),
            "rejected_cards": S.rejected_cards,
            "analyst": getattr(S.analyst, "name", None),
            "budget": S.db.budget_state() if S.db else {},
            "engine_health": S.packet.get("health", {}),
            "telemetry": S.db.telemetry_summary() if S.db else {}}


# ----------------------------------------------------------------- app
@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Path(os.environ.get(
        "VW_CONFIG", "/home/claude/volwatch/config/settings.yaml"))
    root = Path(os.environ.get("VW_DATA", "./sidecar-data")).resolve()
    # the engine resolves config/signals.yaml & config/events.csv from CWD
    os.chdir(cfg.parent.parent)
    S.settings = load_settings(str(cfg))
    S.store = ParquetStore(root / "parquet-root", root / "latest")
    S.db = Db(root / "workstation.db")

    provider_name = os.environ.get("VW_PROVIDER", "mock")
    if provider_name == "bbg":
        from volwatch.data.bloomberg import BloombergProvider
        provider = BloombergProvider()
    elif provider_name == "bql":
        from volwatch.data.bql_provider import BqlProvider
        provider = BqlProvider()
    else:
        from datetime import timedelta
        from volwatch.core.models import utcnow
        from volwatch.data.provider import MockProvider
        # seed history so percentiles mean something on first boot
        existing = S.store.query("SELECT count(*) n FROM vol")["n"][0] \
            if (root / "parquet-root" / "parquet" / "vol").exists() else 0
        provider = MockProvider(seed=11)
        if existing == 0:
            log.info("seeding %d days of mock history...", SEED_DAYS)
            day = {"i": 0}
            seeder = MockProvider(
                seed=11, clock=lambda: utcnow() - timedelta(
                    days=SEED_DAYS - day["i"]))
            for i in range(SEED_DAYS):
                day["i"] = i
                S.store.write_snapshot(seeder.snapshot(
                    S.settings.universe.all_pairs, S.settings.universe.tenors))
            log.info("seeded.")
    S.pipeline = SnapPipeline(S.settings, provider, store=S.store)

    mode = os.environ.get("VW_ANALYST", "auto")
    if mode == "claude" or (mode == "auto"
                            and os.environ.get("ANTHROPIC_API_KEY")):
        S.analyst = AnthropicProvider()
        log.info("analyst: Claude (live)")
    elif mode in ("stub", "auto"):
        S.analyst = StubProvider()
        log.info("analyst: stub (no ANTHROPIC_API_KEY — set VW_ANALYST="
                 "claude + key on the desk)")
    else:
        S.analyst = None
        log.info("analyst: disabled")

    await asyncio.to_thread(run_cycle_sync)          # first cycle before serve
    hub.snapshots["feed"] = {"cards": S.db.all_cards(), "changed": []}
    hub.snapshots["health"] = health_payload()
    task = asyncio.create_task(engine_loop())
    yield
    task.cancel()


app = FastAPI(title="volwatch sidecar", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/api/feed")
def get_feed():
    return {"cards": S.db.all_cards()}


class Transition(BaseModel):
    id: str                       # in the body: card ids contain '/' and '|'
    status: str
    reason: str | None = None
    note: str | None = None


@app.post("/api/feed/transition")
def post_transition(t: Transition):
    dismissal = ({"reason": t.reason, "note": t.note}
                 if t.status == "dismissed" else None)
    card = S.db.transition(t.id, t.status, dismissal)
    return {"ok": card is not None, "card": card}


class BlotterIn(BaseModel):
    kind: str = "idea"
    status: str = "open"
    pair: str
    structure: str
    direction: str
    linked_opportunity_id: str | None = None
    entry_thesis: str | None = None
    size: str | None = None


@app.get("/api/blotter")
def get_blotter():
    return {"rows": S.db.blotter_all()}


@app.post("/api/blotter")
def post_blotter(e: BlotterIn):
    return S.db.blotter_add(e.model_dump())


class BlotterClose(BaseModel):
    pnl_volpts: float
    notes: str = ""


@app.post("/api/blotter/{bid}/close")
def post_blotter_close(bid: str, body: BlotterClose):
    S.db.blotter_close(bid, body.pnl_volpts, body.notes)
    return {"ok": True}


@app.get("/api/health")
def get_health():
    return health_payload()


class InvestigateIn(BaseModel):
    card_id: str
    depth: str = "investigate"           # investigate | deep
    workspace_brief: str = ""


@app.post("/api/investigate")
async def post_investigate(body: InvestigateIn):
    if S.analyst is None:
        return {"error": "analyst disabled"}
    if body.depth not in ("investigate", "deep"):
        return {"error": "bad depth"}
    brief = await asyncio.to_thread(
        run_investigation, body.card_id, body.depth, body.workspace_brief,
        S.db, S.packet, S.analyst)
    await hub.publish("brief", brief)
    return brief


@app.get("/api/briefs")
def get_briefs(card_id: str):
    return {"briefs": S.db.briefs_for(card_id)}


@app.post("/api/postmortem/{bid}")
async def post_postmortem(bid: str):
    """Draft a post-mortem for a closed blotter entry — same 7-section
    structure, same gate; the ledger entry is the evidence."""
    if S.analyst is None:
        return {"error": "analyst disabled"}
    row = next((r for r in S.db.blotter_all() if r["id"] == bid), None)
    if row is None or not row.get("linked_opportunity_id"):
        return {"error": "no linked opportunity for this entry"}
    brief = await asyncio.to_thread(
        run_investigation, row["linked_opportunity_id"], "investigate",
        f"POST-MORTEM of a closed {row['kind']} position: outcome "
        f"{row.get('pnl_volpts')}vp, notes: {row.get('notes') or '—'}. "
        "Focus the note on what the entry thesis got right or wrong.",
        S.db, S.packet, S.analyst)
    await hub.publish("brief", brief)
    return brief


@app.get("/api/telemetry/summary")
def get_telemetry():
    return S.db.telemetry_summary()


@app.get("/api/packet")
def get_packet():
    return S.packet


@app.get("/api/surface/{pair}")
def get_surface(pair: str):
    df = S.store.query(
        f"SELECT tenor, \"asof\", atm, rr25, bf25 FROM vol "
        f"WHERE pair='{pair}' AND status=0")
    if df.empty:
        return {"pair": pair, "history": {}}
    import pandas as pd
    df["date"] = pd.to_datetime(df["asof"]).dt.date.astype(str)
    daily = (df.sort_values("asof")
             .groupby(["tenor", "date"], as_index=False).last())
    out = {t: g[["date", "atm", "rr25", "bf25"]].to_dict("records")
           for t, g in daily.groupby("tenor")}
    return {"pair": pair, "history": out,
            "provenance": f"store://vol/{pair}/<tenor>/<field>"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()        # client pings; topics are pushed
    except WebSocketDisconnect:
        hub.disconnect(ws)
