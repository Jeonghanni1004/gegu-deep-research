"""Third-iteration research quality tests.

Usage:
  python -m tests.test_research_compression
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
from research.citation import extract_fact_tokens, validate_finding_citations
from research.context import build_fundamental_context, build_market_context
from research.fundamental_agent import FundamentalAgent
from research.llm import GroundedLLMClient
from research.market_agent import MarketAgent
from research.relevance import assign_research_role, classify_relevance
from research.schemas import CitedFinding
from research.selection import select_by_weight
from research.synthesize import synthesize_fundamental, synthesize_market


def _check(name: str, cond: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(cond), "detail": detail}


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


def _maotai_pack() -> EvidencePack:
    path = ROOT / "examples" / "600519_evidence_pack.json"
    return EvidencePack.load_json(path)


def test_compression(results: list[dict]) -> None:
    pack = _maotai_pack()
    llm = GroundedLLMClient(pack_for_validation=pack)

    async def _run():
        fund = await FundamentalAgent(llm=llm).research(pack)
        market = await MarketAgent(llm=llm).research(pack)
        return fund, market

    fund, market = asyncio.run(_run())

    # Same research proposition should not be fully regenerated in compat sections
    clones = 0
    for c in fund.canonical_findings:
        for section in [fund.financial_performance, fund.profitability, fund.financial_health, fund.cash_flow]:
            for f in section.findings:
                if f.finding_kind != "reference" and f.claim.strip() == c.claim.strip():
                    clones += 1
        for f in fund.key_strengths + fund.key_weaknesses:
            if f.finding_kind != "reference" and f.claim.strip() == c.claim.strip():
                clones += 1
    results.append(_check("compression_no_full_clone", clones == 0, f"clones={clones}"))

    # Compat sections should mostly reference
    refs = sum(1 for f in fund.profitability.findings if f.finding_kind == "reference")
    results.append(_check("compression_uses_reference", refs >= 1 or not fund.canonical_findings, f"refs={refs}"))
    results.append(_check("canonical_present", len(fund.canonical_findings) >= 1, len(fund.canonical_findings)))


def test_evidence_preservation(results: list[dict]) -> None:
    pack = _maotai_pack()
    fctx = build_fundamental_context(pack)
    fund = synthesize_fundamental(pack.stock_code, fctx)
    cores = [c for c in fund.canonical_findings if c.status == "supported"]
    ok = 0
    checked = 0
    for c in cores[:12]:
        checked += 1
        text = " ".join([c.claim, c.reasoning, c.interpretation])
        nums = extract_fact_tokens(text)
        has_num = len(nums) >= 1 or len(c.numbers_preserved) >= 1
        has_ids = len(c.evidence_ids) >= 1
        # analytical increment: not equal to a single evidence claim
        claim_map = {e.evidence_id: e.claim for e in pack.evidence}
        not_echo = not any(c.claim.strip() == (claim_map.get(eid) or "").strip() for eid in c.evidence_ids)
        cite_err = validate_finding_citations(c, pack)
        if has_num and has_ids and not_echo and not cite_err:
            ok += 1
    ratio = (ok / checked) if checked else 0
    results.append(_check("evidence_preservation_ratio", ratio >= 0.9, f"{ok}/{checked}={ratio:.2f}"))


def test_relevance_precision(results: list[dict]) -> None:
    pack = _maotai_pack()
    cases = [
        ("外汇局经常账户顺差扩大", "macro_market"),
        ("富维股份获得座椅定点", "irrelevant"),
        ("*ST闻泰预亏扩大", "irrelevant"),
        ("CDN+GPU算力租赁行情", "irrelevant"),
        ("白酒行业批价与渠道去库存", "industry_related"),
        ("贵州茅台发布经营公告", "stock_specific"),
    ]
    for claim, expected in cases:
        ev = _ev(eid="x", subtype="market_news", claim=claim, published_at="2026-08-10")
        got = classify_relevance(ev, pack)
        results.append(_check(f"relevance_{expected}_{claim[:8]}", got == expected, f"got={got}"))
        role = assign_research_role(ev, pack, agent="market", relevance=got)
        if expected == "irrelevant":
            results.append(_check(f"role_excluded_{claim[:6]}", role == "excluded", role))
        elif expected == "macro_market":
            results.append(_check(f"role_macro_{claim[:6]}", role == "macro_background", role))
        elif expected == "industry_related":
            results.append(_check(f"role_industry_{claim[:6]}", role == "industry_context", role))


def test_weight_selection(results: list[dict]) -> None:
    low = {
        "evidence_id": "low",
        "subtype": "roe",
        "claim": "ROE 10%",
        "weight": 0.2,
        "freshness": "stale",
    }
    high = {
        "evidence_id": "high",
        "subtype": "roe",
        "claim": "ROE 33.65%",
        "weight": 0.9,
        "freshness": "very_recent",
    }
    picked = select_by_weight([low, high], n=1)
    results.append(_check("weight_select_prefers_high", picked[0]["evidence_id"] == "high", str(picked)))

    # Bundle selection uses weight: put both ROE into a mini pack context path
    pack = EvidencePack(
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
                eid="roe_low",
                subtype="roe",
                et=EvidenceType.DERIVED,
                claim="ROE 10%",
                value={"value": 0.10},
                report_date="2024-12-31",
                freshness=FreshnessStatus.STALE,
                reliability=Reliability.LOW,
            ),
            _ev(
                eid="roe_high",
                subtype="roe",
                et=EvidenceType.DERIVED,
                claim="ROE 33.65%",
                value={"value": 0.3365},
                report_date="2025-12-31",
                freshness=FreshnessStatus.VERY_RECENT,
                reliability=Reliability.HIGH,
            ),
            _ev(
                eid="npy",
                subtype="net_profit_yoy",
                et=EvidenceType.DERIVED,
                claim="净利润同比 -4.53%",
                value={"value": -0.0453},
                report_date="2025-12-31",
            ),
        ],
        generated_at="2026-08-14T00:00:00+08:00",
    )
    fctx = build_fundamental_context(pack, as_of=date(2026, 8, 14))
    bundle = next(b for b in fctx["cross_evidence_bundles"] if b["bundle"] == "profitability_x_growth")
    selected_ids = set(bundle.get("evidence_ids") or [])
    results.append(_check("weight_in_bundle_prefers_high_roe", "roe_high" in selected_ids, str(selected_ids)))
    # If both somehow present, high should still be first among roe
    roe_rows = [r for r in (bundle.get("selected") or []) if r.get("subtype") == "roe"]
    if roe_rows:
        results.append(_check("weight_roe_row_is_high", roe_rows[0]["evidence_id"] == "roe_high", str(roe_rows)))
    else:
        results.append(_check("weight_roe_row_is_high", False, "no roe selected"))


def test_finding_increment(results: list[dict]) -> None:
    pack = _maotai_pack()
    fctx = build_fundamental_context(pack)
    mctx = build_market_context(pack)
    fund = synthesize_fundamental(pack.stock_code, fctx)
    market = synthesize_market(pack.stock_code, mctx)

    atomics = [f for f in fund.core_facts if f.finding_kind == "atomic" and f.status == "supported"]
    crosses = [f for f in fund.canonical_findings if f.finding_kind == "cross" and f.status == "supported"]
    tensions = [f for f in fund.canonical_findings if f.finding_kind == "tension" and f.status == "supported"]
    results.append(_check("increment_atomic_single_id", all(len(f.evidence_ids) == 1 for f in atomics) or not atomics, len(atomics)))
    results.append(_check("increment_cross_multi", all(len(f.evidence_ids) >= 2 for f in crosses), len(crosses)))
    results.append(_check("increment_tension_multi", all(len(f.evidence_ids) >= 2 for f in tensions), len(tensions)))

    # Cross/tension must add relation language beyond single claim concat equality
    claim_map = {e.evidence_id: e.claim for e in pack.evidence}
    for label, rows in [("cross", crosses), ("tension", tensions)]:
        bad = 0
        for f in rows:
            if any(f.claim.strip() == (claim_map.get(eid) or "").strip() for eid in f.evidence_ids):
                bad += 1
        results.append(_check(f"increment_{label}_not_echo", bad == 0, f"bad={bad}"))


def test_citation_completeness(results: list[dict]) -> None:
    pack = _maotai_pack()
    fctx = build_fundamental_context(pack)
    fund = synthesize_fundamental(pack.stock_code, fctx)
    errs = []
    for c in fund.canonical_findings:
        errs.extend(validate_finding_citations(c, pack))
    results.append(_check("citation_canonical_ok", errs == [], str(errs[:3])))


def test_narrative_change_fixture(results: list[dict]) -> None:
    """Synthetic pack: both Current and Previous stock-specific news exist."""
    pack = EvidencePack(
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
                claim="最新价格为 1500.00 元",
                value={"value": 1500.0},
                data_date="2026-08-14",
            ),
            _ev(
                eid="ma5",
                subtype="ma5",
                et=EvidenceType.DERIVED,
                claim="MA5 为 1490.00",
                value={"value": 1490.0},
                data_date="2026-08-14",
            ),
            _ev(
                eid="ma250",
                subtype="ma250",
                et=EvidenceType.DERIVED,
                claim="MA250 为 1600.00",
                value={"value": 1600.0},
                data_date="2026-08-14",
            ),
            _ev(
                eid="n_cur",
                subtype="market_news",
                claim="贵州茅台渠道批价回升",
                published_at="2026-08-10",
                freshness=FreshnessStatus.VERY_RECENT,
            ),
            _ev(
                eid="n_prev",
                subtype="market_news",
                claim="贵州茅台经销商会议召开",
                published_at="2026-07-20",
                freshness=FreshnessStatus.RECENT,
            ),
            _ev(
                eid="fx",
                subtype="market_news",
                claim="外汇局经常账户顺差扩大",
                published_at="2026-08-10",
            ),
        ],
        generated_at="2026-08-14T00:00:00+08:00",
    )
    mctx = build_market_context(pack, as_of=date(2026, 8, 14))
    cur_ids = {r["evidence_id"] for r in mctx["evidence_groups"].get("news_current_7d") or []}
    prev_ids = {r["evidence_id"] for r in mctx["evidence_groups"].get("news_previous_8_30d") or []}
    macro_ids = {r["evidence_id"] for r in mctx["evidence_groups"].get("macro_background") or []}
    results.append(_check("narrative_current_has_stock", "n_cur" in cur_ids, str(cur_ids)))
    results.append(_check("narrative_previous_has_stock", "n_prev" in prev_ids, str(prev_ids)))
    results.append(_check("narrative_macro_not_in_news_core", "fx" not in cur_ids and "fx" in macro_ids, str(macro_ids)))
    market = synthesize_market(pack.stock_code, mctx)
    narr = next((c for c in market.canonical_findings if "NEWS_NARRATIVE" in c.finding_id), None)
    results.append(_check("narrative_canonical_built", narr is not None, bool(narr)))
    if narr:
        results.append(
            _check(
                "narrative_cites_both_windows",
                "n_cur" in narr.evidence_ids and "n_prev" in narr.evidence_ids,
                narr.evidence_ids,
            )
        )


def main() -> None:
    results: list[dict] = []
    if not (ROOT / "examples" / "600519_evidence_pack.json").exists():
        print("missing 600519 evidence pack")
        raise SystemExit(1)
    test_compression(results)
    test_evidence_preservation(results)
    test_relevance_precision(results)
    test_weight_selection(results)
    test_finding_increment(results)
    test_citation_completeness(results)
    test_narrative_change_fixture(results)

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    for r in results:
        print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
    print(f"\n{passed}/{total} PASS")
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
