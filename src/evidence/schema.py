"""Unified Evidence schema (Pydantic). No investment stance fields."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceType(str, Enum):
    FACT = "FACT"
    DERIVED = "DERIVED"
    EVENT = "EVENT"
    EXPECTATION = "EXPECTATION"


class FreshnessStatus(str, Enum):
    VERY_RECENT = "very_recent"  # 0-24h
    RECENT = "recent"  # 1-7d
    HISTORICAL_RECENT = "historical_recent"  # 7-30d
    STALE = "stale"  # >30d
    PERIODIC = "periodic"  # financial statements / consensus snapshots


class Reliability(str, Enum):
    HIGH = "high"
    MEDIUM_HIGH = "medium_high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    source_type: str
    url: str | None = None
    retrieved_at: str | None = None
    published_at: str | None = None
    updated_at: str | None = None


class EvidenceTime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_date: str | None = None
    report_date: str | None = None
    published_at: str | None = None
    retrieved_at: str | None = None


class Freshness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age_hours: float | None = None
    status: FreshnessStatus


class Evidence(BaseModel):
    """A citable factual material unit. Must not contain investment opinions."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    stock_code: str | None = None
    evidence_type: EvidenceType
    subtype: str
    claim: str
    value: dict[str, Any] = Field(default_factory=dict)
    source: EvidenceSource
    time: EvidenceTime
    freshness: Freshness
    reliability: Reliability
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


FORBIDDEN_OPINION_FIELDS = {
    "bull_score",
    "bear_score",
    "stance",
    "investment_rating",
    "confidence_of_investment",
    "supporting",
    "contradicting",
    "uncertain",
}


def assert_no_opinion_fields(payload: dict[str, Any]) -> None:
    flat_keys: set[str] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            flat_keys.update(obj.keys())
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    bad = flat_keys & FORBIDDEN_OPINION_FIELDS
    if bad:
        raise ValueError(f"Opinion fields are forbidden in Evidence: {sorted(bad)}")


def utc_now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()
