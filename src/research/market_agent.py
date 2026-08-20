"""Market Agent: Evidence Pack only → MarketResearch."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from evidence.pack import EvidencePack

from research.citation import validate_research_citations
from research.context import build_market_context
from research.llm import SYSTEM_PROMPT_COMMON, LLMClient, create_llm_client
from research.schemas import MarketResearch

MARKET_SYSTEM = (
    SYSTEM_PROMPT_COMMON
    + """
你是 Market Agent，只从市场价格与技术面角度输出 Research View。
必须使用 research_as_of_date 与分窗口 evidence_groups（含 news_current_7d / news_previous_8_30d）。
优先输出价格×均线、短期×长期趋势、估值×价格等跨证据关系。
宏观背景不得冒充公司基本面；irrelevant 资讯不得进入核心判断。
不要输出 BUY/SELL。
"""
)


class MarketAgent:
    """Reads Evidence via Retriever/context only. Never calls market data APIs."""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm

    def build_context(self, pack: EvidencePack, *, as_of: str | date | None = None) -> dict[str, Any]:
        return build_market_context(pack, as_of=as_of)

    async def research(
        self,
        pack: EvidencePack,
        *,
        as_of: str | date | None = None,
    ) -> MarketResearch:
        ctx = self.build_context(pack, as_of=as_of)
        llm = self.llm or create_llm_client(mode="grounded", pack_for_validation=pack)
        payload = {
            **ctx,
            "agent": "market",
            "task": (
                "Produce MarketResearch JSON with research_as_of_date, news_narrative, "
                "cross_evidence_findings, research_tensions, excluded_audit."
            ),
        }
        user_prompt = json.dumps(payload, ensure_ascii=False)
        result = await llm.generate(MARKET_SYSTEM, user_prompt, MarketResearch)
        updates: dict[str, Any] = {}
        if result.stock_code != pack.stock_code:
            updates["stock_code"] = pack.stock_code
        if not result.research_as_of_date:
            updates["research_as_of_date"] = ctx["research_as_of_date"]
        if updates:
            result = result.model_copy(update=updates)
        errors = validate_research_citations(result, pack)
        if errors:
            raise ValueError("MarketAgent citation errors: " + "; ".join(errors[:8]))
        return result
