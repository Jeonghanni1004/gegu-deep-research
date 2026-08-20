"""Final Analyst agent."""

from __future__ import annotations

from debate.schemas import DebateResult
from evidence.pack import EvidencePack
from research.schemas import FundamentalResearch, MarketResearch

from final_analyst.contract import FinalAnalystInput, build_final_analyst_input
from final_analyst.llm import FALLMClient, create_fa_llm_client
from final_analyst.schemas import FinalAnalystOutput


class FinalAnalystAgent:
    def __init__(self, llm: FALLMClient | None = None):
        self.llm = llm

    async def analyze(
        self,
        *,
        fundamental: FundamentalResearch,
        market: MarketResearch,
        debate: DebateResult,
        mode: str = "grounded",
        pack_for_validation: EvidencePack | None = None,
        fa_input: FinalAnalystInput | None = None,
    ) -> FinalAnalystOutput:
        inp = fa_input or build_final_analyst_input(
            fundamental=fundamental,
            market=market,
            debate=debate,
            mode="openai" if mode == "openai" else "grounded",
        )
        llm = self.llm or create_fa_llm_client(mode, pack_for_validation=pack_for_validation)
        return await llm.generate(inp)
