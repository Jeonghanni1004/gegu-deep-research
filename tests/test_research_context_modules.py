"""Unit tests: Research Time Context / Weight / Relevance / Citation.

Usage:
  python -m tests.test_research_context_modules
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
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
from research.context import build_market_context, build_research_context
from research.priority import evidence_priority_score, rank_evidence
from research.relevance import classify_relevance
from research.schemas import CitedFinding
from research.time_context import (
    ResearchTimeContext,
    ResearchWindowPolicy,
    assign_window_bucket,
    business_event_time,
    news_windows_non_overlapping,
    resolve_as_of,
)


def _check(name: str, cond: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(cond), "detail": detail}


def _ev(
    *,
    eid: str,
    subtype: str,
    et: EvidenceType = EvidenceType.EVENT,
    claim: str = "x",
    published_at: str | None = None,
    data_date: str | None = None,
    report_date: str | None = None,
    retrieved_at: str | None = "2099-01-01",
    stock_code: str | None = "AAA",
    freshness: FreshnessStatus = FreshnessStatus.RECENT,
    reliability: Reliability = Reliability.HIGH,
    value: dict | None = None,
) -> Evidence:
    return Evidence(
        evidence_id=eid,
        stock_code=stock_code,
        evidence_type=et,
        subtype=subtype,
        claim=claim,
        value=value or {},
        source=EvidenceSource(provider="test", source_type="unit", retrieved_at=retrieved_at),
        time=EvidenceTime(
            published_at=published_at,
            data_date=data_date,
            report_date=report_date,
            retrieved_at=retrieved_at,
        ),
        freshness=Freshness(age_hours=1.0, status=freshness),
        reliability=reliability,
    )


def run_tests() -> list[dict]:
    results: list[dict] = []
    as_of = date(2026, 8, 14)
    ctx = ResearchTimeContext(research_as_of_date=as_of, policy=ResearchWindowPolicy())

    # --- business time never retrieved_at ---
    news = _ev(
        eid="n1",
        subtype="market_news",
        published_at="2026-08-10",
        retrieved_at="2099-12-31",
        claim="个股公告测试",
    )
    dt, basis = business_event_time(news)
    results.append(_check("business_time_uses_published_at", dt == date(2026, 8, 10) and basis == "published_at", f"{dt} {basis}"))

    fin = _ev(
        eid="f1",
        subtype="roe",
        et=EvidenceType.DERIVED,
        report_date="2025-12-31",
        retrieved_at="2099-12-31",
        claim="ROE 33.65%",
        value={"value": 0.3365},
    )
    dt2, basis2 = business_event_time(fin)
    results.append(_check("business_time_uses_report_date", dt2 == date(2025, 12, 31) and basis2 == "report_date", f"{dt2} {basis2}"))

    px = _ev(
        eid="p1",
        subtype="close_price",
        et=EvidenceType.FACT,
        data_date="2026-08-14",
        retrieved_at="2099-12-31",
        claim="最新价 10",
    )
    dt3, basis3 = business_event_time(px)
    results.append(_check("business_time_uses_data_date", dt3 == date(2026, 8, 14) and basis3 == "data_date", f"{dt3} {basis3}"))

    # --- PIT: post_as_of excluded even if retrieved earlier ---
    future = _ev(
        eid="fut",
        subtype="market_news",
        published_at="2026-08-20",
        retrieved_at="2026-01-01",
        claim="未来新闻",
    )
    bucket, excl = assign_window_bucket(future, ctx)
    results.append(_check("post_as_of_excluded", bucket is None and excl and excl.reason == "post_as_of", str(excl)))

    # --- news windows non-overlapping ---
    wins = news_windows_non_overlapping(as_of)
    cur_s, cur_e = wins["news_current_7d"]
    prev_s, prev_e = wins["news_previous_8_30d"]
    results.append(
        _check(
            "news_windows_non_overlap",
            cur_s == date(2026, 8, 8) and cur_e == as_of and prev_e == date(2026, 8, 7) and prev_s == date(2026, 7, 16),
            f"cur={cur_s}..{cur_e} prev={prev_s}..{prev_e}",
        )
    )
    results.append(_check("news_windows_adjacent", prev_e + timedelta(days=1) == cur_s, f"{prev_e} {cur_s}"))

    n_cur = _ev(eid="nc", subtype="market_news", published_at="2026-08-10", claim="白酒相关 贵州茅台")
    n_prev = _ev(eid="np", subtype="market_news", published_at="2026-07-20", claim="白酒相关")
    n_old = _ev(eid="no", subtype="market_news", published_at="2026-06-01", claim="白酒")
    b1, _ = assign_window_bucket(n_cur, ctx)
    b2, _ = assign_window_bucket(n_prev, ctx)
    b3, e3 = assign_window_bucket(n_old, ctx)
    results.append(_check("news_current_bucket", b1 == "news_current_7d", str(b1)))
    results.append(_check("news_previous_bucket", b2 == "news_previous_8_30d", str(b2)))
    results.append(_check("news_out_of_window", b3 is None and e3 and e3.reason == "out_of_window", str(e3)))

    # company 90d
    ann = _ev(eid="a1", subtype="announcement", published_at="2026-06-01", claim="公司公告")
    ba, _ = assign_window_bucket(ann, ctx)
    results.append(_check("company_90d", ba == "company_events_90d", str(ba)))

    # --- weight ranking ---
    low = _ev(
        eid="low",
        subtype="market_news",
        published_at="2026-08-10",
        freshness=FreshnessStatus.STALE,
        reliability=Reliability.LOW,
    )
    high = _ev(
        eid="high",
        subtype="market_news",
        published_at="2026-08-10",
        freshness=FreshnessStatus.VERY_RECENT,
        reliability=Reliability.HIGH,
    )
    ranked = rank_evidence([low, high])
    results.append(
        _check(
            "weight_rank_order",
            ranked[0].evidence_id == "high" and evidence_priority_score(high) > evidence_priority_score(low),
            f"{evidence_priority_score(high)} vs {evidence_priority_score(low)}",
        )
    )

    # --- relevance ---
    pack = EvidencePack(
        stock_code="600000",
        evidence=[
            _ev(
                eid="name",
                subtype="stock_name",
                et=EvidenceType.FACT,
                claim="股票名称为 测试股份",
                value={"value": "测试股份"},
                data_date="2026-08-14",
                stock_code="600000",
            ),
            _ev(
                eid="ind",
                subtype="industry",
                et=EvidenceType.FACT,
                claim="所属行业为 制造业-白酒",
                value={"value": "制造业-白酒"},
                report_date="2026-08-14",
                stock_code="600000",
            ),
        ],
        generated_at="2026-08-14T00:00:00+08:00",
    )
    stock_news = _ev(eid="sn", subtype="market_news", published_at="2026-08-10", claim="测试股份 发布提价", stock_code="600000")
    ai_news = _ev(eid="ai", subtype="market_news", published_at="2026-08-10", claim="某CDN+液冷+GPU算力租赁行情异动", stock_code=None)
    liquor_news = _ev(eid="lq", subtype="market_news", published_at="2026-08-10", claim="白酒板块调整", stock_code=None)
    results.append(_check("relevance_stock", classify_relevance(stock_news, pack) == "stock_specific", classify_relevance(stock_news, pack)))
    results.append(_check("relevance_irrelevant_tech", classify_relevance(ai_news, pack) == "irrelevant", classify_relevance(ai_news, pack)))
    results.append(_check("relevance_industry", classify_relevance(liquor_news, pack) == "industry_related", classify_relevance(liquor_news, pack)))

    # context excludes irrelevant / post_as_of
    pack2 = EvidencePack(
        stock_code="600000",
        evidence=list(pack.evidence)
        + [
            stock_news,
            ai_news,
            future,
            _ev(
                eid="close",
                subtype="close_price",
                et=EvidenceType.FACT,
                data_date="2026-08-14",
                claim="最新价格为 10.5 元",
                value={"value": 10.5},
                stock_code="600000",
            ),
        ],
        generated_at="2026-08-14T12:00:00+08:00",
    )
    mctx = build_market_context(pack2, as_of=as_of)
    core_ids = {r["evidence_id"] for r in mctx["evidence_groups"].get("news_current_7d", [])}
    excl_reasons = {(x["evidence_id"], x["reason"]) for x in mctx["excluded_audit"]}
    results.append(_check("context_excludes_irrelevant", "ai" not in core_ids and ("ai", "irrelevant") in excl_reasons, str(excl_reasons)))
    results.append(_check("context_excludes_post_as_of", ("fut", "post_as_of") in excl_reasons, str(excl_reasons)))
    results.append(_check("context_records_as_of", mctx["research_as_of_date"] == "2026-08-14", mctx["research_as_of_date"]))
    results.append(
        _check(
            "default_as_of_from_pack",
            resolve_as_of(pack2) == date(2026, 8, 14),
            str(resolve_as_of(pack2)),
        )
    )

    # --- citation completeness ---
    ok_finding = CitedFinding(
        claim="ROE为 33.65%，净利润同比下降 4.53%",
        reasoning="同时引用盈利能力与增速证据。",
        interpretation="高回报与增速承压并存。",
        evidence_ids=["f1", "f2"],
        status="supported",
        finding_kind="cross",
        confidence=0.8,
    )
    pack_cite = EvidencePack(
        stock_code="X",
        evidence=[
            fin,
            _ev(
                eid="f2",
                subtype="net_profit_yoy",
                et=EvidenceType.DERIVED,
                report_date="2025-12-31",
                claim="归母净利润同比下降 4.53%",
                value={"value": -0.0453},
            ),
        ],
        generated_at="2026-08-14",
    )
    bad_finding = CitedFinding(
        claim="ROE为 33.65%，净利润同比下降 4.53%",
        reasoning="只用了 ROE 证据却提到 4.53%。",
        interpretation="x",
        evidence_ids=["f1"],
        status="supported",
        finding_kind="atomic",
        confidence=0.5,
    )
    err_ok = validate_finding_citations(ok_finding, pack_cite)
    err_bad = validate_finding_citations(bad_finding, pack_cite)
    results.append(_check("citation_ok_multi", err_ok == [], str(err_ok)))
    results.append(_check("citation_incomplete_caught", len(err_bad) >= 1, str(err_bad)))
    results.append(_check("extract_tokens", "33.65" in extract_fact_tokens("ROE 33.65%") or "33.65%" in extract_fact_tokens("ROE 33.65%"), str(extract_fact_tokens("ROE 33.65%"))))

    # real pack smoke (if present)
    real = ROOT / "examples" / "600519_evidence_pack.json"
    if real.exists():
        rpack = EvidencePack.load_json(real)
        fctx = build_research_context(rpack, agent="fundamental")
        results.append(
            _check(
                "real_pack_context_builds",
                bool(fctx["research_as_of_date"]) and "financial_latest" in fctx["evidence_groups"],
                fctx["research_as_of_date"],
            )
        )
        # ensure no excluded post_as_of wrongly if all <= generated
        results.append(_check("real_pack_has_bundles", len(fctx["cross_evidence_bundles"]) >= 4, str(len(fctx["cross_evidence_bundles"]))))

    return results


def main() -> None:
    results = run_tests()
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    for r in results:
        print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
    print(f"\n{passed}/{total} PASS")
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
