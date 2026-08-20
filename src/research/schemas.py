"""Pydantic schemas for Fundamental / Market research outputs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


FindingKind = Literal["atomic", "cross", "tension", "insufficient", "reference"]


class CitedFinding(BaseModel):
    """Fact vs interpretation separation. Factual claims must cite evidence_ids."""

    model_config = ConfigDict(extra="forbid")

    claim: str
    evidence_ids: list[str] = Field(default_factory=list)
    reasoning: str = ""
    interpretation: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    status: Literal["supported", "insufficient_evidence"] = "supported"
    finding_kind: FindingKind = "atomic"
    finding_id: str | None = None
    research_question: str | None = None
    ref_finding_id: str | None = None  # for reference stubs pointing to canonical
    numbers_preserved: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_ids_when_supported(self) -> "CitedFinding":
        if self.status == "supported" and not self.evidence_ids and self.finding_kind != "reference":
            raise ValueError("supported findings must include at least one evidence_id")
        if self.finding_kind in {"cross", "tension"} and self.status == "supported":
            if len(self.evidence_ids) < 2:
                raise ValueError("cross/tension findings require at least 2 evidence_ids")
        if self.status == "insufficient_evidence":
            object.__setattr__(self, "finding_kind", "insufficient")
        if self.finding_kind == "reference" and not self.ref_finding_id:
            raise ValueError("reference findings require ref_finding_id")
        return self


class CanonicalFinding(CitedFinding):
    """Authoritative finding for one research proposition (numbers + relation + boundary)."""

    finding_id: str
    research_question: str


class ResearchSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narrative: str
    findings: list[CitedFinding] = Field(default_factory=list)
    insufficient_topics: list[str] = Field(default_factory=list)


class EvidenceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    evidence_ids: list[str] = Field(min_length=1)
    sources: list[dict[str, Any]] = Field(default_factory=list)


class ExcludedAuditItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    reason: Literal["irrelevant", "post_as_of", "out_of_window", "time_incomplete"]
    detail: str = ""


def _no_trade(v: str, where: str) -> str:
    upper = v.upper()
    for banned in ("BUY", "SELL", "STRONG BUY", "STRONG SELL", "加仓", "减仓", "买入", "卖出"):
        if banned in upper or banned in v:
            raise ValueError(f"{where} must not contain trade advice: {banned}")
    return v


class FundamentalResearch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str
    agent: Literal["fundamental"] = "fundamental"
    research_as_of_date: str
    summary: str
    # Compressed analytical spine
    core_facts: list[CitedFinding] = Field(default_factory=list)
    key_research_findings: list[CitedFinding] = Field(default_factory=list)
    research_tensions: list[CitedFinding] = Field(default_factory=list)
    evidence_gaps: list[CitedFinding] = Field(default_factory=list)
    canonical_findings: list[CanonicalFinding] = Field(default_factory=list)
    # Compatibility sections for Debate (reference stubs, not full clones)
    business_model: ResearchSection
    financial_performance: ResearchSection
    profitability: ResearchSection
    financial_health: ResearchSection
    cash_flow: ResearchSection
    recent_events: ResearchSection
    market_expectations: ResearchSection
    cross_evidence_findings: list[CitedFinding] = Field(default_factory=list)
    key_strengths: list[CitedFinding] = Field(default_factory=list)
    key_weaknesses: list[CitedFinding] = Field(default_factory=list)
    key_uncertainties: list[CitedFinding] = Field(default_factory=list)
    evidence_citations: list[EvidenceCitation] = Field(default_factory=list)
    used_evidence_ids: list[str] = Field(default_factory=list)
    excluded_audit: list[ExcludedAuditItem] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def _no_trade_advice(cls, v: str) -> str:
        return _no_trade(v, "FundamentalResearch.summary")


class MarketResearch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str
    agent: Literal["market"] = "market"
    research_as_of_date: str
    summary: str
    core_facts: list[CitedFinding] = Field(default_factory=list)
    key_research_findings: list[CitedFinding] = Field(default_factory=list)
    research_tensions: list[CitedFinding] = Field(default_factory=list)
    evidence_gaps: list[CitedFinding] = Field(default_factory=list)
    canonical_findings: list[CanonicalFinding] = Field(default_factory=list)
    # Compatibility
    price_status: ResearchSection
    trend: ResearchSection
    moving_average_structure: ResearchSection
    momentum: ResearchSection
    technical_signals: ResearchSection
    recent_market_events: ResearchSection
    market_expectations: ResearchSection
    news_narrative: ResearchSection = Field(
        default_factory=lambda: ResearchSection(narrative="insufficient_evidence：新闻叙事对比未提供。")
    )
    cross_evidence_findings: list[CitedFinding] = Field(default_factory=list)
    key_strengths: list[CitedFinding] = Field(default_factory=list)
    key_weaknesses: list[CitedFinding] = Field(default_factory=list)
    key_uncertainties: list[CitedFinding] = Field(default_factory=list)
    evidence_citations: list[EvidenceCitation] = Field(default_factory=list)
    used_evidence_ids: list[str] = Field(default_factory=list)
    excluded_audit: list[ExcludedAuditItem] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def _no_trade_advice(cls, v: str) -> str:
        return _no_trade(v, "MarketResearch.summary")


class ParallelExecutionMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parallel: bool = True
    started_at: str
    finished_at: str
    duration_ms: int
    research_as_of_date: str | None = None


class ParallelResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str
    research_as_of_date: str
    fundamental: FundamentalResearch
    market: MarketResearch
    execution: ParallelExecutionMeta
