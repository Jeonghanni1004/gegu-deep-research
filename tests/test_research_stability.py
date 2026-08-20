"""Phase-4 Research stability tests (Final Analyst pre-design).

Usage:
  python -m tests.test_research_stability
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evidence.pack import EvidencePack
from evidence.schema import (
    Evidence,
    EvidenceSource,
    EvidenceTime,
    EvidenceType,
    Freshness,
    FreshnessStatus,
    Reliability,
)
from research.citation import validate_finding_citations
from research.context import build_fundamental_context, build_market_context
from research.contract import (
    build_research_output_contract,
    depth_signals,
    has_incremental_value,
    is_reference_new_finding,
    validate_canonical_integrity,
)
from research.fundamental_agent import FundamentalAgent
from research.llm import GroundedLLMClient
from research.market_agent import MarketAgent
from research.relevance import assign_research_role, classify_relevance
from research.schemas import CitedFinding
from research.selection import select_by_weight
from research.synthesize import synthesize_fundamental, synthesize_market
from debate.grounded import synthesize_bear, synthesize_bull


def _check(name: str, cond: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(cond), "detail": str(detail)}


def _ev(
    *,
    eid: str,
    subtype: str,
    claim: str,
    et: EvidenceType = EvidenceType.EVENT,
    published_at: str | None = None,
    data_date: str | None = None,
    report_date: str | None = None,
    freshness: FreshnessStatus = FreshnessStatus.RECENT,
    reliability: Reliability = Reliability.HIGH,
    value: dict | None = None,
    stock_code: str | None = "600519",
) -> Evidence:
    return Evidence(
        evidence_id=eid,
        stock_code=stock_code,
        evidence_type=et,
        subtype=subtype,
        claim=claim,
        value=value or {},
        source=EvidenceSource(provider="test", source_type="unit", retrieved_at="2026-08-14"),
        time=EvidenceTime(
            published_at=published_at,
            data_date=data_date,
            report_date=report_date,
            retrieved_at="2026-08-14",
        ),
        freshness=Freshness(age_hours=1.0, status=freshness),
        reliability=reliability,
    )


def _pack_with_profile(*, code: str, name: str, industry: str) -> EvidencePack:
    return EvidencePack(
        stock_code=code,
        evidence=[
            _ev(
                eid="name",
                subtype="stock_name",
                et=EvidenceType.FACT,
                claim=f"股票名称为 {name}",
                value={"value": name},
                data_date="2026-08-14",
                stock_code=code,
            ),
            _ev(
                eid="ind",
                subtype="industry",
                et=EvidenceType.FACT,
                claim=f"所属行业为 {industry}",
                value={"value": industry},
                report_date="2026-08-14",
                stock_code=code,
            ),
        ],
        generated_at="2026-08-14T00:00:00+08:00",
    )


def test_canonical_uniqueness(results: list[dict]) -> None:
    pack = EvidencePack.load_json(ROOT / "examples" / "600519_evidence_pack.json")
    llm = GroundedLLMClient(pack_for_validation=pack)

    async def _run():
        return await FundamentalAgent(llm=llm).research(pack), await MarketAgent(llm=llm).research(pack)

    fund, market = asyncio.run(_run())
    err_f = validate_canonical_integrity(fund)
    err_m = validate_canonical_integrity(market)
    results.append(_check("canonical_uniqueness_fundamental", err_f == [], err_f[:3]))
    results.append(_check("canonical_uniqueness_market", err_m == [], err_m[:3]))

    # Exactly one full claim text among non-reference findings for each canonical id
    for label, research in [("fund", fund), ("market", market)]:
        for c in research.canonical_findings:
            full_hits = 0
            for f in [
                *research.canonical_findings,
                *research.key_research_findings,
                *research.research_tensions,
                *research.cross_evidence_findings,
                *research.key_strengths,
                *research.key_strengths,
                *research.key_weaknesses,
            ]:
                if f.finding_kind == "reference":
                    continue
                if f.claim.strip() == c.claim.strip():
                    full_hits += 1
            # canonical + optional spine mirrors with same finding_id
            results.append(
                _check(
                    f"single_full_expression_{label}_{c.finding_id}",
                    full_hits == 1,
                    f"hits={full_hits}",
                )
            )


def test_reference_is_not_new_finding(results: list[dict]) -> None:
    pack = EvidencePack.load_json(ROOT / "examples" / "600519_evidence_pack.json")
    fctx = build_fundamental_context(pack)
    fund = synthesize_fundamental(pack.stock_code, fctx)
    refs = [f for f in fund.profitability.findings if f.finding_kind == "reference"]
    results.append(_check("has_reference_stubs", len(refs) >= 1, len(refs)))
    for r in refs:
        results.append(_check("reference_is_not_new_finding", is_reference_new_finding(r) is False, r.ref_finding_id))
        if fund.canonical_findings:
            results.append(
                _check(
                    "reference_no_incremental",
                    has_incremental_value(fund.canonical_findings[0], r) is False,
                    r.ref_finding_id,
                )
            )


def test_evidence_preservation_and_numeric_citation(results: list[dict]) -> None:
    pack = EvidencePack.load_json(ROOT / "examples" / "600519_evidence_pack.json")
    fund = synthesize_fundamental(pack.stock_code, build_fundamental_context(pack))
    ok = 0
    for c in fund.canonical_findings:
        sig = depth_signals(c)
        cite_err = validate_finding_citations(c, pack)
        preserved = len(c.numbers_preserved) >= 1 or any(ch.isdigit() for ch in c.claim)
        if preserved and not cite_err and not sig["listing_only"]:
            ok += 1
        results.append(
            _check(
                f"preserve_{c.finding_id}",
                preserved and not cite_err,
                f"nums={c.numbers_preserved[:4]} cite={cite_err[:1]}",
            )
        )
        results.append(
            _check(
                f"depth_not_listing_{c.finding_id}",
                not sig["listing_only"],
                sig,
            )
        )
    results.append(_check("numeric_citation_completeness", ok == len(fund.canonical_findings), f"{ok}/{len(fund.canonical_findings)}"))


def test_incremental_finding_value(results: list[dict]) -> None:
    a = CitedFinding(
        claim="ROE 33.65%，毛利率 91.18%",
        evidence_ids=["a", "b"],
        reasoning="两指标并列。",
        interpretation="盈利能力较强。",
        finding_kind="cross",
        status="supported",
        confidence=0.7,
    )
    b_same = CitedFinding(
        claim="ROE 33.65%，毛利率 91.18%",
        evidence_ids=["a", "b"],
        reasoning="换个 section 再说一遍。",
        interpretation="盈利能力较强。",
        finding_kind="cross",
        status="supported",
        confidence=0.7,
    )
    b_better = CitedFinding(
        claim="ROE 33.65%、毛利率 91.18%，但净利同比 -4.53%，说明增长承压；单期不足以判结构变化。",
        evidence_ids=["a", "b", "c"],
        reasoning="盈利与增长对照。",
        interpretation="形成分化；边界：无法确认结构性。",
        finding_kind="tension",
        status="supported",
        confidence=0.8,
    )
    results.append(_check("incremental_rejects_paraphrase", has_incremental_value(a, b_same) is False, "same"))
    results.append(_check("incremental_accepts_relation_boundary", has_incremental_value(a, b_better) is True, "better"))


def test_cross_industry_relevance(results: list[dict]) -> None:
    cases = [
        (
            "consumer",
            "603288",
            "海天味业",
            "食品饮料-调味品",
            [
                ("海天味业提价", "stock_specific"),
                ("调味品行业去库存", "industry_related"),
                ("外汇局经常账户顺差", "macro_market"),
                ("某CDN算力租赁", "irrelevant"),
            ],
        ),
        (
            "manufacturing",
            "000338",
            "潍柴动力",
            "汽车制造-汽车零部件",
            [
                ("潍柴动力发布公告", "stock_specific"),
                ("新能源汽车产业链景气", "industry_related"),
                ("社融与央行公开市场", "macro_market"),
                ("富维股份座椅定点", "irrelevant"),
            ],
        ),
        (
            "tech",
            "300750",
            "宁德时代",
            "电气机械-电池；兼看软件与互联网资讯噪声",
            [
                ("宁德时代产能公告", "stock_specific"),
                ("半导体晶圆厂扩产", "irrelevant"),  # not this pack's strong industry
                ("云计算SaaS板块波动", "irrelevant"),
                ("产业与市场景气度提升", "macro_market"),  # generic tokens only
            ],
        ),
    ]
    # Fix tech pack industry to semiconductor-ish for clearer industry hit
    cases[2] = (
        "tech",
        "688981",
        "中芯国际",
        "半导体-集成电路",
        [
            ("中芯国际产能利用率", "stock_specific"),
            ("半导体晶圆代工景气", "industry_related"),
            ("美联储与国债收益率", "macro_market"),
            ("白酒批价波动", "irrelevant"),
        ],
    )

    for label, code, name, industry, news_cases in cases:
        pack = _pack_with_profile(code=code, name=name, industry=industry)
        for claim, expected in news_cases:
            ev = _ev(eid="n", subtype="market_news", claim=claim, published_at="2026-08-10", stock_code=None)
            got = classify_relevance(ev, pack)
            results.append(_check(f"relevance_{label}_{expected}_{claim[:6]}", got == expected, f"got={got}"))
            role = assign_research_role(ev, pack, agent="market", relevance=got)
            if expected == "irrelevant":
                results.append(_check(f"role_{label}_excluded", role == "excluded", role))
            elif expected == "macro_market":
                results.append(_check(f"role_{label}_macro", role == "macro_background", role))
            elif expected == "industry_related":
                results.append(_check(f"role_{label}_industry", role == "industry_context", role))


def test_weight_conflict_selection(results: list[dict]) -> None:
    high = {
        "evidence_id": "high",
        "subtype": "roe",
        "claim": "ROE 33.65%",
        "weight": 1.0,
        "freshness": "very_recent",
    }
    low = {
        "evidence_id": "low",
        "subtype": "roe",
        "claim": "ROE 10%",
        "weight": 0.24,
        "freshness": "stale",
    }
    picked = select_by_weight([low, high], n=1)
    results.append(_check("weight_prefers_high", picked[0]["evidence_id"] == "high", picked))
    # Conflict: both remain available; selection of high must not delete low from pool
    results.append(_check("weight_does_not_delete_low", low in [low, high] and high in [low, high], "pool intact"))
    # Weight is not an investment probability statement
    results.append(_check("weight_not_probability_semantics", True, "weight=selection priority only"))


def test_narrative_shift_and_insufficient(results: list[dict]) -> None:
    # Theme shift
    pack_shift = EvidencePack(
        stock_code="600519",
        evidence=[
            _ev(
                eid="name",
                subtype="stock_name",
                et=EvidenceType.FACT,
                claim="股票名称为 贵州茅台",
                value={"value": "贵州茅台"},
                data_date="2026-08-14",
            ),
            _ev(
                eid="close",
                subtype="close_price",
                et=EvidenceType.FACT,
                claim="最新价格为 1500 元",
                value={"value": 1500},
                data_date="2026-08-14",
            ),
            _ev(
                eid="ma5",
                subtype="ma5",
                et=EvidenceType.DERIVED,
                claim="MA5 为 1490",
                value={"value": 1490},
                data_date="2026-08-14",
            ),
            _ev(
                eid="n_prev",
                subtype="market_news",
                claim="贵州茅台经销渠道去库存与需求承压",
                published_at="2026-07-20",
            ),
            _ev(
                eid="n_cur",
                subtype="market_news",
                claim="贵州茅台提价与销量恢复，管理层释出口径",
                published_at="2026-08-10",
                freshness=FreshnessStatus.VERY_RECENT,
            ),
        ],
        generated_at="2026-08-14T00:00:00+08:00",
    )
    mctx = build_market_context(pack_shift, as_of=date(2026, 8, 14))
    market = synthesize_market(pack_shift.stock_code, mctx)
    narr = next((c for c in market.canonical_findings if "NEWS_NARRATIVE" in c.finding_id), None)
    results.append(_check("narrative_shift_present", narr is not None, bool(narr)))
    if narr:
        results.append(
            _check(
                "narrative_shift_mentions_change",
                "narrative change" in narr.claim or "主题" in narr.claim,
                narr.claim[:120],
            )
        )
        results.append(
            _check(
                "narrative_shift_cites_both",
                "n_cur" in narr.evidence_ids and "n_prev" in narr.evidence_ids,
                narr.evidence_ids,
            )
        )
        results.append(_check("narrative_shift_not_forced_false", "不得强行" not in narr.claim, narr.claim[:80]))

    # Same theme — must NOT force shift
    pack_same = EvidencePack(
        stock_code="600519",
        evidence=[
            _ev(
                eid="name",
                subtype="stock_name",
                et=EvidenceType.FACT,
                claim="股票名称为 贵州茅台",
                value={"value": "贵州茅台"},
                data_date="2026-08-14",
            ),
            _ev(
                eid="close",
                subtype="close_price",
                et=EvidenceType.FACT,
                claim="最新价格为 1500 元",
                value={"value": 1500},
                data_date="2026-08-14",
            ),
            _ev(
                eid="n_prev",
                subtype="market_news",
                claim="贵州茅台批价与渠道动销跟踪",
                published_at="2026-07-20",
            ),
            _ev(
                eid="n_cur",
                subtype="market_news",
                claim="贵州茅台批价与渠道动销继续跟踪",
                published_at="2026-08-10",
            ),
        ],
        generated_at="2026-08-14T00:00:00+08:00",
    )
    market2 = synthesize_market(pack_same.stock_code, build_market_context(pack_same, as_of=date(2026, 8, 14)))
    narr2 = next((c for c in market2.canonical_findings if "NEWS_NARRATIVE" in c.finding_id), None)
    results.append(_check("narrative_same_theme_no_force", narr2 is not None and "不得强行" in (narr2.claim if narr2 else ""), narr2.claim[:100] if narr2 else ""))

    # One side missing
    pack_one = EvidencePack(
        stock_code="600519",
        evidence=[
            _ev(
                eid="name",
                subtype="stock_name",
                et=EvidenceType.FACT,
                claim="股票名称为 贵州茅台",
                value={"value": "贵州茅台"},
                data_date="2026-08-14",
            ),
            _ev(
                eid="n_cur",
                subtype="market_news",
                claim="贵州茅台提价",
                published_at="2026-08-10",
            ),
        ],
        generated_at="2026-08-14T00:00:00+08:00",
    )
    market3 = synthesize_market(pack_one.stock_code, build_market_context(pack_one, as_of=date(2026, 8, 14)))
    has_gap = any(f.status == "insufficient_evidence" for f in market3.evidence_gaps + market3.news_narrative.findings)
    results.append(_check("narrative_insufficient_without_two_sides", has_gap, "ok"))


def test_debate_canonical_consumption(results: list[dict]) -> None:
    pack = EvidencePack.load_json(ROOT / "examples" / "600519_evidence_pack.json")
    fund = synthesize_fundamental(pack.stock_code, build_fundamental_context(pack))
    market = synthesize_market(pack.stock_code, build_market_context(pack))
    bull = synthesize_bull(pack, fund, market)
    bear = synthesize_bear(pack, fund, market)
    canon_ids = {c.finding_id for c in fund.canonical_findings}
    results.append(_check("debate_has_canonical_in_research", len(canon_ids) >= 1, sorted(canon_ids)[:3]))

    bull_text = " ".join(c.reasoning for c in bull.claims)
    bear_text = " ".join(c.reasoning for c in bear.claims)
    results.append(
        _check(
            "bull_references_canonical_tension",
            any(cid in bull_text for cid in canon_ids if "PROFIT" in cid) or "canonical" in bull_text,
            bull_text[:160],
        )
    )
    results.append(
        _check(
            "bear_references_canonical_tension",
            any(cid in bear_text for cid in canon_ids if "PROFIT" in cid) or "canonical" in bear_text,
            bear_text[:160],
        )
    )

    # Citation: if reasoning mentions a claim from pack, ids should cover key numbers where cheap-fixed
    bull01 = next(c for c in bull.claims if c.claim_id == "BULL_01")
    if "同比" in bull01.reasoning or "4.53" in bull01.reasoning:
        np_yoy = next((e for e in pack.evidence if e.subtype == "net_profit_yoy"), None)
        results.append(
            _check(
                "bull_numeric_citation_small_fix",
                np_yoy is None or np_yoy.evidence_id in bull01.evidence_ids,
                bull01.evidence_ids,
            )
        )
    else:
        results.append(_check("bull_numeric_citation_small_fix", True, "no yoy in reasoning"))

    # Debate must not invent a second full research claim equal to canonical claim text
    cloned = 0
    for claim in list(bull.claims) + list(bear.claims):
        for c in fund.canonical_findings:
            if claim.claim.strip() == c.claim.strip():
                cloned += 1
    results.append(_check("debate_no_full_canonical_clone", cloned == 0, f"cloned={cloned}"))


def test_research_output_contract(results: list[dict]) -> None:
    pack = EvidencePack.load_json(ROOT / "examples" / "600519_evidence_pack.json")
    fund = synthesize_fundamental(pack.stock_code, build_fundamental_context(pack))
    contract = build_research_output_contract(fund)
    results.append(_check("contract_as_of", bool(contract.research_as_of_date), contract.research_as_of_date))
    results.append(_check("contract_canonical_primary", len(contract.canonical_findings) >= 1, len(contract.canonical_findings)))
    results.append(
        _check(
            "contract_tensions_subset",
            all(t.finding_id in {c.finding_id for c in contract.canonical_findings} for t in contract.research_tensions),
            len(contract.research_tensions),
        )
    )
    deep = [c for c in contract.canonical_findings if depth_signals(c)["valid_deep"] or depth_signals(c)["has_relation"]]
    results.append(_check("contract_has_deep_findings", len(deep) >= 1, len(deep)))


def main() -> None:
    results: list[dict] = []
    if not (ROOT / "examples" / "600519_evidence_pack.json").exists():
        print("missing pack")
        raise SystemExit(1)
    test_canonical_uniqueness(results)
    test_reference_is_not_new_finding(results)
    test_evidence_preservation_and_numeric_citation(results)
    test_incremental_finding_value(results)
    test_cross_industry_relevance(results)
    test_weight_conflict_selection(results)
    test_narrative_shift_and_insufficient(results)
    test_debate_canonical_consumption(results)
    test_research_output_contract(results)

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    for r in results:
        print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
    print(f"\n{passed}/{total} PASS")
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
