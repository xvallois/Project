"""Phase 2 contract tests — the locked Analyst principles, enforced:

  - the Analyst cannot introduce numbers (gate kills the statement/brief)
  - all seven sections or rejection (structure IS the contract)
  - budget refusal is typed; triage reserve protected; zero-budget leaves
    the deterministic path untouched
  - institutional memory: ledger episodes flow into packs and cards with
    resolvable ledger: refs
  - end-to-end investigation through the seam persists a gated brief
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("VW_CONFIG",
                      "/home/claude/volwatch/config/settings.yaml")

from server.analyst.context import build_pack, ledger_memory
from server.analyst.engine import investigate, triage
from server.analyst.provider import AnalystProvider, StubProvider
from server.analyst.schema import (Evidence, Statement, gate_brief,
                                   gate_statement)
from server.db import Db
from server.provenance import ProvenanceVerifier

EV = {"E1": Evidence("E1", "z-score", "+2.31", "packet.signals[0].score"),
      "E2": Evidence("E2", "3M rr25", "-1.842 (p97)",
                     "store://vol/EURJPY/3M/rr25")}


def _sections(**over):
    base = {k: [Statement("qualitative read.", "analyst", [])]
            for k in ("finding", "supporting", "contradictory", "why_now",
                      "invalidation", "historical", "next_investigation")}
    base["finding"] = [Statement("Skew stretched at z +2.31.", "analyst",
                                 ["E1"])]
    base.update(over)
    return base


class TestNumericGate:
    def test_cited_number_passes(self) -> None:
        st = Statement("z-score sits at +2.31, two-sigma-plus.", "analyst",
                       ["E1"])
        assert gate_statement(st, EV) is None

    def test_rounded_quote_of_cited_number_passes(self) -> None:
        st = Statement("z of 2.3 on the driver.", "analyst", ["E1"])
        assert gate_statement(st, EV) is None

    def test_inventing_extra_precision_is_killed(self) -> None:
        st = Statement("z of 2.3174 precisely.", "analyst", ["E1"])
        assert "uncited" in gate_statement(st, EV)

    def test_uncited_number_is_killed(self) -> None:
        st = Statement("roughly 70% of such moves revert.", "analyst",
                       ["E1"])
        reason = gate_statement(st, EV)
        assert reason and "uncited" in reason

    def test_citing_unknown_evidence_is_killed(self) -> None:
        st = Statement("per E9 the move is large.", "analyst", ["E9"])
        assert "unknown evidence" in gate_statement(st, EV)

    def test_deterministic_statements_bypass_text_gate(self) -> None:
        st = Statement("engine: 3M rr25 = -1.842", "deterministic", [])
        assert gate_statement(st, EV) is None

    def test_missing_section_rejects_brief(self) -> None:
        secs = _sections()
        del secs["historical"]
        _, dropped, status = gate_brief(secs, EV)
        assert status == "rejected"
        assert any("missing section" in d for d in dropped)

    def test_fabrications_degrade_then_reject(self) -> None:
        bad = Statement("hit rate is 83% historically.", "analyst", [])
        secs = _sections(supporting=[bad])
        clean, dropped, status = gate_brief(secs, EV)
        assert status == "degraded" and len(dropped) == 1
        assert clean["supporting"] == []
        secs = _sections(supporting=[bad, bad, bad, bad])
        _, _, status = gate_brief(secs, EV)
        assert status == "rejected"

    def test_gutted_finding_rejects(self) -> None:
        secs = _sections(finding=[Statement("worth 4.5vp easily.",
                                            "analyst", [])])
        _, _, status = gate_brief(secs, EV)
        assert status == "rejected"


def _card(id_="skew_richcheap|EURJPY|3M 25d rr", pair="EURJPY"):
    now = "2026-06-11T08:00:00+00:00"
    return {"id": id_, "type": id_.split("|")[0], "pair": pair,
            "tenors": ["3M"], "headline": "3M RR z +2.3", "structure": "3M",
            "band": "WATCH",
            "confidence": {"absZ": 2.3, "persistedCycles": 2,
                           "dataQualityOk": True, "modelsAgree": True,
                           "backtestPrior": None},
            "findings": "skew stretched", "evidence": [
                {"label": "z-score", "value": "+2.31",
                 "provenance": "packet.signals[0].score"}],
            "supporting": [], "contradictions": [],
            "invalidation_criteria": ["|z| reverts inside ±1.0"],
            "similar_history_items": [], "similar_history_note": "",
            "status": "new", "created_at": now, "updated_at": now,
            "detected_at": now, "dismissal": None, "invalidation": None}


PACKET = {"signals": [{"score": 2.31}],
          "health": {"EURJPY": {"model_divergence_worst": {"volpts": 1.1}}}}


class TestLedgerMemory:
    @pytest.fixture()
    def db(self, tmp_path) -> Db:
        db = Db(tmp_path / "t.db")
        old = _card("skew_richcheap|EURJPY|3M old-episode")
        db.apply_cycle([old])
        b = db.blotter_add({"kind": "paper", "status": "open",
                            "pair": "EURJPY", "structure": "3M",
                            "direction": "sell",
                            "linked_opportunity_id": old["id"],
                            "entry_thesis": "t"})
        db.blotter_close(b["id"], 0.85, "converged")
        db.transition(old["id"], "acted")
        return db

    def test_pack_contains_episodes_and_funnel(self, db: Db) -> None:
        db.apply_cycle([_card()])
        pack = build_pack(_card(), db.all_cards(), PACKET, db, "")
        tags = [e["tag"] for e in pack["evidence"]]
        assert "ledger" in tags
        led = [e for e in pack["evidence"] if e["tag"] == "ledger"]
        assert any("+0.85vp" in e["value"] for e in led)
        assert all(e["provenance"].startswith("ledger:") for e in led)

    def test_ledger_refs_resolve_in_verifier(self, db: Db) -> None:
        keys = {f"ledger:card({c['id']})" for c in db.all_cards()}
        v = ProvenanceVerifier(PACKET, set(), keys)
        good = next(iter(keys))
        assert v.check_ref(good) is None
        assert v.check_ref("ledger:card(invented|XXX|1Y)") is not None


class TestBudgetDiscipline:
    @pytest.fixture()
    def db(self, tmp_path) -> Db:
        db = Db(tmp_path / "t.db")
        db.apply_cycle([_card()])
        return db

    def test_investigation_spends_and_refuses_typed(self, db: Db) -> None:
        stub = StubProvider()
        r = investigate(_card()["id"], "investigate", "", db, PACKET, stub)
        assert r["status"] in ("ok", "degraded")
        assert db.budget_state()["used"] == 3
        # burn to the reserve with deep dives
        while db.budget_spend("deep", 10)["ok"]:
            pass
        r = investigate(_card()["id"], "deep", "", db, PACKET, stub)
        assert r["refused"] == "reserve-protected"
        # triage still runs inside the reserve
        assert db.budget_spend("triage", 1)["ok"]

    def test_zero_budget_never_touches_deterministic_path(self,
                                                          db: Db) -> None:
        db.budget_state()                          # materialize today's row
        db._con.execute("UPDATE budget SET used=120")
        db._con.commit()
        assert triage(db, PACKET, StubProvider()) is None   # silent skip
        # feed lifecycle continues regardless
        db.apply_cycle([_card("skew_richcheap|GBPUSD|1M rr")])
        assert len(db.all_cards()) == 2


class FabricatingProvider(AnalystProvider):
    """Adversarial: smuggles invented numbers + drops a section."""
    name = "stub"

    def complete(self, depth, system, user):
        return json.dumps({
            "finding": [{"text": "Worth 4.5vp; 83% hit rate.",
                         "cites": []}],
            "supporting": [], "contradictory": [], "why_now": [],
            "invalidation": [], "next_investigation": []})  # no historical


class TestEndToEnd:
    def test_stub_investigation_persists_gated_brief(self, tmp_path) -> None:
        db = Db(tmp_path / "t.db")
        db.apply_cycle([_card()])
        out = investigate(_card()["id"], "investigate", "ECB week — EUR "
                          "event pricing first", db, PACKET, StubProvider())
        assert out["status"] in ("ok", "degraded")
        for sec in ("finding", "supporting", "contradictory", "why_now",
                    "invalidation", "historical", "next_investigation"):
            assert sec in out["sections"]
        for sec in out["sections"].values():
            for st in sec:
                assert st["kind"] == "analyst"
        assert db.briefs_for(_card()["id"])           # persisted
        ev = db.telemetry_summary()["counts"]
        assert ev.get("analyst_brief", 0) == 1

    def test_fabricating_provider_is_rejected(self, tmp_path) -> None:
        db = Db(tmp_path / "t.db")
        db.apply_cycle([_card()])
        out = investigate(_card()["id"], "investigate", "", db, PACKET,
                          FabricatingProvider())
        assert out["status"] == "rejected"
        assert any("missing section" in d or "uncited" in d
                   for d in out["dropped"])

    def test_triage_ranks_without_touching_bands(self, tmp_path) -> None:
        db = Db(tmp_path / "t.db")
        a, b = _card(), _card("skew_richcheap|GBPUSD|1M rr", "GBPUSD")
        db.apply_cycle([a, b])
        before = {c["id"]: (c["band"], c["status"])
                  for c in db.all_cards()}
        assert triage(db, PACKET, StubProvider()) is not None
        for c in db.all_cards():
            assert (c["band"], c["status"]) == before[c["id"]]
            assert "analyst_rank" in c       # alongside, never instead
