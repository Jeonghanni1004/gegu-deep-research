"""Evidence Layer: fact materials for downstream agents (no opinions)."""

from .pack import EvidencePack
from .schema import (
    Evidence,
    EvidenceSource,
    EvidenceTime,
    EvidenceType,
    Freshness,
    FreshnessStatus,
    Reliability,
)
from .normalizer import EvidenceNormalizer, build_evidence_pack

__all__ = [
    "Evidence",
    "EvidencePack",
    "EvidenceNormalizer",
    "EvidenceSource",
    "EvidenceTime",
    "EvidenceType",
    "Freshness",
    "FreshnessStatus",
    "Reliability",
    "build_evidence_pack",
]
