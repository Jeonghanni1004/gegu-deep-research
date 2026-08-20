"""Parallel runner for Fundamental + Market agents."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

from evidence.pack import EvidencePack
from evidence.schema import utc_now_iso

from research.fundamental_agent import FundamentalAgent
from research.llm import LLMClient, create_llm_client
from research.market_agent import MarketAgent
from research.schemas import ParallelExecutionMeta, ParallelResearchResult
from research.time_context import resolve_as_of

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"


async def run_parallel_research(
    pack: EvidencePack,
    *,
    as_of: str | date | None = None,
    llm: LLMClient | None = None,
    fundamental_llm: LLMClient | None = None,
    market_llm: LLMClient | None = None,
) -> ParallelResearchResult:
    """Truly parallel: asyncio.gather; agents do not wait on each other."""
    as_of_date = resolve_as_of(pack, as_of)
    shared = llm or create_llm_client(mode="grounded", pack_for_validation=pack)
    fund_agent = FundamentalAgent(llm=fundamental_llm or shared)
    mkt_agent = MarketAgent(llm=market_llm or shared)

    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    fundamental, market = await asyncio.gather(
        fund_agent.research(pack, as_of=as_of_date),
        mkt_agent.research(pack, as_of=as_of_date),
    )
    finished = datetime.now(timezone.utc)
    duration_ms = int((time.perf_counter() - t0) * 1000)

    return ParallelResearchResult(
        stock_code=pack.stock_code,
        research_as_of_date=as_of_date.isoformat(),
        fundamental=fundamental,
        market=market,
        execution=ParallelExecutionMeta(
            parallel=True,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            duration_ms=duration_ms,
            research_as_of_date=as_of_date.isoformat(),
        ),
    )


def save_research_outputs(result: ParallelResearchResult, *, out_dir: Path | None = None) -> dict[str, Path]:
    out_dir = out_dir or EXAMPLES
    out_dir.mkdir(parents=True, exist_ok=True)
    code = result.stock_code
    paths = {
        "fundamental": out_dir / f"{code}_fundamental_research.json",
        "market": out_dir / f"{code}_market_research.json",
        "parallel": out_dir / f"{code}_parallel_research.json",
    }
    paths["fundamental"].write_text(
        json.dumps(result.fundamental.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["market"].write_text(
        json.dumps(result.market.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["parallel"].write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return paths


async def _amain(symbol: str, pack_path: Path | None, as_of: str | None) -> None:
    path = pack_path or (EXAMPLES / f"{symbol}_evidence_pack.json")
    pack = EvidencePack.load_json(path)
    result = await run_parallel_research(pack, as_of=as_of)
    paths = save_research_outputs(result)
    print(
        json.dumps(
            {
                "stock_code": symbol,
                "research_as_of_date": result.research_as_of_date,
                "generated_at": utc_now_iso(),
                "paths": {k: str(v) for k, v in paths.items()},
                "execution": result.execution.model_dump(),
                "fundamental_summary": result.fundamental.summary,
                "market_summary": result.market.summary,
                "fundamental_cross": len(result.fundamental.cross_evidence_findings),
                "market_tensions": len(result.market.research_tensions),
                "excluded_audit": len(result.fundamental.excluded_audit) + len(result.market.excluded_audit),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Fundamental + Market agents in parallel")
    parser.add_argument("--symbol", default="600519")
    parser.add_argument("--pack", default=None, help="Path to evidence pack JSON")
    parser.add_argument("--as-of", default=None, help="research_as_of_date YYYY-MM-DD (default: pack.generated_at date)")
    args = parser.parse_args()
    pack_path = Path(args.pack) if args.pack else None
    asyncio.run(_amain(args.symbol, pack_path, args.as_of))


if __name__ == "__main__":
    main()
