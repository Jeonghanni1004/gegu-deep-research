"""Research-layer evidence priority (weight ranking).

Reuses debate.evidence_weight formula. Weight is a debate/research reference
score — NOT an up/down or investment probability.
"""

from __future__ import annotations

from evidence.schema import Evidence

from debate.evidence_weight import calculate_evidence_weight, evidence_weight_breakdown


def evidence_priority_score(evidence: Evidence) -> float:
    """reliability × freshness reference weight for context ranking."""
    return calculate_evidence_weight(evidence)


def rank_evidence(items: list[Evidence], *, reverse: bool = True) -> list[Evidence]:
    """Sort evidence by priority weight (default: highest first)."""
    return sorted(items, key=evidence_priority_score, reverse=reverse)


def attach_weight_meta(evidence: Evidence) -> dict:
    return evidence_weight_breakdown(evidence)
