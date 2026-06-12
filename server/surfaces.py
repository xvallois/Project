"""Decision surfaces (Phase 3, ADR-0009).

Server-computed views over REAL store history. Every payload answers one
trader question and carries provenance refs; every surface routes back
into the Investigate→Feed→Blotter flow (no standalone charts).

  heat(pair)    — "where on this surface is rich/cheap, and is an
                   opportunity already open there?"
  smile(pair,t) — "is the smile itself dislocated, or just ATM — and has
                   it actually moved vs a week ago?"
  term(pair)    — "is the curve repricing at a point (kink) or in level?"
  driver(card)  — "what does the series behind this card look like, and
                   where did detection fire?"
"""
from __future__ import annotations

import pandas as pd

NODES = ("10P", "25P", "ATM", "25C", "10C")
TENOR_ORDER = ("ON", "1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y")


def node_vol(atm: float, rr25: float, bf25: float, node: str) -> float:
    """Smile reconstruction — same approximation family as the detectors."""
    if node == "ATM":
        return atm
    wing = node.startswith("10")
    b, m = (3.2, 1.85) if wing else (1.0, 1.0)
    sign = 1 if node.endswith("C") else -1
    return atm + bf25 * b + sign * (rr25 * m) / 2


def _daily(store, pair: str) -> pd.DataFrame:
    df = store.query(
        f"SELECT tenor, \"asof\", atm, rr25, bf25 FROM vol "
        f"WHERE pair='{pair}' AND status=0")
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["asof"]).dt.date
    return (df.sort_values("asof")
            .groupby(["tenor", "date"], as_index=False).last())


def _pct(past, cur) -> float:
    if len(past) == 0:
        return 50.0
    return round(100.0 * (((past < cur).sum() + 0.5 * (past == cur).sum())
                          / len(past)), 1)


def heat(store, pair: str) -> dict:
    daily = _daily(store, pair)
    rows = []
    for tenor in TENOR_ORDER:
        g = daily[daily.tenor == tenor]
        if len(g) < 2:
            continue
        cur, prev = g.iloc[-1], g.iloc[-2]
        nodes = {}
        for n in NODES:
            v = node_vol(cur.atm, cur.rr25, cur.bf25, n)
            hist = [node_vol(r.atm, r.rr25, r.bf25, n)
                    for r in g.iloc[:-1].itertuples()]
            nodes[n] = {"vol": round(v, 3),
                        "d1": round(v - node_vol(prev.atm, prev.rr25,
                                                 prev.bf25, n), 3),
                        "pct": _pct(pd.Series(hist), v)}
        rows.append({"tenor": tenor, "nodes": nodes,
                     "provenance": f"derived:node_vols(store://vol/{pair}"
                                   f"/{tenor}/atm, store://vol/{pair}/"
                                   f"{tenor}/rr25, store://vol/{pair}/"
                                   f"{tenor}/bf25)"})
    return {"pair": pair, "rows": rows, "history_days":
            int(daily.date.nunique()) if not daily.empty else 0}


def smile(store, pair: str, tenor: str) -> dict:
    daily = _daily(store, pair)
    g = daily[daily.tenor == tenor]
    if len(g) < 7:
        return {"pair": pair, "tenor": tenor, "nodes": []}
    cur = g.iloc[-1]
    t5 = g.iloc[-6]                       # ~one trading week back
    out = []
    for n in NODES:
        hist = sorted(node_vol(r.atm, r.rr25, r.bf25, n)
                      for r in g.iloc[:-1].itertuples())
        v = node_vol(cur.atm, cur.rr25, cur.bf25, n)
        q = lambda f: hist[min(len(hist) - 1, int(f * len(hist)))]
        out.append({"node": n, "vol": round(v, 3),
                    "t5": round(node_vol(t5.atm, t5.rr25, t5.bf25, n), 3),
                    "p10": round(q(0.10), 3), "p90": round(q(0.90), 3),
                    "pct": _pct(pd.Series(hist), v)})
    prov = (f"derived:node_vols(store://vol/{pair}/{tenor}/atm, "
            f"store://vol/{pair}/{tenor}/rr25, "
            f"store://vol/{pair}/{tenor}/bf25)")
    return {"pair": pair, "tenor": tenor, "nodes": out,
            "asof": str(cur.date), "t5_date": str(t5.date),
            "provenance": prov}


def term(store, pair: str) -> dict:
    daily = _daily(store, pair)
    series = {}
    for label, idx in (("today", -1), ("t1", -2), ("t5", -6)):
        pts = []
        for tenor in TENOR_ORDER:
            g = daily[daily.tenor == tenor]
            if len(g) >= abs(idx):
                pts.append({"tenor": tenor,
                            "atm": round(float(g.iloc[idx].atm), 3)})
        series[label] = pts
    return {"pair": pair, "field": "atm", "series": series,
            "provenance": f"store://vol/{pair}/<tenor>/atm"}


def driver(store, card: dict) -> dict:
    """The series behind a card + the detection moment — drilldown."""
    import re
    ref = next((it["provenance"] for it in card.get("evidence", [])
                if "store://" in it["provenance"]), None)
    if ref:
        m = re.search(r"store://vol/([A-Z]{6})/(\w+)/(atm|rr25|bf25)", ref)
        pair, tenor, fld = m.group(1), m.group(2), m.group(3)
    else:                                  # packet-signal card fallback
        pair = card["pair"]
        tenor = (card.get("tenors") or ["3M"])[0]
        fld = "rr25" if "skew" in card["type"].lower() else "atm"
        ref = f"store://vol/{pair}/{tenor}/{fld}"
    daily = _daily(store, pair)
    g = daily[daily.tenor == tenor].tail(120)
    pts = [{"date": str(r.date), "value": round(float(getattr(r, fld)), 4)}
           for r in g.itertuples()]
    return {"card_id": card["id"], "pair": pair, "tenor": tenor,
            "field": fld, "series": pts, "detected_at": card["detected_at"],
            "provenance": ref}
