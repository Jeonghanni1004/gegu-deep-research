"""Final Analyst input contract — Research Layer stable output surface.

canonical_findings is the sole authoritative research fact source.
Compat sections / reference stubs are consumption interfaces only.
This module does NOT implement Final Analyst.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from research.schemas import (
    CanonicalFinding,
    CitedFinding,
    ExcludedAuditItem,
    FundamentalResearch,
    MarketResearch,
    ResearchSection,
)


class ResearchOutputContract(BaseModel):
    """What Final Analyst should consume by default.

    Explicit non-goals for Final Analyst:
    - do not treat raw EvidencePack as primary research input
    - do not re-scan compat sections for new research facts
    - do not re-summarize numbers as if that were analysis
    """

    model_config = ConfigDict(extra="forbid")

    stock_code: str
    agent: Literal["fundamental", "market"]
    research_as_of_date: str
    canonical_findings: list[CanonicalFinding] = Field(default_factory=list)
    research_tensions: list[CanonicalFinding] = Field(default_factory=list)
    research_gaps: list[CitedFinding] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    excluded_audit: list[ExcludedAuditItem] = Field(default_factory=list)
    relevance_notes: list[str] = Field(default_factory=list)
    time_context: dict[str, Any] = Field(default_factory=dict)
    uncertainty_boundaries: list[str] = Field(default_factory=list)
    contract_notes: list[str] = Field(
        default_factory=lambda: [
            "canonical_findings is the only authoritative research expression",
            "compat/reference/cross_evidence_findings must not invent new research facts",
            "weight is selection priority, not investment probability",
            "Grounded synthesis is deterministic, not autonomous research",
        ]
    )


def _boundary_texts(findings: list[CitedFinding | CanonicalFinding]) -> list[str]:
    out: list[str] = []
    for f in findings:
        text = " ".join([f.interpretation or "", f.reasoning or "", f.claim or ""])
        if any(k in text for k in ("不足以", "边界", "无法", "不能单独", "不足以判定", "不足")):
            if f.interpretation:
                out.append(f.interpretation)
            elif f.claim:
                out.append(f.claim)
    # de-dup preserve order
    seen = set()
    uniq = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def build_research_output_contract(
    research: FundamentalResearch | MarketResearch,
    *,
    time_context: dict[str, Any] | None = None,
) -> ResearchOutputContract:
    agent: Literal["fundamental", "market"] = (
        "fundamental" if isinstance(research, FundamentalResearch) else "market"
    )
    canonicals = list(research.canonical_findings)
    tensions = [c for c in canonicals if c.finding_kind == "tension"]
    gaps = list(research.evidence_gaps)
    return ResearchOutputContract(
        stock_code=research.stock_code,
        agent=agent,
        research_as_of_date=research.research_as_of_date,
        canonical_findings=canonicals,
        research_tensions=tensions,
        research_gaps=gaps,
        evidence_references=list(research.used_evidence_ids),
        excluded_audit=list(research.excluded_audit),
        relevance_notes=[
            "irrelevant excluded from core",
            "macro_market → macro_background only",
            "industry_related requires strong industry tokens",
        ],
        time_context=time_context or {"research_as_of_date": research.research_as_of_date},
        uncertainty_boundaries=_boundary_texts(canonicals + gaps),
    )


def iter_all_findings(research: FundamentalResearch | MarketResearch) -> list[CitedFinding]:
    out: list[CitedFinding] = []
    data = research.model_dump()
    list_keys = {
        "core_facts",
        "key_research_findings",
        "research_tensions",
        "evidence_gaps",
        "canonical_findings",
        "cross_evidence_findings",
        "key_strengths",
        "key_weaknesses",
        "key_uncertainties",
    }
    for key, val in data.items():
        if key in list_keys and isinstance(val, list):
            for item in val:
                out.append(CitedFinding.model_validate(item))
        elif isinstance(val, dict) and "findings" in val:
            out.extend(ResearchSection.model_validate(val).findings)
    return out


def validate_canonical_integrity(research: FundamentalResearch | MarketResearch) -> list[str]:
    """Canonical uniqueness + reference-not-new-finding + stable ids/numbers."""
    errors: list[str] = []
    canonicals = list(research.canonical_findings)
    by_id = {c.finding_id: c for c in canonicals}
    if len(by_id) != len(canonicals):
        errors.append("duplicate finding_id inside canonical_findings")

    # Full analytical expressions outside canonical must not invent new claims
    for f in iter_all_findings(research):
        if f.finding_kind == "reference":
            rid = f.ref_finding_id
            if not rid or rid not in by_id:
                errors.append(f"reference missing canonical target: {f.ref_finding_id}")
                continue
            target = by_id[rid]
            if f.claim.strip() == target.claim.strip():
                errors.append(f"reference {rid} clones full canonical claim (not allowed)")
            continue

        if f.status != "supported":
            continue

        # Spine lists may repeat the same canonical object by finding_id
        fid = f.finding_id
        if fid and fid in by_id:
            target = by_id[fid]
            if f.claim.strip() != target.claim.strip():
                errors.append(f"{fid} claim diverged from canonical")
            if list(f.evidence_ids) != list(target.evidence_ids):
                errors.append(f"{fid} evidence_ids diverged from canonical")
            if (f.reasoning or "") != (target.reasoning or ""):
                errors.append(f"{fid} reasoning diverged from canonical")
            continue

        # Compat full finding that equals a canonical claim without shared id = illegal clone
        if f.finding_kind in {"cross", "tension"}:
            for c in canonicals:
                if f.claim.strip() == c.claim.strip() and f.finding_id != c.finding_id:
                    errors.append(
                        f"compat/orphan finding clones canonical {c.finding_id} without shared finding_id"
                    )
    return errors


def is_reference_new_finding(finding: CitedFinding) -> bool:
    """References are never new research insights. Always False for reference stubs."""
    if finding.finding_kind == "reference":
        return False
    return False


def is_authoritative_research_finding(finding: CitedFinding) -> bool:
    """True only for supported non-reference analytical/atomic findings."""
    return finding.finding_kind != "reference" and finding.status == "supported"


def has_incremental_value(a: CitedFinding, b: CitedFinding) -> bool:
    """Return True if B adds relation/interpretation/boundary beyond A.

    Not incremental if B only restates same numbers/section/phrasing.
    """
    if b.finding_kind == "reference":
        return False
    if a.claim.strip() == b.claim.strip():
        return False
    same_ids = set(a.evidence_ids) == set(b.evidence_ids) and len(a.evidence_ids) > 0
    if same_ids:
        # Require new interpretive content
        a_interp = (a.interpretation or "").strip()
        b_interp = (b.interpretation or "").strip()
        if b_interp and b_interp != a_interp:
            # Still check boundary / relation markers
            markers = ("但", "因此", "因此", "不足以", "边界", "条件", "对照", "分化", "冲突")
            if any(m in b_interp or m in (b.claim or "") for m in markers):
                if b_interp not in a_interp and a_interp not in b_interp:
                    return True
        return False
    # Different evidence set can be incremental if multi-id relation
    if len(b.evidence_ids) >= 2 and set(b.evidence_ids) - set(a.evidence_ids):
        return True
    return False


def depth_signals(finding: CitedFinding) -> dict[str, bool]:
    """Lightweight depth checklist (not a score by finding count)."""
    text = " ".join([finding.claim or "", finding.reasoning or "", finding.interpretation or ""])
    has_number = any(ch.isdigit() for ch in text)
    has_relation = any(k in text for k in ("但", "同时", "对照", "分化", "冲突", "因此", "vs", "与"))
    has_interp = bool((finding.interpretation or "").strip()) and finding.interpretation != finding.claim
    has_boundary = any(k in text for k in ("不足以", "边界", "无法", "不能单独", "不能仅", "不作"))
    listing_only = has_number and not has_relation and not has_boundary
    return {
        "has_number": has_number,
        "has_relation": has_relation,
        "has_interpretation": has_interp,
        "has_boundary": has_boundary,
        "listing_only": listing_only,
        "valid_deep": has_number and has_relation and has_interp and has_boundary and not listing_only,
    }
