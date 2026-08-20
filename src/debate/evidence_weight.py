"""Deterministic Evidence weight for debate (not investment probability)."""

from __future__ import annotations

from evidence.schema import Evidence, FreshnessStatus, Reliability

RELIABILITY_WEIGHT: dict[str, float] = {
    Reliability.HIGH.value: 1.0,
    Reliability.MEDIUM_HIGH.value: 0.9,
    Reliability.MEDIUM.value: 0.8,
    Reliability.LOW.value: 0.6,
}

FRESHNESS_WEIGHT: dict[str, float] = {
    FreshnessStatus.VERY_RECENT.value: 1.0,
    FreshnessStatus.RECENT.value: 0.9,
    FreshnessStatus.HISTORICAL_RECENT.value: 0.7,
    FreshnessStatus.STALE.value: 0.4,
    FreshnessStatus.PERIODIC.value: 0.8,
}


def reliability_weight(reliability: str | Reliability) -> float:
    key = reliability.value if isinstance(reliability, Reliability) else str(reliability)
    return RELIABILITY_WEIGHT.get(key, 0.7)


def freshness_weight(freshness: str | FreshnessStatus) -> float:
    key = freshness.value if isinstance(freshness, FreshnessStatus) else str(freshness)
    return FRESHNESS_WEIGHT.get(key, 0.7)


def calculate_evidence_weight(evidence: Evidence) -> float:
    """Reference weight for debate only — NOT upside/downside probability."""
    rw = reliability_weight(evidence.reliability)
    fw = freshness_weight(evidence.freshness.status)
    return round(rw * fw, 6)


def evidence_weight_breakdown(evidence: Evidence) -> dict[str, float | str]:
    rw = reliability_weight(evidence.reliability)
    fw = freshness_weight(evidence.freshness.status)
    return {
        "evidence_id": evidence.evidence_id,
        "reliability": evidence.reliability.value,
        "freshness": evidence.freshness.status.value,
        "reliability_weight": rw,
        "freshness_weight": fw,
        "weight": round(rw * fw, 6),
    }
