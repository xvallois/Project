"""Event calendar: CSV-backed to start (desk decision pending on ECO feed).

config/events.csv columns: date (YYYY-MM-DD), ccy, name, importance (1-3).
Keep PAST occurrences in the file: the event-vol signal needs them to
measure historical realized event moves. A calendar with only future
events can price nothing.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Event:
    date: date
    ccy: str
    name: str
    importance: int


class EventCalendar:
    def __init__(self, events: list[Event]) -> None:
        self._events = sorted(events, key=lambda e: e.date)

    @classmethod
    def from_csv(cls, path: str | Path = "config/events.csv") -> "EventCalendar":
        p = Path(path)
        if not p.exists():
            log.warning("no event calendar at %s — event signals silent", p)
            return cls([])
        out = []
        with p.open() as f:
            for row in csv.DictReader(f):
                try:
                    out.append(Event(date=date.fromisoformat(row["date"].strip()),
                                     ccy=row["ccy"].strip().upper(),
                                     name=row["name"].strip(),
                                     importance=int(row["importance"])))
                except (KeyError, ValueError) as e:
                    log.error("bad event row %s: %s — skipped", row, e)
        return cls(out)

    def upcoming(self, asof: date, horizon_days: int,
                 min_importance: int = 2) -> list[Event]:
        lo, hi = asof + timedelta(days=1), asof + timedelta(days=horizon_days)
        return [e for e in self._events
                if lo <= e.date <= hi and e.importance >= min_importance]

    def past_occurrences(self, name: str, ccy: str, before: date,
                         max_n: int = 24) -> list[Event]:
        hits = [e for e in self._events
                if e.name == name and e.ccy == ccy and e.date < before]
        return hits[-max_n:]

    def affects(self, event: Event, pair: str) -> bool:
        return event.ccy in (pair[:3], pair[3:])
