"""Snap pipeline: provider -> validator -> store. One call = one cycle."""
from __future__ import annotations

import logging

from volwatch.config import Settings
from volwatch.data.provider import MarketDataProvider
from volwatch.data.store import ParquetStore
from volwatch.core.models import MarketSnapshot
from volwatch.data.validation import SnapshotValidator, ValidationReport

log = logging.getLogger(__name__)


class SnapPipeline:
    def __init__(self, settings: Settings, provider: MarketDataProvider,
                 validator: SnapshotValidator | None = None,
                 store: ParquetStore | None = None) -> None:
        self.settings = settings
        self.provider = provider
        self.validator = validator or SnapshotValidator()
        self.store = store or ParquetStore(settings.storage.root,
                                           settings.storage.latest_dir)

    def run_once(self) -> tuple[MarketSnapshot, ValidationReport]:
        """Snap once; return the VALIDATED snapshot so downstream consumers
        (analytics, signals) see exactly what was stored — never re-snap."""
        u = self.settings.universe
        snap = self.provider.snapshot(u.all_pairs, u.tenors)
        snap, report = self.validator.validate(snap)
        self.store.write_snapshot(snap)
        if not report.clean:
            log.warning("snapshot %s: %d flags", snap.snapshot_id[:8],
                        len(report.flagged))
        return snap, report
