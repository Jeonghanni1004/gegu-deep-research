"""Final Analyst input assembly from ResearchOutputContract + DebateResult."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from debate.schemas import DebateResult
from research.contract import ResearchOutputContract, build_research_output_contract
from research.schemas import FundamentalResearch, MarketResearch


class FinalAnalystInput(BaseModel):
    """FA primary input. EvidencePack is not a primary research source."""

    model_config = ConfigDict(extra="forbid")

    stock_code: str
    research_as_of_date: str
    mode: Literal["grounded", "openai"] = "grounded"
    fundamental: ResearchOutputContract
    market: ResearchOutputContract
    debate: DebateResult
    assembly_notes: list[str] = Field(
        default_factory=lambda: [
            "canonical_findings is the only authoritative research expression",
            "compat sections must not be scanned for new facts",
            "EvidencePack is not primary input; evidence_id lookup is read-only for citation",
            "weight is selection priority already applied upstream, not investment probability",
            "grounded synthesizer is deterministic, not autonomous research",
        ]
    )

    @model_validator(mode="after")
    def _as_of_consistent(self) -> "FinalAnalystInput":
        if self.fundamental.research_as_of_date != self.market.research_as_of_date:
            raise ValueError(
                "fail-closed: fundamental/market research_as_of_date mismatch: "
                f"{self.fundamental.research_as_of_date} vs {self.market.research_as_of_date}"
            )
        if self.research_as_of_date != self.fundamental.research_as_of_date:
            raise ValueError("fail-closed: top-level research_as_of_date mismatch")
        if self.fundamental.stock_code != self.market.stock_code:
            raise ValueError("fail-closed: stock_code mismatch across contracts")
        if self.stock_code != self.fundamental.stock_code:
            raise ValueError("fail-closed: stock_code mismatch")
        return self


def build_final_analyst_input(
    *,
    fundamental: FundamentalResearch,
    market: MarketResearch,
    debate: DebateResult,
    mode: Literal["grounded", "openai"] = "grounded",
    fund_time_context: dict[str, Any] | None = None,
    market_time_context: dict[str, Any] | None = None,
) -> FinalAnalystInput:
    """Assemble FA input. Does not read EvidencePack."""
    fund_c = build_research_output_contract(fundamental, time_context=fund_time_context)
    mkt_c = build_research_output_contract(market, time_context=market_time_context)
    if fund_c.research_as_of_date != mkt_c.research_as_of_date:
        raise ValueError(
            "fail-closed: fundamental/market research_as_of_date mismatch before FA assembly"
        )
    return FinalAnalystInput(
        stock_code=fundamental.stock_code,
        research_as_of_date=fund_c.research_as_of_date,
        mode=mode,
        fundamental=fund_c,
        market=mkt_c,
        debate=debate,
    )


def all_canonical(inp: FinalAnalystInput) -> list:
    return list(inp.fundamental.canonical_findings) + list(inp.market.canonical_findings)


def canonical_index(inp: FinalAnalystInput) -> dict[str, Any]:
    return {c.finding_id: c for c in all_canonical(inp)}
