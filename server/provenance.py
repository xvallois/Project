"""Provenance — the non-negotiable rule, made structural (Phase 1 §3).

Every numeric value shipped to the UI carries a provenance ref. The
verifier RESOLVES each ref against the live packet/store before a card
may leave the server; an unverifiable number rejects the whole card
(logged with the violation named). The future Analyst inherits this gate
unchanged: its output passes through verify_card like everything else.

Ref schemes:
  packet.<dotted.path[idx]>     resolvable inside the cycle ResearchPacket
  store://vol/<pair>/<tenor>/<field>   latest stored quote field
  derived:<fn>(<ref>[, <ref>...])      arithmetic over resolvable refs
  prior:<name>                  declared placeholder (NOT a market number;
                                allowed, rendered as 'placeholder' in UI)
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

_PACKET_TOKEN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)((\[\d+\])*)")


@dataclass(frozen=True)
class Violation:
    ref: str
    reason: str


def resolve_packet_path(packet: dict, path: str) -> Any:
    """Resolve 'packet.market.EURJPY.vols.3M.rr25' / 'packet.signals[0].score'."""
    if not path.startswith("packet."):
        raise KeyError(f"not a packet ref: {path}")
    cur: Any = packet
    for part in path[len("packet."):].split("."):
        m = _PACKET_TOKEN.fullmatch(part)
        if not m:
            raise KeyError(f"bad path token {part!r}")
        key, idxs = m.group(1), re.findall(r"\[(\d+)\]", m.group(2) or "")
        if not isinstance(cur, dict) or key not in cur:
            raise KeyError(f"missing key {key!r} in {path}")
        cur = cur[key]
        for i in idxs:
            cur = cur[int(i)]
    return cur


_STORE_RE = re.compile(
    r"store://vol/([A-Z]{6})/(ON|1W|2W|1M|2M|3M|6M|9M|1Y)/(atm|rr25|bf25)$")
_DERIVED_RE = re.compile(r"derived:[a-z_0-9]+\((.*)\)$")


def _split_args(argstr: str) -> list[str]:
    """Split derived-fn args at top-level commas (refs contain no parens
    except nested derived, which we keep intact)."""
    out, depth, cur = [], 0, ""
    for ch in argstr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


class ProvenanceVerifier:
    """Resolves refs against a packet and a set of known store series."""

    def __init__(self, packet: dict,
                 store_fields: set[tuple[str, str, str]],
                 ledger_keys: set[str] | None = None) -> None:
        self._packet = packet
        self._store_fields = store_fields   # {(pair, tenor, field)}
        self._ledger_keys = ledger_keys

    def check_ref(self, ref: str) -> Violation | None:
        if ref.startswith("packet."):
            try:
                v = resolve_packet_path(self._packet, ref)
            except (KeyError, IndexError, TypeError) as e:
                return Violation(ref, f"unresolvable packet path: {e}")
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return Violation(ref, "resolves to non-finite value")
            return None
        if ref.startswith("store://"):
            m = _STORE_RE.match(ref)
            if not m:
                return Violation(ref, "malformed store ref")
            if (m.group(1), m.group(2), m.group(3)) not in self._store_fields:
                return Violation(ref, "series not present in store")
            return None
        if ref.startswith("derived:"):
            m = _DERIVED_RE.match(ref)
            if not m:
                return Violation(ref, "malformed derived ref")
            inner = [a for a in _split_args(m.group(1))
                     if a.startswith(("packet.", "store://", "derived:",
                                      "prior:"))]
            if not inner:
                return Violation(ref, "derived ref names no source refs")
            for a in inner:
                v = self.check_ref(a)
                if v:
                    return Violation(ref, f"input fails: {v.reason}")
            return None
        if ref.startswith("prior:"):
            return None                    # declared placeholder, allowed
        if ref.startswith("ledger:"):
            # institutional memory: resolvable iff the db key exists
            if self._ledger_keys is None:
                return None                # no ledger context: tolerated
            return (None if ref in self._ledger_keys
                    else Violation(ref, "ledger key not present"))
        return Violation(ref, "unknown provenance scheme")

    def verify_card(self, card: dict) -> list[Violation]:
        """Every numeric-bearing element must carry a checkable ref."""
        violations: list[Violation] = []
        items = (card.get("evidence", []) + card.get("supporting", [])
                 + card.get("contradictions", [])
                 + card.get("similar_history_items", []))
        for item in items:
            ref = item.get("provenance")
            if not ref:
                violations.append(Violation(
                    f"{card.get('id')}::{item.get('label')}",
                    "numeric item without provenance"))
                continue
            v = self.check_ref(ref)
            if v:
                violations.append(v)
        return violations
