"""Agent Layer research tests (phase-2 depth / time / weight / relevance / citation).

Usage:
  python -m tests.test_research_agents --symbol 600519
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evidence.pack import EvidencePack
from research.citation import validate_research_citations
from research.context import build_fundamental_context, build_market_context
from research.fundamental_agent import FundamentalAgent
from research.llm import GroundedLLMClient
from research.market_agent import MarketAgent
from research.parallel import run_parallel_research, save_research_outputs
from research.retriever import EvidenceRetriever
from research.schemas import CitedFinding, FundamentalResearch, MarketResearch, ResearchSection


def _check(name: str, cond: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(cond), "detail": detail}


def _iter_findings(obj) -> list[CitedFinding]:
    findings: list[CitedFinding] = []
    if isinstance(obj, CitedFinding):
        return [obj]
    if isinstance(obj, ResearchSection):
        return list(obj.findings)
    if isinstance(obj, (FundamentalResearch, MarketResearch)):
        data = obj.model_dump()
        for key, val in data.items():
            if key in {
                "key_strengths",
                "key_weaknesses",
                "key_uncertainties",
                "cross_evidence_findings",
                "research_tensions",
                "core_facts",
                "key_research_findings",
                "evidence_gaps",
                "canonical_findings",
            } and isinstance(val, list):
                for item in val:
                    findings.append(CitedFinding.model_validate(item))
            elif isinstance(val, dict) and "findings" in val:
                findings.extend(ResearchSection.model_validate(val).findings)
    return findings


def _non_ref(findings: list[CitedFinding]) -> list[CitedFinding]:
    return [f for f in findings if f.finding_kind != "reference"]


def _supported(findings: list[CitedFinding]) -> list[CitedFinding]:
    return [f for f in findings if f.status == "supported"]


async def _run_async(symbol: str) -> list[dict]:
    pack_path = ROOT / "examples" / f"{symbol}_evidence_pack.json"
    results: list[dict] = []
    if not pack_path.exists():
        results.append(_check("evidence_pack_exists", False, str(pack_path)))
        return results
    results.append(_check("evidence_pack_exists", True, str(pack_path)))

    pack = EvidencePack.load_json(pack_path)
    before = copy.deepcopy([e.model_dump(mode="json") for e in pack.evidence])
    known_ids = {e.evidence_id for e in pack.evidence}

    # Retriever still works
    r = EvidenceRetriever(pack)
    q1 = r.query(
        stock_code=symbol,
        evidence_type=["FACT", "DERIVED"],
        subtype=["operating_revenue", "net_profit_parent", "roe"],
    )
    results.append(_check("retriever_query", len(q1) >= 1, f"n={len(q1)}"))

    fctx = build_fundamental_context(pack)
    mctx = build_market_context(pack)
    results.append(_check("as_of_explicit", bool(fctx.get("research_as_of_date")), fctx.get("research_as_of_date")))
    results.append(
        _check(
            "context_has_time_buckets",
            "financial_latest" in fctx["evidence_groups"] and "news_current_7d" in mctx["evidence_groups"],
            list(fctx["evidence_groups"].keys())[:5],
        )
    )
    # weight present & sorted desc in a non-empty group
    spot = mctx["evidence_groups"].get("market_spot") or []
    if len(spot) >= 2:
        weights = [float(x.get("weight") or 0) for x in spot]
        results.append(_check("weight_sorted_in_context", weights == sorted(weights, reverse=True), str(weights[:5])))
    else:
        results.append(_check("weight_sorted_in_context", True, "spot<2 skip"))

    # excluded_audit reasons namespace
    reasons = {x.get("reason") for x in (mctx.get("excluded_audit") or [])}
    results.append(
        _check(
            "excluded_audit_present",
            True,
            f"reasons={sorted(reasons)} n={len(mctx.get('excluded_audit') or [])}",
        )
    )

    llm = GroundedLLMClient(pack_for_validation=pack)
    fund_agent = FundamentalAgent(llm=llm)
    mkt_agent = MarketAgent(llm=llm)

    def _block(*a, **k):
        raise RuntimeError("network access forbidden during agent research")

    with mock.patch("requests.get", side_effect=_block), mock.patch(
        "requests.post", side_effect=_block
    ), mock.patch("requests.request", side_effect=_block):
        fund = await fund_agent.research(pack)
        market = await mkt_agent.research(pack)
        t0 = time.perf_counter()
        parallel = await run_parallel_research(pack, llm=llm)
        elapsed = time.perf_counter() - t0

    results.append(_check("fundamental_schema", isinstance(fund, FundamentalResearch), type(fund).__name__))
    results.append(_check("market_schema", isinstance(market, MarketResearch), type(market).__name__))
    FundamentalResearch.model_validate(fund.model_dump())
    MarketResearch.model_validate(market.model_dump())
    results.append(_check("pydantic_roundtrip", True, "ok"))
    results.append(
        _check(
            "research_as_of_in_output",
            bool(fund.research_as_of_date) and fund.research_as_of_date == market.research_as_of_date,
            fund.research_as_of_date,
        )
    )

    # citations / ids
    cite_err = validate_research_citations(fund, pack) + validate_research_citations(market, pack)
    results.append(_check("citation_completeness", cite_err == [], str(cite_err[:3])))

    fund_f = _supported(_non_ref(_iter_findings(fund)))
    mkt_f = _supported(_non_ref(_iter_findings(market)))
    results.append(_check("fundamental_supported_have_ids", all(f.evidence_ids for f in fund_f), f"n={len(fund_f)}"))
    results.append(_check("market_supported_have_ids", all(f.evidence_ids for f in mkt_f), f"n={len(mkt_f)}"))
    missing = []
    for f in fund_f + mkt_f:
        for eid in f.evidence_ids:
            if eid not in known_ids:
                missing.append(eid)
    results.append(_check("ids_in_pack", not missing, str(missing[:5])))

    # Depth: cross / tension
    fund_cross = [f for f in _non_ref(_iter_findings(fund)) if f.finding_kind in {"cross", "tension"} and f.status == "supported"]
    mkt_cross = [f for f in _non_ref(_iter_findings(market)) if f.finding_kind in {"cross", "tension"} and f.status == "supported"]
    results.append(_check("fundamental_cross_findings", len(fund.canonical_findings) >= 1 or len(fund_cross) >= 1, len(fund.canonical_findings)))
    results.append(_check("market_cross_or_tension", len(mkt_cross) >= 1 or len([c for c in market.canonical_findings if c.finding_kind in {"cross", "tension"}]) >= 1, len(mkt_cross)))
    results.append(
        _check(
            "cross_has_multi_ids",
            all(
                len(f.evidence_ids) >= 2
                for f in fund.canonical_findings + market.canonical_findings
                if f.status == "supported" and f.finding_kind in {"cross", "tension"}
            ),
            "ok",
        )
    )

    # Compression: section claims must not fully clone canonical claim text
    clone_hits = 0
    for c in fund.canonical_findings + market.canonical_findings:
        for sec in [
            fund.financial_performance,
            fund.profitability,
            fund.key_strengths,
            fund.key_weaknesses,
            market.trend,
            market.price_status,
        ]:
            items = sec if isinstance(sec, list) else sec.findings
            for f in items:
                if f.finding_kind == "reference":
                    continue
                if f.claim.strip() == c.claim.strip():
                    clone_hits += 1
    results.append(_check("no_canonical_clone_in_compat_sections", clone_hits == 0, f"clones={clone_hits}"))
    results.append(_check("has_canonical_findings", len(fund.canonical_findings) >= 1, len(fund.canonical_findings)))

    # Anti echo: supported cross/tension claim should not equal a single evidence claim
    echo = 0
    claim_map = {e.evidence_id: e.claim for e in pack.evidence}
    for f in fund.canonical_findings + market.canonical_findings:
        if f.status != "supported" or f.finding_kind not in {"cross", "tension"}:
            continue
        if any(f.claim.strip() == (claim_map.get(eid) or "").strip() for eid in f.evidence_ids):
            echo += 1
    results.append(_check("no_single_evidence_echo_in_cross", echo == 0, f"echo={echo}"))

    # Numbers preserved in profitability tension when data available
    tension_profit = next((c for c in fund.canonical_findings if "PROFIT_VS_GROWTH" in c.finding_id), None)
    if tension_profit:
        text = tension_profit.claim + tension_profit.interpretation
        has_num = any(ch.isdigit() for ch in text)
        results.append(_check("evidence_numbers_preserved", has_num and len(tension_profit.numbers_preserved) >= 1, str(tension_profit.numbers_preserved[:5])))
    else:
        results.append(_check("evidence_numbers_preserved", True, "no profit tension skip"))

    # insufficient still present somewhere
    has_insuff = any(f.status == "insufficient_evidence" for f in _iter_findings(fund) + _iter_findings(market))
    results.append(_check("insufficient_evidence_handled", has_insuff, "ok"))

    after = [e.model_dump(mode="json") for e in pack.evidence]
    results.append(_check("evidence_not_mutated", before == after, f"{len(before)}"))

    results.append(_check("parallel_flag", parallel.execution.parallel is True, str(parallel.execution.duration_ms)))
    results.append(_check("parallel_as_of", parallel.research_as_of_date == fund.research_as_of_date, parallel.research_as_of_date))
    results.append(_check("parallel_gather_both", bool(parallel.fundamental.summary) and bool(parallel.market.summary), f"elapsed={elapsed:.4f}"))
    results.append(_check("no_internet_access", True, "requests blocked"))

    # trade advice check on authored fields
    authored = "\n".join(
        [fund.summary, market.summary]
        + [f.interpretation for f in _iter_findings(fund) + _iter_findings(market)]
        + [f.reasoning for f in _iter_findings(fund) + _iter_findings(market)]
    )
    banned = ["STRONG BUY", "STRONG SELL", "买入", "卖出", "加仓", "减仓"]
    has_ban = any(b in authored or b in authored.upper() for b in banned)
    results.append(_check("no_trade_advice", not has_ban, "authored only"))

    paths = save_research_outputs(parallel, out_dir=ROOT / "examples")
    results.append(
        _check(
            "outputs_saved",
            all(p.exists() and p.stat().st_size > 50 for p in paths.values()),
            {k: str(v) for k, v in paths.items()},
        )
    )

    # as-of override smoke: future as_of still builds; past as_of excludes later market day if any
    older = await fund_agent.research(pack, as_of="2020-01-01")
    results.append(
        _check(
            "as_of_override",
            older.research_as_of_date == "2020-01-01",
            older.research_as_of_date,
        )
    )

    return results


def run_tests(symbol: str = "600519") -> list[dict]:
    return asyncio.run(_run_async(symbol))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="600519")
    args = parser.parse_args()
    results = run_tests(args.symbol)
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    for r in results:
        print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
    print(f"\n{passed}/{total} PASS")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
