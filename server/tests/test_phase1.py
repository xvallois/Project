"""Phase 1 server contract tests. The themes the user locked:
provenance is structural (poisoned cards REJECTED), lifecycle parity with
the Phase-0 client rules, telemetry records the whole funnel, the API
serves real engine analytics.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("VW_CONFIG", str(
    Path(__file__).resolve().parents[2] / "engine/config/settings.yaml"))

from server.db import Db
from server.detectors import band_for, detect
from server.provenance import ProvenanceVerifier, resolve_packet_path


# ----------------------------------------------------------- provenance
class TestProvenance:
    PACKET = {"signals": [{"score": 2.31, "edge_estimate_volpts": 0.4}],
              "health": {"EURJPY": {"model_divergence_worst":
                                    {"volpts": 1.2}}}}
    FIELDS = {("EURJPY", "3M", "rr25"), ("EURJPY", "3M", "atm")}

    def v(self) -> ProvenanceVerifier:
        return ProvenanceVerifier(self.PACKET, self.FIELDS)

    def test_packet_paths_resolve_including_indices(self) -> None:
        assert resolve_packet_path(self.PACKET,
                                   "packet.signals[0].score") == 2.31
        assert self.v().check_ref("packet.signals[0].score") is None
        assert self.v().check_ref(
            "packet.health.EURJPY.model_divergence_worst.volpts") is None

    def test_unresolvable_refs_are_violations(self) -> None:
        assert self.v().check_ref("packet.signals[9].score") is not None
        assert self.v().check_ref("packet.nope.nothing") is not None
        assert self.v().check_ref(
            "store://vol/EURJPY/3M/badfield") is not None
        assert self.v().check_ref(
            "store://vol/USDMXN/3M/atm") is not None     # not in store
        assert self.v().check_ref("vibes://trust-me") is not None

    def test_derived_requires_resolvable_inputs(self) -> None:
        ok = "derived:percentile(store://vol/EURJPY/3M/rr25)"
        bad = "derived:percentile(store://vol/USDMXN/3M/atm)"
        none = "derived:magic()"
        assert self.v().check_ref(ok) is None
        assert self.v().check_ref(bad) is not None
        assert self.v().check_ref(none) is not None

    def test_poisoned_card_is_rejected_whole(self) -> None:
        card = {"id": "x", "evidence": [
            {"label": "z", "value": "2.3",
             "provenance": "packet.signals[0].score"},
            {"label": "made up", "value": "9.9",
             "provenance": "packet.signals[3].score"}],
            "supporting": [], "contradictions": [],
            "similar_history_items": []}
        violations = self.v().verify_card(card)
        assert len(violations) == 1
        assert "unresolvable" in violations[0].reason

    def test_numeric_item_without_ref_is_a_violation(self) -> None:
        card = {"id": "x", "evidence": [{"label": "z", "value": "2.3"}],
                "supporting": [], "contradictions": [],
                "similar_history_items": []}
        assert self.v().verify_card(card)


# ----------------------------------------------------------------- bands
class TestBanding:
    def test_numpy_scalar_inputs_band_identically(self) -> None:
        """Regression for the replay-found production bug: np.float64 z +
        np.bool_ arithmetic (logical OR) saturated scores at 1."""
        import numpy as np
        for z in (1.6, 2.07, 2.78, 4.0):
            assert band_for(np.float64(z), 1, True, True, False) == \
                band_for(z, 1, True, True, False)
        assert band_for(np.float64(2.07), 1, True, True, False) == "WATCH"

    def test_dq_flags_never_actionable(self) -> None:
        assert band_for(9.0, 9, dq_ok=False, models_agree=True,
                        prior_ok=True) == "SPECULATIVE"

    def test_full_evidence_actionable(self) -> None:
        assert band_for(3.0, 3, True, True, True) == "ACTIONABLE"

    def test_thin_evidence_speculative(self) -> None:
        assert band_for(1.2, 1, True, False, False) == "SPECULATIVE"


# ---------------------------------------------------------- db lifecycle
def _card(id_="t|EURJPY|3M", band="WATCH", status="new") -> dict:
    now = "2026-06-11T08:00:00+00:00"
    return {"id": id_, "type": "t", "pair": "EURJPY", "tenors": ["3M"],
            "headline": "h", "structure": "3M", "band": band,
            "confidence": {"absZ": 2.0, "persistedCycles": 1,
                           "dataQualityOk": True, "modelsAgree": True,
                           "backtestPrior": None},
            "findings": "", "evidence": [], "supporting": [],
            "contradictions": [], "invalidation_criteria": [],
            "similar_history_items": [], "similar_history_note": "",
            "status": status, "created_at": now, "updated_at": now,
            "detected_at": now, "dismissal": None, "invalidation": None}


class TestDbLifecycle:
    @pytest.fixture()
    def db(self, tmp_path) -> Db:
        return Db(tmp_path / "t.db")

    def test_dedup_and_persistence_counter(self, db: Db) -> None:
        db.apply_cycle([_card()])
        db.apply_cycle([_card()])
        cards = db.all_cards()
        assert len(cards) == 1
        assert cards[0]["confidence"]["persistedCycles"] == 2

    def test_persistence_feeds_banding(self, db: Db) -> None:
        from server.detectors import band_for
        fn = lambda c: band_for(c["absZ"], c["persistedCycles"],
                                c["dataQualityOk"], c["modelsAgree"], False)
        strong = _card()
        strong["confidence"]["absZ"] = 2.6          # z2.6 + agree = WATCH@1
        db.apply_cycle([strong], band_fn=fn)
        assert db.all_cards()[0]["band"] == "WATCH"
        db.apply_cycle([strong], band_fn=fn)        # persisted=2 → +1
        assert db.all_cards()[0]["band"] == "ACTIONABLE"

    def test_dismiss_cooldown_and_escalation_override(self, db: Db) -> None:
        db.apply_cycle([_card()])
        db.transition("t|EURJPY|3M", "dismissed",
                      {"reason": "Too low conviction"})
        db.apply_cycle([_card()])                       # inside cooldown
        assert db.all_cards()[0]["status"] == "dismissed"
        db.apply_cycle([_card(band="ACTIONABLE")])      # escalation
        assert db.all_cards()[0]["status"] == "new"

    def test_disappearance_invalidates_and_sticky_acted(self, db: Db) -> None:
        db.apply_cycle([_card(), _card("u|USDJPY|9M")])
        db.transition("u|USDJPY|9M", "acted")
        db.apply_cycle([])            # missing #1: debounced, still live
        assert {c["status"] for c in db.all_cards()} >= {"new"}
        db.apply_cycle([])            # missing #2: now a real closure
        by_id = {c["id"]: c for c in db.all_cards()}
        assert by_id["t|EURJPY|3M"]["status"] == "invalidated"
        assert by_id["u|USDJPY|9M"]["status"] == "acted"   # never invalidated

    def test_one_cycle_blip_does_not_invalidate(self, db: Db) -> None:
        db.apply_cycle([_card()])
        db.apply_cycle([])                       # blip
        db.apply_cycle([_card()])                # back
        c = db.all_cards()[0]
        assert c["status"] == "new"
        assert c.get("_missing", 0) == 0

    def test_telemetry_funnel_records_everything(self, db: Db) -> None:
        db.apply_cycle([_card()])
        db.transition("t|EURJPY|3M", "seen")
        db.transition("t|EURJPY|3M", "watching")
        b = db.blotter_add({"kind": "idea", "status": "open",
                            "pair": "EURJPY", "structure": "3M RR",
                            "direction": "sell_skew",
                            "linked_opportunity_id": "t|EURJPY|3M",
                            "entry_thesis": "frozen"})
        db.blotter_close(b["id"], -0.4, "took profit early")
        s = db.telemetry_summary()
        for k in ("generated", "seen", "watching",
                  "blotter_open", "blotter_close"):
            assert s["counts"].get(k, 0) >= 1, k
        assert s["outcomes"]["closed"] == 1
        assert s["outcomes"]["avg_pnl_volpts"] == pytest.approx(-0.4)

    def test_blotter_provenance_chain(self, db: Db) -> None:
        db.apply_cycle([_card()])
        db.blotter_add({"kind": "paper", "status": "open", "pair": "EURJPY",
                        "structure": "3M RR", "direction": "sell",
                        "linked_opportunity_id": "t|EURJPY|3M",
                        "entry_thesis": "z=2.0 at entry"})
        row = db.blotter_all()[0]
        assert row["linked_opportunity_id"] == "t|EURJPY|3M"
        assert "z=2.0" in row["entry_thesis"]


# ----------------------------------------------- live engine integration
class TestLiveEngine:
    """detect() over a REAL engine cycle (mock provider, identical path)."""

    @pytest.fixture(scope="class")
    def cycle(self, tmp_path_factory):
        from datetime import timedelta
        from volwatch.ai.context import assemble_packet
        from volwatch.config import load_settings
        from volwatch.core.models import utcnow
        from volwatch.data.provider import MockProvider
        from volwatch.data.store import ParquetStore
        from volwatch.signals.engine import SignalEngine, build_context

        tmp = tmp_path_factory.mktemp("live")
        os.chdir(Path(os.environ["VW_CONFIG"]).parent.parent)
        settings = load_settings(os.environ["VW_CONFIG"])
        settings = settings.model_copy(update={
            "universe": settings.universe.model_copy(update={
                "pairs": ["EURUSD", "USDJPY"], "cross_pairs": []})})
        store = ParquetStore(tmp / "d", tmp / "l")
        day = {"i": 0}
        p = MockProvider(seed=5, clock=lambda: utcnow()
                         - timedelta(days=60 - day["i"]))
        for i in range(60):
            day["i"] = i
            store.write_snapshot(p.snapshot(["EURUSD", "USDJPY"],
                                            settings.universe.tenors))
        live = MockProvider(seed=5)
        snap = live.snapshot(["EURUSD", "USDJPY"], settings.universe.tenors)
        store.write_snapshot(snap)
        import json as _json
        ctx = build_context(settings, snap, store, live)
        packet = _json.loads(
            assemble_packet(ctx, SignalEngine().run(ctx)).to_json())
        return packet, store, settings

    def test_cards_built_and_all_pass_provenance(self, cycle) -> None:
        from server.app import _store_fields
        packet, store, settings = cycle
        cards = [c.to_dict() for c in detect(packet, store, settings)]
        assert cards, "real cycle produced no observations at all"
        verifier = ProvenanceVerifier(packet, _store_fields(store))
        for c in cards:
            assert verifier.verify_card(c) == [], c["id"]

    def test_cards_are_analyst_shaped(self, cycle) -> None:
        packet, store, settings = cycle
        for c in (c.to_dict() for c in detect(packet, store, settings)):
            for key in ("findings", "evidence", "supporting",
                        "contradictions", "invalidation_criteria",
                        "similar_history_items", "confidence", "band",
                        "detected_at"):
                assert key in c, key
            assert c["invalidation_criteria"], "must state what kills it"
            for item in c["evidence"]:
                assert item["provenance"], "numeric without ref"


class TestFeedHygiene:
    """Phase 1 feed-quality fixes: clustering + hysteresis."""

    def test_broad_drift_clusters_to_one_card(self, tmp_path) -> None:
        import numpy as np, pandas as pd
        from unittest.mock import MagicMock
        n_days = 60
        dates = pd.date_range("2026-01-01", periods=n_days, freq="D")
        rows = []
        for tenor in ("1W", "1M", "3M", "6M"):
            vals = np.linspace(8, 9, n_days)
            vals[-1] = 12.0                      # all four breach p100
            for d, v in zip(dates, vals):
                rows.append(dict(pair="AUDUSD", tenor=tenor,
                                 asof=d.isoformat(),
                                 atm=v, rr25=-0.5, bf25=0.2))
        store = MagicMock()
        store.query.return_value = pd.DataFrame(rows)
        cards = [c.to_dict() for c in
                 detect({"signals": [], "health": {}}, store, None)]
        atm = [c for c in cards if "ATM" in c["type"]
               or c["type"].startswith("SURFACE")]
        assert len(atm) == 1
        assert atm[0]["type"] == "SURFACE_RICH"
        assert len(atm[0]["tenors"]) == 4
        assert "single driver" in [i["label"]
                                   for i in atm[0]["contradictions"]]

    def test_hysteresis_holds_a_live_card_at_p92(self, tmp_path) -> None:
        import numpy as np, pandas as pd
        from unittest.mock import MagicMock
        def frame(last):
            vals = list(np.linspace(-1, 1, 59)) + [last]
            dates = pd.date_range("2026-01-01", periods=60, freq="D")
            return pd.DataFrame([dict(pair="EURJPY", tenor="3M",
                asof=d.isoformat(), atm=8.0, rr25=v, bf25=0.2)
                for d, v in zip(dates, vals)])
        store = MagicMock()
        # p92-ish value: above 90th pct of the ramp but below 95th
        store.query.return_value = frame(0.87)
        none_live = detect({"signals": [], "health": {}}, store, None)
        assert not any(c.id == "SKEW_PCTILE|EURJPY|3M" for c in none_live)
        held = detect({"signals": [], "health": {}}, store, None,
                      live_ids={"SKEW_PCTILE|EURJPY|3M"})
        assert any(c.id == "SKEW_PCTILE|EURJPY|3M" for c in held)
