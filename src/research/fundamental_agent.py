"""Fundamental Agent: Evidence Pack only → FundamentalResearch."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from evidence.pack import EvidencePack

from research.citation import validate_research_citations
from research.context import build_fundamental_context
from research.llm import SYSTEM_PROMPT_COMMON, LLMClient, create_llm_client
from research.schemas import FundamentalResearch

FUNDAMENTAL_SYSTEM = (
    SYSTEM_PROMPT_COMMON
    + """
你是 Fundamental Agent，只从基本面角度输出 Research View。
必须使用提供的 research_as_of_date 与分窗口 evidence_groups / cross_evidence_bundles。
优先输出 cross_evidence_findings 与 research_tensions。
覆盖：盈利能力×增长、现金流×利润质量、资产负债表×经营风险、估值×盈利/增长（证据不足则 insufficient_evidence）。
不要输出 BUY/SELL。不要复述单条 Evidence 原文作为唯一分析。
"""
)


class FundamentalAgent:
    """Reads Evidence via Retriever/context only. Never calls market data APIs."""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm

    def build_context(self, pack: EvidencePack, *, as_of: str | date | None = None) -> dict[str, Any]:
        return build_fundamental_context(pack, as_of=as_of)

    async def research(
        self,
        pack: EvidencePack,
        *,
        as_of: str | date | None = None,
    ) -> FundamentalResearch:
        ctx = self.build_context(pack, as_of=as_of)
        llm = self.llm or create_llm_client(mode="grounded", pack_for_validation=pack)
        payload = {
            **ctx,
            "agent": "fundamental",
            "task": (
                "Produce FundamentalResearch JSON with research_as_of_date, "
                "cross_evidence_findings, research_tensions, excluded_audit. "
                "Cite every fact used in claim/reasoning/interpretation."
            ),
        }
        user_prompt = json.dumps(payload, ensure_ascii=False)
        result = await llm.generate(FUNDAMENTAL_SYSTEM, user_prompt, FundamentalResearch)
        updates: dict[str, Any] = {}
        if result.stock_code != pack.stock_code:
            updates["stock_code"] = pack.stock_code
        if not result.research_as_of_date:
            updates["research_as_of_date"] = ctx["research_as_of_date"]
        if updates:
            result = result.model_copy(update=updates)
        # Always enforce citation completeness at agent boundary
        errors = validate_research_citations(result, pack)
        if errors:
            raise ValueError("FundamentalAgent citation errors: " + "; ".join(errors[:8]))
        return result
