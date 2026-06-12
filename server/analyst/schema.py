"""Research Brief — the Analyst's ONLY output shape (Phase 2).

Seven sections, identical everywhere (feed, Investigate, workspace brief,
post-mortem). Statements are typed: kind="analyst" for model prose,
kind="deterministic" for engine items. Every numeric in analyst prose must
be covered by a cited evidence item or the statement is dropped — the
provenance gate, applied to language.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

SECTIONS = ("finding", "supporting", "contradictory", "why_now",
            "invalidation", "historical", "next_investigation")

SECTION_TITLES = {
    "finding": "Finding", "supporting": "Supporting Evidence",
    "contradictory": "Contradictory Evidence", "why_now": "Why Now",
    "invalidation": "What Would Invalidate This",
    "historical": "Similar Historical Episodes",
    "next_investigation": "Suggested Next Investigation"}


@dataclass
class Evidence:
    """One numbered fact handed to the Analyst. Always deterministic."""
    eid: str                 # "E1"...
    label: str
    value: str
    provenance: str


@dataclass
class Statement:
    text: str
    kind: str                # "analyst" | "deterministic"
    cites: list[str] = field(default_factory=list)


@dataclass
class ResearchBrief:
    card_id: str
    depth: str               # "triage" | "investigate" | "deep"
    provider: str            # "claude" | "stub"
    model: str
    units: int
    status: str              # "ok" | "degraded" | "rejected"
    sections: dict[str, list[Statement]]
    evidence: list[Evidence]
    dropped: list[str]       # statements killed by the numeric gate
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- gating
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(text: str) -> set[str]:
    return {m.group(0).replace(",", ".").rstrip("0").rstrip(".")
            for m in _NUM.finditer(text)}


def gate_statement(st: Statement, evidence: dict[str, Evidence],
                   allowed_freebies: frozenset[str] = frozenset(
                       {"1", "2", "3", "5", "10", "25"})) -> str | None:
    """Return a rejection reason, or None if the statement passes.

    Rule: every number in analyst text must appear in the VALUE of a cited
    evidence item. Tiny structural numerals (tenor arithmetic like 25d,
    counts 1-3) are tolerated; everything else needs a citation trail.
    """
    if st.kind != "analyst":
        return None
    cited_numbers: set[str] = set()
    for c in st.cites:
        e = evidence.get(c)
        if e is None:
            return f"cites unknown evidence {c}"
        cited_numbers |= _numbers(e.value) | _numbers(e.label)
    for n in _numbers(st.text):
        if n in cited_numbers or n in allowed_freebies:
            continue
        if _rounds_to_cited(n, cited_numbers):
            continue                       # "2.3" quoting a cited "2.31"
        return f"uncited number {n!r}"
    return None


def _rounds_to_cited(n: str, cited: set[str]) -> bool:
    """A text number passes if some cited number rounds to it at the
    text's own precision — quoting with fewer decimals is legitimate;
    inventing MORE precision than the source is not."""
    try:
        nv = float(n)
    except ValueError:
        return False
    decimals = len(n.split(".")[1]) if "." in n else 0
    for c in cited:
        try:
            cv = float(c)
        except ValueError:
            continue
        if len(c.split(".")[1] if "." in c else "") < decimals:
            continue                       # text more precise than source
        if abs(round(cv, decimals) - nv) < 1e-9 or abs(cv - nv) < 1e-9:
            return True
    return False


def gate_brief(sections: dict[str, list[Statement]],
               evidence: dict[str, Evidence],
               max_drops: int = 3) -> tuple[dict[str, list[Statement]],
                                            list[str], str]:
    """Apply the numeric gate to a whole brief.

    Returns (clean_sections, dropped_reasons, status). Missing sections
    reject the brief outright — the structure IS the contract.
    """
    for s in SECTIONS:
        if s not in sections:
            return {}, [f"missing section {s}"], "rejected"
    dropped: list[str] = []
    clean: dict[str, list[Statement]] = {}
    for name, stmts in sections.items():
        kept = []
        for st in stmts:
            reason = gate_statement(st, evidence)
            if reason:
                dropped.append(f"{name}: {reason} :: {st.text[:80]}")
            else:
                kept.append(st)
        clean[name] = kept
    if len(dropped) > max_drops:
        return {}, dropped, "rejected"
    if not clean["finding"]:
        return {}, dropped + ["finding empty after gating"], "rejected"
    return clean, dropped, "degraded" if dropped else "ok"
