"""Bull-side equity researcher. Shared Evidence only; no new facts."""

from __future__ import annotations

import json
from typing import Any

from evidence.pack import EvidencePack
from research.llm import LLMClient
from research.schemas import FundamentalResearch, MarketResearch

from debate.context import build_shared_context
from debate.grounded import synthesize_bull, synthesize_bull_challenges, synthesize_rebuttals
from debate.schemas import BearResearch, BullResearch, Challenge, Rebuttal

BULL_SYSTEM = """你是一名 Bull-side Equity Researcher。
你不是证明股票一定会上涨。
你的任务是：在现有 Evidence / Fundamental Research / Market Research 中，
寻找能够支持公司投资价值的事实，并构建最强 Bull Case。

规则：
1. 只能使用提供的材料
2. 不得联网、不得创造新事实、不得修改 Evidence
3. 每个 Claim 必须引用 evidence_id
4. 承认明显负面证据
5. 最多 3 个核心 Bull Claims
6. 禁止输出 BUY/SELL/目标价/投资建议
"""


class BullAgent:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm  # optional; default uses grounded synthesizer

    async def research(
        self,
        pack: EvidencePack,
        fundamental: FundamentalResearch,
        market: MarketResearch,
        *,
        shared_context: dict[str, Any] | None = None,
    ) -> BullResearch:
        ctx = shared_context if shared_context is not None else build_shared_context(pack, fundamental, market)
        if self.llm is not None:
            user = json.dumps(
                {
                    "agent": "bull",
                    "task": "Produce BullResearch with <=3 claims; each claim cites evidence_ids.",
                    "context": ctx,
                },
                ensure_ascii=False,
            )
            try:
                result = await self.llm.generate(BULL_SYSTEM, user, BullResearch)
                if result.stock_code != pack.stock_code:
                    result = result.model_copy(update={"stock_code": pack.stock_code})
                return result
            except Exception:
                pass
        # Grounded path ignores unused ctx fields but identity of inputs is guaranteed by caller
        _ = ctx
        return synthesize_bull(pack, fundamental, market)

    async def challenge(
        self,
        pack: EvidencePack,
        bull: BullResearch,
        bear: BearResearch,
    ) -> list[Challenge]:
        return synthesize_bull_challenges(pack, bull, bear)

    async def rebut(
        self,
        pack: EvidencePack,
        bull: BullResearch,
        bear: BearResearch,
        challenges: list[Challenge],
    ) -> list[Rebuttal]:
        mine = [c for c in challenges if c.challenger == "bear"]
        all_rebs = synthesize_rebuttals(pack, bull, bear, mine)
        return [r for r in all_rebs if r.author == "bull"]
