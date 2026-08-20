"""Structured Debate Engine: Claims → Challenges → Rebuttals (max 2 debate rounds)."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evidence.pack import EvidencePack
from research.schemas import FundamentalResearch, MarketResearch

from debate.bear_agent import BearAgent
from debate.bull_agent import BullAgent
from debate.context import build_shared_context, index_pack
from debate.evidence_weight import evidence_weight_breakdown
from debate.grounded import synthesize_debate_summary
from debate.schemas import (
    DebateExecutionMeta,
    DebateResult,
    EvidenceWeightEntry,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"


def _load_json_model(path: Path, model_cls):
    return model_cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


def collect_cited_ids(result: DebateResult) -> set[str]:
    ids: set[str] = set()
    for c in result.bull.claims + result.bear.claims:
        ids.update(c.evidence_ids)
    for ch in result.challenges:
        ids.update(ch.evidence_ids)
    for rb in result.rebuttals:
        ids.update(rb.evidence_ids)
    return ids


async def run_debate(
    pack: EvidencePack,
    fundamental: FundamentalResearch,
    market: MarketResearch,
    *,
    bull_agent: BullAgent | None = None,
    bear_agent: BearAgent | None = None,
) -> DebateResult:
    """
    Round structure (max 2 debate rounds after claims):
      Round 1: Claims (parallel)
      Round 2: Challenges (parallel)
      Round 3: Rebuttals (parallel)
    Then stop. No infinite loop. No Final Analyst.
    """
    bull_agent = bull_agent or BullAgent()
    bear_agent = bear_agent or BearAgent()

    # Identical shared context object for both agents
    shared_context = build_shared_context(pack, fundamental, market)

    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    rounds: list[str] = []

    # Round 1 — Claims (parallel)
    bull, bear = await asyncio.gather(
        bull_agent.research(pack, fundamental, market, shared_context=shared_context),
        bear_agent.research(pack, fundamental, market, shared_context=shared_context),
    )
    rounds.append("claims")

    # Round 2 — Challenges (parallel)
    bull_challenges, bear_challenges = await asyncio.gather(
        bull_agent.challenge(pack, bull, bear),
        bear_agent.challenge(pack, bull, bear),
    )
    challenges = list(bull_challenges) + list(bear_challenges)
    rounds.append("challenges")

    # Round 3 — Rebuttals (parallel); end of max 2 debate rounds
    bull_rebuttals, bear_rebuttals = await asyncio.gather(
        bull_agent.rebut(pack, bull, bear, challenges),
        bear_agent.rebut(pack, bull, bear, challenges),
    )
    rebuttals = list(bull_rebuttals) + list(bear_rebuttals)
    rounds.append("rebuttals")

    finished = datetime.now(timezone.utc)
    duration_ms = int((time.perf_counter() - t0) * 1000)

    # Evidence weights for all cited evidence (deterministic Python)
    by_id = index_pack(pack)
    cited = set()
    for c in bull.claims + bear.claims:
        cited.update(c.evidence_ids)
    for ch in challenges:
        cited.update(ch.evidence_ids)
    for rb in rebuttals:
        cited.update(rb.evidence_ids)

    weights: list[EvidenceWeightEntry] = []
    for eid in sorted(cited):
        ev = by_id.get(eid)
        if not ev:
            continue
        breakdown = evidence_weight_breakdown(ev)
        weights.append(EvidenceWeightEntry.model_validate(breakdown))

    summary = synthesize_debate_summary(pack, bull, bear, challenges)

    return DebateResult(
        stock_code=pack.stock_code,
        bull=bull,
        bear=bear,
        challenges=challenges,
        rebuttals=rebuttals,
        evidence_weights=weights,
        debate_summary=summary,
        execution=DebateExecutionMeta(
            parallel_claims=True,
            parallel_challenges=True,
            parallel_rebuttals=True,
            max_rounds=2,
            rounds_executed=rounds,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            duration_ms=duration_ms,
        ),
        metadata={},
    )


def save_debate_outputs(result: DebateResult, *, out_dir: Path | None = None) -> dict[str, Path]:
    out_dir = out_dir or EXAMPLES
    out_dir.mkdir(parents=True, exist_ok=True)
    code = result.stock_code
    paths = {
        "bull": out_dir / f"{code}_bull.json",
        "bear": out_dir / f"{code}_bear.json",
        "debate": out_dir / f"{code}_debate.json",
    }
    paths["bull"].write_text(
        json.dumps(result.bull.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["bear"].write_text(
        json.dumps(result.bear.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["debate"].write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return paths


async def _amain(symbol: str) -> None:
    pack = EvidencePack.load_json(EXAMPLES / f"{symbol}_evidence_pack.json")
    fundamental = _load_json_model(EXAMPLES / f"{symbol}_fundamental_research.json", FundamentalResearch)
    market = _load_json_model(EXAMPLES / f"{symbol}_market_research.json", MarketResearch)
    result = await run_debate(pack, fundamental, market)
    paths = save_debate_outputs(result)
    print(
        json.dumps(
            {
                "stock_code": symbol,
                "paths": {k: str(v) for k, v in paths.items()},
                "bull_claims": len(result.bull.claims),
                "bear_claims": len(result.bear.claims),
                "challenges": len(result.challenges),
                "rebuttals": len(result.rebuttals),
                "execution": result.execution.model_dump() if result.execution else None,
                "debate_summary": result.debate_summary.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Bull/Bear structured debate")
    parser.add_argument("--symbol", default="600519")
    args = parser.parse_args()
    asyncio.run(_amain(args.symbol))


if __name__ == "__main__":
    main()
