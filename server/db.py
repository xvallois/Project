"""SQLite persistence (stdlib) + server-side feed lifecycle + telemetry.

Three tables, one file, WAL mode, Alembic-shaped DDL (surrogate ids, ISO
timestamps, JSON only for genuinely schemaless payloads):

  cards     — feed state, survives restarts (a trading day, then forever)
  events    — TELEMETRY (Phase 1 §5): every lifecycle transition with ts,
              the funnel dataset the future Analyst trains against
  blotter   — the unified decision ledger (locked decision #4)

Lifecycle parity with the Phase-0 client engine (same rules, now
authoritative server-side): dedup by id, 12h dismissal cooldown overridden
by band escalation, disappearance-without-action => invalidated,
acted/watching sticky.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

COOLDOWN_S = 12 * 3600
BAND_RANK = {"SPECULATIVE": 0, "WATCH": 1, "ACTIONABLE": 2}

_DDL = """
CREATE TABLE IF NOT EXISTS cards (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, band TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  dismissed_at TEXT, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, ts TEXT NOT NULL, card_id TEXT,
  event TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS ix_events_card ON events(card_id);
CREATE TABLE IF NOT EXISTS briefs (
  brief_id TEXT PRIMARY KEY, card_id TEXT NOT NULL, depth TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_briefs_card ON briefs(card_id);
CREATE TABLE IF NOT EXISTS budget (
  day TEXT PRIMARY KEY, used INTEGER NOT NULL, carryover INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS blotter (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
  pair TEXT NOT NULL, structure TEXT NOT NULL, direction TEXT NOT NULL,
  linked_opportunity_id TEXT, entry_thesis TEXT, size TEXT,
  pnl_volpts REAL, pnl_ccy REAL, notes TEXT, post_mortem TEXT,
  opened_at TEXT NOT NULL, closed_at TEXT);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Db:
    def __init__(self, path: str | Path) -> None:
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.executescript(_DDL)
        self._con.row_factory = sqlite3.Row

    # ------------------------------------------------------------ events
    def record(self, event: str, card_id: str | None = None,
               payload: dict | None = None) -> None:
        self._con.execute(
            "INSERT INTO events VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), _now(), card_id, event,
             json.dumps(payload or {})))
        self._con.commit()

    def telemetry_summary(self) -> dict:
        rows = self._con.execute(
            "SELECT event, count(*) n FROM events GROUP BY event").fetchall()
        counts = {r["event"]: r["n"] for r in rows}
        outcomes = self._con.execute(
            "SELECT count(*) n, avg(pnl_volpts) avg_pnl FROM blotter "
            "WHERE status != 'open'").fetchone()
        return {"counts": counts,
                "funnel": {k: counts.get(k, 0) for k in
                           ("generated", "seen", "watching", "acted",
                            "dismissed", "invalidated")},
                "outcomes": {"closed": outcomes["n"],
                             "avg_pnl_volpts": outcomes["avg_pnl"]}}

    # ------------------------------------------------------------- cards
    def all_cards(self) -> list[dict]:
        rows = self._con.execute(
            "SELECT payload FROM cards ORDER BY updated_at DESC").fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def _put(self, c: dict) -> None:
        self._con.execute(
            "INSERT INTO cards VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO "
            "UPDATE SET status=excluded.status, band=excluded.band, "
            "updated_at=excluded.updated_at, "
            "dismissed_at=excluded.dismissed_at, payload=excluded.payload",
            (c["id"], c["status"], c["band"], c["created_at"],
             c["updated_at"],
             (c.get("dismissal") or {}).get("at"), json.dumps(c)))

    def apply_cycle(self, detected: list[dict],
                    band_fn=None) -> list[dict]:
        """Authoritative lifecycle merge; returns the changed cards."""
        now = _now()
        existing = {c["id"]: c for c in self.all_cards()}
        seen, changed = set(), []

        for d in detected:
            seen.add(d["id"])
            prev = existing.get(d["id"])
            if prev is None:
                self._put(d)
                self.record("generated", d["id"],
                            {"band": d["band"], "type": d["type"]})
                changed.append(d)
                continue
            if prev["status"] == "dismissed" and prev.get("dismissal"):
                age = (datetime.fromisoformat(now)
                       - datetime.fromisoformat(prev["dismissal"]["at"])
                       ).total_seconds()
                escalated = BAND_RANK[d["band"]] > BAND_RANK[prev["band"]]
                if age < COOLDOWN_S and not escalated:
                    continue
            conf = {**d["confidence"],
                    "persistedCycles": prev["confidence"].get(
                        "persistedCycles", 1) + 1}
            # persistence FEEDS banding (replay-found bug: bands were
            # frozen at detect-time persisted=1 forever)
            band = band_fn(conf) if band_fn else d["band"]
            merged = {**d, "band": band,
                      "created_at": prev["created_at"],
                      "detected_at": prev.get("detected_at",
                                              prev["created_at"]),
                      "updated_at": now,
                      "confidence": conf,
                      "status": prev["status"]
                      if prev["status"] in ("watching", "acted")
                      else "new" if prev["status"] == "dismissed"
                      else prev["status"]}
            self._put(merged)
            self.record("updated", merged["id"], {"band": merged["band"]})
            changed.append(merged)

        for c in existing.values():
            if c["id"] in seen:
                if c.get("_missing"):
                    c["_missing"] = 0          # came back: clear debounce
                    self._put(c)
                continue
            if c["status"] not in ("new", "seen", "watching"):
                continue
            # debounce: one missing cycle is noise, two is a closed event
            c["_missing"] = c.get("_missing", 0) + 1
            if c["_missing"] < 2:
                self._put(c)
                continue
            c.update(status="invalidated", updated_at=now,
                     invalidation={"at": now,
                                   "outcome": "closed without action"})
            self._put(c)
            self.record("invalidated", c["id"])
            changed.append(c)
        self._con.commit()
        return changed

    def transition(self, card_id: str, status: str,
                   dismissal: dict | None = None) -> dict | None:
        cards = {c["id"]: c for c in self.all_cards()}
        c = cards.get(card_id)
        if c is None:
            return None
        c.update(status=status, updated_at=_now())
        if status == "dismissed" and dismissal:
            c["dismissal"] = {**dismissal, "at": _now()}
        self._put(c)
        self.record(status, card_id, dismissal or {})
        self._con.commit()
        return c

    # ------------------------------------------------ decision metrics
    def decision_metrics(self) -> dict:
        """signal_detected→surfaced→investigated→blottered→closed.
        'generated' IS surfaced (same cycle, by construction)."""
        rows = self._con.execute(
            "SELECT card_id, event, ts FROM events WHERE card_id IS NOT "
            "NULL ORDER BY ts").fetchall()
        first: dict[str, dict[str, str]] = {}
        for r in rows:
            first.setdefault(r["card_id"], {}).setdefault(r["event"],
                                                          r["ts"])
        from datetime import datetime
        def lat(a, b):
            out = []
            for ev in first.values():
                if a in ev and b in ev:
                    out.append((datetime.fromisoformat(ev[b])
                                - datetime.fromisoformat(ev[a])
                                ).total_seconds())
            out.sort()
            return round(out[len(out) // 2], 1) if out else None
        gen = [c for c, ev in first.items() if "generated" in ev]
        seen = [c for c in gen if "seen" in first[c]
                or "watching" in first[c]]
        inv_cards = [c for c in gen if "analyst_brief" in first[c]]
        blot = [c for c in gen if "blotter_open" in first[c]]
        ignored = [c for c in gen if "invalidated" in first[c]
                   and c not in seen]
        abst = sum(1 for r in rows if r["event"] == "analyst_abstain")
        briefs = sum(1 for r in rows if r["event"] == "analyst_brief")
        surf = self._con.execute(
            "SELECT count(*) n FROM events WHERE event='surface_open'"
        ).fetchone()["n"]
        return {
            "median_investigate_latency_s": lat("generated",
                                                "analyst_brief"),
            "median_decision_latency_s": lat("generated", "blotter_open"),
            "median_close_latency_s": lat("blotter_open", "blotter_close"),
            "generated": len(gen), "seen": len(seen),
            "ignored": len(ignored), "acted": len(blot),
            "investigate_rate": round(len(inv_cards) / len(gen), 3)
            if gen else None,
            "blotter_rate": round(len(blot) / len(gen), 3) if gen else None,
            "investigation_conversion": round(len(blot) / len(inv_cards),
                                              3) if inv_cards else None,
            "analyst_abstain_rate": round(abst / (abst + briefs), 3)
            if (abst + briefs) else None,
            "surface_opens": surf,
        }

    # ------------------------------------------------------------- briefs
    def brief_add(self, brief: dict) -> None:
        self._con.execute(
            "INSERT INTO briefs VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), brief["card_id"], brief["depth"],
             brief["status"], brief["created_at"], json.dumps(brief)))
        self._con.commit()

    def briefs_for(self, card_id: str) -> list[dict]:
        return [json.loads(r["payload"]) for r in self._con.execute(
            "SELECT payload FROM briefs WHERE card_id=? "
            "ORDER BY created_at DESC", (card_id,)).fetchall()]

    def set_analyst_rank(self, card_id: str, rank: int, note: str) -> None:
        cards = {c["id"]: c for c in self.all_cards()}
        c = cards.get(card_id)
        if c is None:
            return
        c["analyst_rank"], c["analyst_note"] = rank, note
        self._put(c)
        self._con.commit()

    # ------------------------------------------------------------- budget
    # Server-side mirror of the locked Phase-0 rules: 100u/day, 20%
    # carryover cap, 12u triage reserve deep spends can't touch.
    BASE_DAILY, CARRY_CAP, TRIAGE_RESERVE = 100, 20, 12
    COST = {"triage": 1, "analysis": 3, "deep": 10}

    def _budget_row(self) -> dict:
        day = _now()[:10]
        row = self._con.execute(
            "SELECT * FROM budget WHERE day=?", (day,)).fetchone()
        if row:
            return dict(row)
        prev = self._con.execute(
            "SELECT * FROM budget ORDER BY day DESC LIMIT 1").fetchone()
        carry = 0
        if prev:
            carry = min(self.BASE_DAILY + prev["carryover"] - prev["used"],
                        self.CARRY_CAP)
            carry = max(carry, 0)
        self._con.execute("INSERT INTO budget VALUES (?,?,?)",
                          (day, 0, carry))
        self._con.commit()
        return {"day": day, "used": 0, "carryover": carry}

    def budget_state(self) -> dict:
        r = self._budget_row()
        total = self.BASE_DAILY + r["carryover"]
        return {**r, "total": total, "remaining": total - r["used"],
                "triage_reserve": self.TRIAGE_RESERVE}

    def budget_spend(self, tier: str, units: int) -> dict:
        st = self.budget_state()
        if units > st["remaining"]:
            return {"ok": False, "reason": "insufficient", "state": st}
        if tier != "triage" and st["remaining"] - units < self.TRIAGE_RESERVE:
            return {"ok": False, "reason": "reserve-protected", "state": st}
        self._con.execute("UPDATE budget SET used=used+? WHERE day=?",
                          (units, st["day"]))
        self._con.commit()
        return {"ok": True, "state": self.budget_state()}

    # ------------------------------------------------------------ blotter
    def blotter_add(self, e: dict) -> dict:
        e = {**e, "id": str(uuid.uuid4()), "opened_at": _now()}
        self._con.execute(
            "INSERT INTO blotter VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (e["id"], e["kind"], e["status"], e["pair"], e["structure"],
             e["direction"], e.get("linked_opportunity_id"),
             e.get("entry_thesis"), e.get("size"), e.get("pnl_volpts"),
             e.get("pnl_ccy"), e.get("notes"), e.get("post_mortem"),
             e["opened_at"], e.get("closed_at")))
        self._con.commit()
        self.record("blotter_open", e.get("linked_opportunity_id"),
                    {"blotter_id": e["id"], "kind": e["kind"]})
        return e

    def blotter_close(self, bid: str, pnl_volpts: float,
                      notes: str) -> None:
        self._con.execute(
            "UPDATE blotter SET status='closed', pnl_volpts=?, notes=?, "
            "closed_at=? WHERE id=?", (pnl_volpts, notes, _now(), bid))
        row = self._con.execute(
            "SELECT linked_opportunity_id FROM blotter WHERE id=?",
            (bid,)).fetchone()
        self._con.commit()
        self.record("blotter_close",
                    row["linked_opportunity_id"] if row else None,
                    {"blotter_id": bid, "pnl_volpts": pnl_volpts})

    def blotter_all(self) -> list[dict]:
        return [dict(r) for r in self._con.execute(
            "SELECT * FROM blotter ORDER BY opened_at DESC").fetchall()]
