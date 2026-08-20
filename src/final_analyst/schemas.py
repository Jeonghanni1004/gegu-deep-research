"""Final Analyst schemas — Debate-driven conditional judgment."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


StatementKind = Literal["FACT", "INFERENCE", "ASSUMPTION", "UNCERTAINTY"]
ScenarioLabel = Literal["base", "bull", "bear"]
AnalystMode = Literal["grounded", "openai"]
ResolutionKind = Literal["bull_supported", "bear_supported", "partially_resolved", "unresolved"]
AssessmentStrength = Literal["strong", "moderate", "tentative", "unresolved"]
SupportStrength = Literal["weak", "moderate", "strong"]
InferenceStatus = Literal["SUPPORTED", "DERIVED", "CONDITIONAL", "UNSUPPORTED"]
EvidencePressure = Literal["mild", "elevated", "severe"]


def _forbid_trade(text: str, where: str) -> str:
    upper = text.upper()
    for banned in ("BUY", "SELL", "STRONG BUY", "STRONG SELL", "加仓", "减仓", "买入", "卖出", "目标价"):
        if banned in upper or banned in text:
            raise ValueError(f"{where} must not contain trade advice: {banned}")
    for banned in ("Autonomous Research", "自主研究", "自主发现新事实"):
        if banned in text:
            raise ValueError(f"{where} must not claim autonomous research: {banned}")
    return text


class AnalyzedStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: StatementKind
    text: str
    canonical_finding_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    debate_refs: list[str] = Field(default_factory=list)
    numbers_used: list[str] = Field(default_factory=list)
    assessment_strength: AssessmentStrength | None = None
    inference_status: InferenceStatus | None = None

    @field_validator("text")
    @classmethod
    def _no_advice(cls, v: str) -> str:
        return _forbid_trade(v, "AnalyzedStatement.text")

    @model_validator(mode="after")
    def _kind_rules(self) -> "AnalyzedStatement":
        if self.kind == "FACT" and not self.evidence_ids:
            raise ValueError("FACT statements require evidence_ids")
        if self.kind == "INFERENCE" and not self.canonical_finding_ids:
            raise ValueError("INFERENCE statements require canonical_finding_ids")
        if self.inference_status == "UNSUPPORTED":
            raise ValueError("UNSUPPORTED inference_status is not allowed in output")
        return self


class TensionDebateLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str | None = None
    challenge_id: str | None = None
    rebuttal_id: str | None = None
    challenge_type: str | None = None
    response_type: str | None = None
    summary: str = ""


class DebateResolution(BaseModel):
    """How Debate resolves a Research tension — judgment driver for FA."""

    model_config = ConfigDict(extra="forbid")

    tension_id: str
    bull_position: str
    bear_position: str
    bull_reference_ids: list[str] = Field(default_factory=list)
    bear_reference_ids: list[str] = Field(default_factory=list)
    decisive_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_challenges: list[str] = Field(default_factory=list)
    accepted_rebuttals: list[str] = Field(default_factory=list)
    rejected_rebuttals: list[str] = Field(default_factory=list)
    partially_accepted_rebuttals: list[str] = Field(default_factory=list)
    resolution: ResolutionKind
    resolution_reason: str
    assessment_strength: AssessmentStrength
    support_strength: SupportStrength | None = None  # weak|moderate|strong calibration dial


class AssessmentBasis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported_facts: list[str] = Field(default_factory=list)
    interpretation_advantage: str = ""
    unresolved: list[str] = Field(default_factory=list)
    reason_base_case_selected: str = ""
    primary_resolution: ResolutionKind | None = None
    debate_support_strength: SupportStrength | None = None
    evidence_pressure: EvidencePressure | None = None
    calibrated_frame: str = ""
    active_challenges: list[str] = Field(default_factory=list)
    accepted_rebuttals: list[str] = Field(default_factory=list)
    limiting_challenge: str = ""


class TensionResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tension_id: str
    research_question: str
    fact_anchor: AnalyzedStatement
    bull_reference: str = ""
    bear_reference: str = ""
    bull_interpretation: AnalyzedStatement
    bear_interpretation: AnalyzedStatement
    challenges: list[TensionDebateLink] = Field(default_factory=list)
    rebuttals: list[TensionDebateLink] = Field(default_factory=list)
    debate_resolution: DebateResolution
    current_assessment: AnalyzedStatement
    conditions_to_change: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: ScenarioLabel
    thesis: AnalyzedStatement
    supporting_canonical_ids: list[str] = Field(default_factory=list)
    required_assumptions: list[AnalyzedStatement] = Field(default_factory=list)
    inconsistent_with: list[str] = Field(default_factory=list)
    explanation_shift_variable: str = ""  # which verifiable variable moves the frame

    @field_validator("inconsistent_with")
    @classmethod
    def _no_advice_list(cls, values: list[str]) -> list[str]:
        for v in values:
            _forbid_trade(v, "Scenario.inconsistent_with")
        return values


class ViewChanger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger_evidence_description: str
    would_affect: str
    direction: Literal["more_constructive", "more_cautious", "unresolved_to_resolved"]
    related_gap_or_boundary: str
    canonical_finding_ids: list[str] = Field(default_factory=list)

    @field_validator("trigger_evidence_description", "related_gap_or_boundary")
    @classmethod
    def _no_advice(cls, v: str) -> str:
        return _forbid_trade(v, "ViewChanger")


class TraceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion_ref: str
    canonical_finding_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    debate_refs: list[str] = Field(default_factory=list)


class FinalAnalystMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    no_trade_advice: bool = True
    grounded_is_not_autonomous: bool = True
    selected_tension_ids: list[str] = Field(default_factory=list)
    primary_resolution: ResolutionKind | None = None
    assessment_strength: AssessmentStrength | None = None
    debate_support_strength: SupportStrength | None = None
    evidence_pressure: EvidencePressure | None = None
    notes: list[str] = Field(default_factory=list)


class FinalAnalystOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str
    research_as_of_date: str
    analyst_mode: AnalystMode
    executive_assessment: AnalyzedStatement
    core_thesis: AnalyzedStatement
    key_drivers: list[AnalyzedStatement] = Field(default_factory=list)
    core_tensions: list[TensionResolution] = Field(default_factory=list)
    assessment_basis: AssessmentBasis = Field(default_factory=AssessmentBasis)
    base_case: Scenario
    bull_case: Scenario
    bear_case: Scenario
    what_would_change_my_view: list[ViewChanger] = Field(default_factory=list)
    uncertainty: list[AnalyzedStatement] = Field(default_factory=list)
    research_gaps: list[AnalyzedStatement] = Field(default_factory=list)
    evidence_trace: list[TraceLink] = Field(default_factory=list)
    canonical_finding_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    meta: FinalAnalystMeta = Field(default_factory=FinalAnalystMeta)

    @model_validator(mode="after")
    def _meta_flags(self) -> "FinalAnalystOutput":
        if not self.meta.no_trade_advice:
            raise ValueError("meta.no_trade_advice must be true")
        if self.analyst_mode == "grounded" and not self.meta.grounded_is_not_autonomous:
            raise ValueError("grounded mode requires grounded_is_not_autonomous=true")
        if len(self.key_drivers) > 4:
            raise ValueError("key_drivers must be at most 4")
        if len(self.core_tensions) > 3:
            raise ValueError("core_tensions must be at most 3")
        return self
