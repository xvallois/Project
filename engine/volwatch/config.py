"""Configuration loading & validation.

All runtime configuration lives in YAML under config/ and is validated by
pydantic models at startup. Fail-fast: a typo in a pair name should kill the
process at boot, not corrupt a day of history.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from volwatch.core.models import Tenor

_PAIR_RE = re.compile(r"^[A-Z]{6}$")


class UniverseConfig(BaseModel):
    pairs: list[str]
    cross_pairs: list[str] = Field(default_factory=list)
    tenors: list[Tenor]

    @field_validator("tenors", mode="before")
    @classmethod
    def _yaml_on_bool_guard(cls, v: list) -> list:
        """YAML 1.1 parses bare `ON` as boolean True — undo that footgun."""
        return ["ON" if t is True else t for t in v]

    @field_validator("pairs", "cross_pairs")
    @classmethod
    def _valid_pairs(cls, v: list[str]) -> list[str]:
        bad = [p for p in v if not _PAIR_RE.match(p)]
        if bad:
            raise ValueError(f"Invalid pair codes: {bad}")
        return v

    @property
    def all_pairs(self) -> list[str]:
        return [*self.pairs, *self.cross_pairs]


class ScheduleConfig(BaseModel):
    snap_interval_minutes: int = Field(ge=1, le=60)
    eod_time_utc: str = "21:30"          # NY 5pm-ish official mark
    market_open_days: list[int] = [0, 1, 2, 3, 4]  # Mon-Fri


class StorageConfig(BaseModel):
    root: Path
    latest_dir: Path

    def parquet_dir(self, data_type: str) -> Path:
        return self.root / "parquet" / data_type


class BookConfig(BaseModel):
    enabled: bool = False               # planned: position ingestion
    source: str = "csv"                 # csv | api (future)
    path: Path | None = None


class AiConfig(BaseModel):
    model: str = "claude-sonnet-4-20250514"
    max_ideas_per_cycle: int = 5


class Settings(BaseModel):
    universe: UniverseConfig
    schedule: ScheduleConfig
    storage: StorageConfig
    book: BookConfig = BookConfig()
    ai: AiConfig = AiConfig()


def load_settings(path: str | Path = "config/settings.yaml") -> Settings:
    raw = yaml.safe_load(Path(path).read_text())
    return Settings.model_validate(raw)
