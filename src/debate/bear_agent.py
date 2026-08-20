"""Bear-side equity researcher. Shared Evidence only; no new facts."""

from __future__ import annotations

import json
from typing import Any

from evidence.pack import EvidencePack
from research.llm import LLMClient
from research.schemas import FundamentalResearch, MarketResearch

from debate.context import build_shared_context
from debate.grounded import synthesize_bear, synthesize_bear_challenges, synthesize_rebuttals
from debate.schemas import BearResearch, BullResearch, Challenge, Rebuttal

BEAR_SYSTEM = """你是一名 Bear-side Equity Researcher。
你的任务是：在现有 Evidence / Fundamental Research / Market Research 中，
寻找能够削弱公司投资价值的事实，构建最强 Bear Case。

规则：
1. 只能使用提供的材料
2. 不得联网、不得创造新事实、不得修改 Evidence
3. 每个 Claim 必须引用 evidence_id
4. 不得为了看空而过度解读
5. 承认 Bull 可能成立的部分
6. 最多 3 个核心 Bear Claims
7. 禁止输出 BUY/SELL/目标价/投资建议
"""


class BearAgent:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm

    async def research(
        self,
        pack: EvidencePack,
        fundamental: FundamentalResearch,
        market: MarketResearch,
        *,
        shared_context: dict[str, Any] | None = None,
    ) -> BearResearch:
        ctx = shared_context if shared_context is not None else build_shared_context(pack, fundamental, market)
        if self.llm is not None:
            user = json.dumps(
                {
                    "agent": "bear",
                    "task": "Produce BearResearch with <=3 claims; each claim cites evidence_ids.",
                    "context": ctx,
                },
                ensure_ascii=False,
            )
            try:
                result = await self.llm.generate(BEAR_SYSTEM, user, BearResearch)
                if result.stock_code != pack.stock_code:
                    result = result.model_copy(update={"stock_code": pack.stock_code})
                return result
            except Exception:
                pass
        _ = ctx
        return synthesize_bear(pack, fundamental, market)

    async def challenge(
        self,
        pack: EvidencePack,
        bull: BullResearch,
        bear: BearResearch,
    ) -> list[Challenge]:
        return synthesize_bear_challenges(pack, bull, bear)

    async def rebut(
        self,
        pack: EvidencePack,
        bull: BullResearch,
        bear: BearResearch,
        challenges: list[Challenge],
    ) -> list[Rebuttal]:
        mine = [c for c in challenges if c.challenger == "bull"]
        all_rebs = synthesize_rebuttals(pack, bull, bear, mine)
        return [r for r in all_rebs if r.author == "bear"]
