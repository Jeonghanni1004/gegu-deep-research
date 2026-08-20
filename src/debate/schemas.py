"""Pydantic schemas for Bull/Bear adversarial debate."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Stance = Literal["bull", "bear"]
ChallengeType = Literal[
    "evidence_conflict",
    "evidence_insufficient",
    "interpretation_conflict",
    "time_sensitivity",
    "assumption",
    "scope",
]
ResponseType = Literal["accept", "partially_accept", "reject"]
Challenger = Literal["bull", "bear"]


def _forbid_trade_advice(text: str, where: str) -> str:
    upper = text.upper()
    for banned in ("BUY", "SELL", "STRONG BUY", "STRONG SELL", "加仓", "减仓", "买入", "卖出", "目标价"):
        if banned in upper or banned in text:
            raise ValueError(f"{where} must not contain trade advice / target price: {banned}")
    return text


class ResearchClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    stance: Stance
    claim: str
    reasoning: str
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0)
    # Links to Research canonical_findings (optional; empty if not tension-aligned)
    canonical_finding_ids: list[str] = Field(default_factory=list)

    @field_validator("claim", "reasoning")
    @classmethod
    def _no_advice(cls, v: str) -> str:
        return _forbid_trade_advice(v, "ResearchClaim")


class BullResearch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str
    stance: Literal["bull"] = "bull"
    thesis: str
    claims: list[ResearchClaim] = Field(default_factory=list, max_length=3)
    key_risks: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)

    @field_validator("thesis")
    @classmethod
    def _no_advice(cls, v: str) -> str:
        return _forbid_trade_advice(v, "BullResearch.thesis")

    @model_validator(mode="after")
    def _claims_are_bull(self) -> "BullResearch":
        for c in self.claims:
            if c.stance != "bull":
                raise ValueError(f"Bull claim {c.claim_id} must have stance=bull")
            if not c.evidence_ids:
                raise ValueError(f"Bull claim {c.claim_id} must cite evidence_ids")
        if len(self.claims) > 3:
            raise ValueError("BullResearch allows at most 3 claims")
        return self


class BearResearch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str
    stance: Literal["bear"] = "bear"
    thesis: str
    claims: list[ResearchClaim] = Field(default_factory=list, max_length=3)
    key_opportunities: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)

    @field_validator("thesis")
    @classmethod
    def _no_advice(cls, v: str) -> str:
        return _forbid_trade_advice(v, "BearResearch.thesis")

    @model_validator(mode="after")
    def _claims_are_bear(self) -> "BearResearch":
        for c in self.claims:
            if c.stance != "bear":
                raise ValueError(f"Bear claim {c.claim_id} must have stance=bear")
            if not c.evidence_ids:
                raise ValueError(f"Bear claim {c.claim_id} must cite evidence_ids")
        if len(self.claims) > 3:
            raise ValueError("BearResearch allows at most 3 claims")
        return self


class Challenge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: str
    challenger: Challenger
    target_claim_id: str
    challenge_type: ChallengeType
    argument: str
    evidence_ids: list[str] = Field(default_factory=list)
    strength: float = Field(ge=0.0, le=1.0)

    @field_validator("argument")
    @classmethod
    def _no_advice(cls, v: str) -> str:
        return _forbid_trade_advice(v, "Challenge.argument")


class Rebuttal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rebuttal_id: str
    author: Challenger
    target_challenge_id: str
    response_type: ResponseType
    argument: str
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("argument")
    @classmethod
    def _no_advice(cls, v: str) -> str:
        return _forbid_trade_advice(v, "Rebuttal.argument")


class EvidenceWeightEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    reliability: str
    freshness: str
    reliability_weight: float
    freshness_weight: float
    weight: float


class DebateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shared_facts: list[str] = Field(default_factory=list)
    core_disagreements: list[str] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)

    @field_validator("shared_facts", "core_disagreements", "unresolved_issues")
    @classmethod
    def _no_advice_list(cls, values: list[str]) -> list[str]:
        for v in values:
            _forbid_trade_advice(v, "DebateSummary")
        return values


class DebateExecutionMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parallel_claims: bool = True
    parallel_challenges: bool = True
    parallel_rebuttals: bool = True
    max_rounds: int = 2
    rounds_executed: list[str] = Field(default_factory=list)
    started_at: str
    finished_at: str
    duration_ms: int


class DebateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str
    bull: BullResearch
    bear: BearResearch
    challenges: list[Challenge] = Field(default_factory=list)
    rebuttals: list[Rebuttal] = Field(default_factory=list)
    evidence_weights: list[EvidenceWeightEntry] = Field(default_factory=list)
    debate_summary: DebateSummary
    execution: DebateExecutionMeta | None = None
    # Explicitly forbid score/probability fields via schema discipline (also validated in tests)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _no_score_fields(self) -> "DebateResult":
        forbidden = {
            "bull_score",
            "bear_score",
            "bull_probability",
            "bear_probability",
            "buy_probability",
            "sell_probability",
        }
        bad = forbidden.intersection(self.metadata.keys())
        if bad:
            raise ValueError(f"DebateResult must not contain score/probability fields: {sorted(bad)}")
        return self
