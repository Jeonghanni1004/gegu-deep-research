"""Build demo artifacts for one A-share symbol (no OpenAI).

Steps:
  1) AKShare bundle
  2) Eastmoney / CLS / THS market PoCs (retarget keywords for the symbol)
  3) EvidencePack
  4) Grounded Research → Debate → Final Analyst pipeline

Usage:
  set PYTHONPATH=src
  python scripts/build_demo_symbol.py --symbol 601127 --name 赛力斯
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_service.service import save_bundle
from debate.debate_engine import run_debate, save_debate_outputs
from evidence.normalizer import build_evidence_pack, save_evidence_pack
from evidence.pack import EvidencePack
from final_analyst.dotenv_load import load_dotenv
from final_analyst.pipeline import run_production_pipeline
from poc_market_sources import cls_poc, eastmoney_poc
from poc_market_sources.cls_poc import run_cls_poc
from poc_market_sources.common import save_json
from poc_market_sources.eastmoney_poc import run_eastmoney_poc
from poc_market_sources.run_poc import (
    _announcements,
    _events,
    _news_from_cls,
    _news_from_eastmoney,
)
from poc_market_sources.ths_poc import run_ths_poc
from research.parallel import run_parallel_research, save_research_outputs
from research.schemas import FundamentalResearch, MarketResearch

DEFAULT_ALIASES = {
    "601127": ["赛力斯", "问界", "AITO", "华为汽车", "新能源汽车"],
}


def _retarget_sources(symbol: str, name: str, aliases: list[str]) -> None:
    """Point PoC keyword filters at the target stock (modules default to 茅台)."""
    keys = [name, symbol, *aliases]
    keys = [k for i, k in enumerate(keys) if k and k not in keys[:i]]

    eastmoney_poc.STOCK_CODE = symbol
    eastmoney_poc.STOCK_NAME = name
    cls_poc.STOCK_CODE = symbol
    cls_poc.STOCK_NAME = name
    cls_poc.KEYWORDS = keys


def build_market_inputs(symbol: str, name: str, aliases: list[str]) -> dict:
    _retarget_sources(symbol, name, aliases)
    print(f"[1/4] Eastmoney PoC for {symbol} {name} ...")
    em = run_eastmoney_poc(symbol)
    em["stock_code"] = symbol
    em["stock_name"] = name
    save_json(f"{symbol}_eastmoney_test.json", em)

    print(f"[2/4] CLS PoC for {symbol} ...")
    cls = run_cls_poc(symbol)
    cls["stock_code"] = symbol
    cls["stock_name"] = name
    save_json(f"{symbol}_cls_test.json", cls)

    print(f"[3/4] THS PoC for {symbol} ...")
    ths = run_ths_poc(symbol)
    ths["stock_code"] = symbol
    save_json(f"{symbol}_ths_test.json", ths)

    market_info = {
        "stock_code": symbol,
        "stock_name": name,
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "news": _news_from_eastmoney(em) + _news_from_cls(cls),
        "announcements": _announcements(em),
        "consensus": ths.get("consensus_normalized") or [],
        "events": _events(em),
        "source_status": {
            "eastmoney": em.get("attempts"),
            "cls": cls.get("attempts"),
            "ths": ths.get("attempts"),
        },
    }
    save_json(f"{symbol}_market_information.json", market_info)
    print(f"Saved {symbol}_market_information.json")
    return {
        "eastmoney": em,
        "cls": cls,
        "ths": ths,
        "market_info": market_info,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build demo symbol artifacts (grounded, no OpenAI)")
    parser.add_argument("--symbol", default="601127")
    parser.add_argument("--name", default="赛力斯")
    parser.add_argument(
        "--alias",
        action="append",
        default=None,
        help="Extra relevance keywords (repeatable)",
    )
    parser.add_argument("--skip-pipeline", action="store_true", help="Only build EvidencePack")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    symbol = "".join(c for c in args.symbol if c.isdigit()).zfill(6)
    name = args.name.strip() or symbol
    aliases = list(args.alias or DEFAULT_ALIASES.get(symbol, []))

    print(f"=== Building demo artifacts for {symbol} {name} ===")
    print(f"Aliases: {aliases}")

    print("[0/4] Saving AKShare bundle ...")
    bundle_path = save_bundle(symbol)
    print(f"Saved bundle -> {bundle_path}")

    meta = build_market_inputs(symbol, name, aliases)
    news_n = len((meta["market_info"].get("news") or []))
    ann_n = len((meta["market_info"].get("announcements") or []))
    cons_n = len((meta["market_info"].get("consensus") or []))
    print(f"Market inputs: news={news_n} announcements={ann_n} consensus={cons_n}")

    print("[4/4] Building EvidencePack ...")
    pack = build_evidence_pack(symbol=symbol)
    out = save_evidence_pack(pack)
    print(f"Saved EvidencePack -> {out} (n={len(pack.evidence)})")

    if args.skip_pipeline:
        print("Skipped grounded pipeline (--skip-pipeline)")
        return 0

    print("Running grounded Research (no OpenAI) ...")
    pack_obj = EvidencePack.load_json(out)
    research = asyncio.run(run_parallel_research(pack_obj))
    research_paths = save_research_outputs(research)
    print("Saved research:", {k: str(v) for k, v in research_paths.items()})

    print("Running grounded Debate ...")
    fund = FundamentalResearch.model_validate(
        json.loads(research_paths["fundamental"].read_text(encoding="utf-8"))
    )
    market = MarketResearch.model_validate(json.loads(research_paths["market"].read_text(encoding="utf-8")))
    debate = asyncio.run(run_debate(pack_obj, fund, market))
    debate_paths = save_debate_outputs(debate)
    print("Saved debate:", {k: str(v) for k, v in debate_paths.items()})

    print("Running grounded Final Analyst production pipeline ...")
    result = asyncio.run(
        run_production_pipeline(
            symbol,
            mode="grounded",
            as_of=None,
            write_trace=True,
            allow_fallback=True,
        )
    )
    summary = {
        "status": result.status,
        "mode": result.mode,
        "stock": result.stock,
        "as_of": result.as_of,
        "failure_code": result.failure_code,
        "trace_path": result.trace_path,
        "gate": result.gate,
        "notes": (result.notes or [])[:8],
    }
    if result.output is not None:
        summary["executive"] = (result.output.executive_assessment.text or "")[:240]
        summary["analyst_mode"] = result.output.analyst_mode
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    fa_path = ROOT / "examples" / f"{symbol}_final_analyst.json"
    if result.status not in {"PASS", "FALLBACK_PASS"} or not fa_path.exists():
        print(f"PIPELINE INCOMPLETE: status={result.status} fa_exists={fa_path.exists()}")
        return 1

    # Quick demo list check
    sys.path.insert(0, str(ROOT / "web"))
    from assemble import list_studies, resolve_symbol

    studies = list_studies()
    print("Demo studies:", studies)
    print("resolve 赛力斯 ->", resolve_symbol("赛力斯"), "resolve 601127 ->", resolve_symbol("601127"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
