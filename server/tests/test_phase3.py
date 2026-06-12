"""Phase 3 — decision surfaces: server-computed, provenance-carrying."""
from __future__ import annotations
import os, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("VW_CONFIG",
                      "/home/claude/volwatch/config/settings.yaml")
from server.surfaces import driver, heat, node_vol, smile, term


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    from datetime import timedelta
    from volwatch.config import load_settings
    from volwatch.core.models import utcnow
    from volwatch.data.provider import MockProvider
    from volwatch.data.store import ParquetStore
    os.chdir(Path(os.environ["VW_CONFIG"]).parent.parent)
    settings = load_settings(os.environ["VW_CONFIG"])
    tmp = tmp_path_factory.mktemp("surf")
    st = ParquetStore(tmp / "d", tmp / "l")
    day = {"i": 0}
    p = MockProvider(seed=3, clock=lambda: utcnow()
                     - timedelta(days=60 - day["i"]))
    for i in range(60):
        day["i"] = i
        st.write_snapshot(p.snapshot(["EURUSD"], settings.universe.tenors))
    return st


class TestSurfaces:
    def test_heat_grid_shape_and_provenance(self, store) -> None:
        h = heat(store, "EURUSD")
        assert h["history_days"] >= 55
        assert len(h["rows"]) >= 8
        for row in h["rows"]:
            assert set(row["nodes"]) == {"10P", "25P", "ATM", "25C", "10C"}
            assert row["provenance"].startswith("derived:node_vols(store://")
            for n in row["nodes"].values():
                assert 0 <= n["pct"] <= 100

    def test_smile_cone_and_t5_overlay(self, store) -> None:
        s = smile(store, "EURUSD", "3M")
        assert len(s["nodes"]) == 5
        for n in s["nodes"]:
            assert n["p10"] <= n["p90"]
            assert "t5" in n                     # the comparison overlay
        assert s["provenance"].startswith("derived:node_vols(")

    def test_smile_consistency_with_node_vol(self, store) -> None:
        s = smile(store, "EURUSD", "3M")
        atm = next(n for n in s["nodes"] if n["node"] == "ATM")
        assert atm["vol"] == round(node_vol(atm["vol"], 0, 0, "ATM"), 3)

    def test_term_three_vintages(self, store) -> None:
        t = term(store, "EURUSD")
        assert set(t["series"]) == {"today", "t1", "t5"}
        assert len(t["series"]["today"]) >= 8
        assert t["provenance"] == "store://vol/EURUSD/<tenor>/atm"

    def test_driver_resolves_store_ref_and_marks_detection(self,
                                                           store) -> None:
        card = {"id": "ATM_PCTILE|EURUSD|3M", "type": "ATM_PCTILE",
                "pair": "EURUSD", "tenors": ["3M"],
                "detected_at": "2026-06-11T08:00:00+00:00",
                "evidence": [{"label": "atm", "value": "8.1",
                  "provenance": "store://vol/EURUSD/3M/atm"}]}
        d = driver(store, card)
        assert d["field"] == "atm" and d["tenor"] == "3M"
        assert len(d["series"]) >= 50
        assert d["detected_at"] == card["detected_at"]
        assert d["provenance"] == "store://vol/EURUSD/3M/atm"

    def test_driver_fallback_for_signal_cards(self, store) -> None:
        card = {"id": "skew_richcheap|EURUSD|3M rr", "type":
                "skew_richcheap", "pair": "EURUSD", "tenors": ["3M"],
                "detected_at": "t", "evidence": [
                  {"label": "z", "value": "2",
                   "provenance": "packet.signals[0].score"}]}
        d = driver(store, card)
        assert d["field"] == "rr25"          # skew family → rr series
