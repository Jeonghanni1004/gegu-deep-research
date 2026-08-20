"""Build Research Agent context: time windows + weight + relevance."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from evidence.pack import EvidencePack
from evidence.schema import Evidence

from research.priority import attach_weight_meta, evidence_priority_score, rank_evidence
from research.relevance import RelevanceBucket, assign_research_role, classify_relevance
from research.selection import select_best_per_subtype
from research.time_context import (
    ExclusionRecord,
    ResearchTimeContext,
    ResearchWindowPolicy,
    assign_window_bucket,
    business_event_time,
    classify_role,
    resolve_as_of,
)


def _serialize_ref(
    evidence: Evidence,
    *,
    window_bucket: str,
    relevance: RelevanceBucket,
    as_of: date,
    pack: EvidencePack,
    agent: str,
) -> dict[str, Any]:
    event_dt, basis = business_event_time(evidence)
    age = (as_of - event_dt).days if event_dt else None
    meta = attach_weight_meta(evidence)
    research_role = assign_research_role(evidence, pack, agent=agent, relevance=relevance)
    return {
        "evidence_id": evidence.evidence_id,
        "evidence_type": evidence.evidence_type.value,
        "subtype": evidence.subtype,
        "claim": evidence.claim,
        "value": evidence.value,
        "role": classify_role(evidence),
        "window_bucket": window_bucket,
        "time_basis": basis,
        "event_time": event_dt.isoformat() if event_dt else None,
        "age_days_vs_as_of": age,
        "relevance_bucket": relevance,
        "research_role": research_role,
        "weight": meta["weight"],
        "reliability": meta["reliability"],
        "freshness": meta["freshness"],
        "source": {
            "provider": evidence.source.provider,
            "source_type": evidence.source.source_type,
            "url": evidence.source.url,
        },
        "time": {
            "data_date": evidence.time.data_date,
            "report_date": evidence.time.report_date,
            "published_at": evidence.time.published_at,
            "retrieved_at": evidence.time.retrieved_at,
        },
    }


def _latest_by_subtype(items: list[Evidence], *, key: str) -> list[Evidence]:
    """Keep newest event_time per subtype."""
    best: dict[str, Evidence] = {}
    best_dt: dict[str, date] = {}
    for e in items:
        event_dt, _ = business_event_time(e)
        if event_dt is None:
            continue
        prev = best_dt.get(e.subtype)
        if prev is None or event_dt > prev:
            best[e.subtype] = e
            best_dt[e.subtype] = event_dt
    return list(best.values())


def build_research_context(
    pack: EvidencePack,
    *,
    as_of: str | date | None = None,
    agent: str = "fundamental",
    policy: ResearchWindowPolicy | None = None,
) -> dict[str, Any]:
    """Assemble LLM/research context. Does not mutate EvidencePack."""
    as_of_date = resolve_as_of(pack, as_of)
    time_ctx = ResearchTimeContext(research_as_of_date=as_of_date, policy=policy or ResearchWindowPolicy())

    buckets: dict[str, list[Evidence]] = defaultdict(list)
    exclusions: list[ExclusionRecord] = []

    for e in pack.evidence:
        bucket, excl = assign_window_bucket(e, time_ctx)
        if excl is not None:
            exclusions.append(excl)
            continue
        assert bucket is not None
        rel = classify_relevance(e, pack)
        rrole = assign_research_role(e, pack, agent=agent, relevance=rel)
        if rel == "irrelevant" or rrole == "excluded":
            exclusions.append(
                ExclusionRecord(e.evidence_id, "irrelevant", f"claim={e.claim[:80]}")
            )
            continue
        # Macro never enters fundamental core
        if agent == "fundamental" and rel == "macro_market" and classify_role(e) in {
            "news_flash",
            "macro_news",
        }:
            exclusions.append(
                ExclusionRecord(e.evidence_id, "irrelevant", "macro_not_in_fundamental_core")
            )
            continue
        # News windows: only stock_specific stays in news_* ; industry → industry_30d; macro → macro_background
        if agent == "market" and bucket in {"news_current_7d", "news_previous_8_30d"}:
            if rel == "stock_specific":
                buckets[bucket].append(e)
            elif rel == "industry_related":
                buckets["industry_30d"].append(e)
            elif rel == "macro_market":
                buckets["macro_background"].append(e)
            else:
                exclusions.append(
                    ExclusionRecord(e.evidence_id, "irrelevant", "news_not_usable_for_core")
                )
            continue
        # industry_30d window: only true industry_related; else re-route or exclude
        if agent == "market" and bucket == "industry_30d":
            if rel == "industry_related":
                buckets["industry_30d"].append(e)
            elif rel == "macro_market":
                buckets["macro_background"].append(e)
            else:
                exclusions.append(
                    ExclusionRecord(e.evidence_id, "irrelevant", "industry_window_not_industry_related")
                )
            continue
        buckets[bucket].append(e)

    # Split financial_history → financial_latest (newest report_date per subtype) + rest history
    fin_all = buckets.get("financial_history", [])
    fin_latest = _latest_by_subtype(fin_all, key="report_date")
    latest_ids = {e.evidence_id for e in fin_latest}
    fin_history = [e for e in fin_all if e.evidence_id not in latest_ids]
    buckets["financial_latest"] = rank_evidence(fin_latest)
    buckets["financial_history"] = rank_evidence(fin_history)

    # Split market_trend → market_spot (latest data_date per subtype) + trend remainder
    mkt_all = buckets.get("market_trend", [])
    mkt_spot = _latest_by_subtype(mkt_all, key="data_date")
    spot_ids = {e.evidence_id for e in mkt_spot}
    mkt_trend = [e for e in mkt_all if e.evidence_id not in spot_ids]
    buckets["market_spot"] = rank_evidence(mkt_spot)
    buckets["market_trend"] = rank_evidence(mkt_trend)

    # Rank remaining buckets
    for key in list(buckets.keys()):
        if key in {"financial_latest", "financial_history", "market_spot", "market_trend"}:
            continue
        buckets[key] = rank_evidence(buckets[key])

    def ser_list(window_bucket: str, items: list[Evidence], *, limit: int | None = None) -> list[dict]:
        rows = []
        for e in items[: limit if limit is not None else len(items)]:
            rel = classify_relevance(e, pack)
            rows.append(
                _serialize_ref(
                    e,
                    window_bucket=window_bucket,
                    relevance=rel,
                    as_of=as_of_date,
                    pack=pack,
                    agent=agent,
                )
            )
        rows.sort(key=lambda r: float(r.get("weight") or 0), reverse=True)
        return rows

    groups: dict[str, list[dict]] = {
        "company_profile": ser_list("company_profile", buckets.get("company_profile", [])),
        "financial_latest": ser_list("financial_latest", buckets.get("financial_latest", [])),
        "financial_history": ser_list("financial_history", buckets.get("financial_history", []), limit=40),
        "company_events_90d": ser_list("company_events_90d", buckets.get("company_events_90d", []), limit=15),
        "expectation_latest": ser_list("expectation_latest", buckets.get("expectation_latest", [])),
        "market_spot": ser_list("market_spot", buckets.get("market_spot", [])),
        "market_trend": ser_list("market_trend", buckets.get("market_trend", []), limit=40),
        "news_current_7d": ser_list("news_current_7d", buckets.get("news_current_7d", []), limit=20),
        "news_previous_8_30d": ser_list(
            "news_previous_8_30d", buckets.get("news_previous_8_30d", []), limit=20
        ),
        "industry_30d": ser_list("industry_30d", buckets.get("industry_30d", []), limit=15),
        "macro_background": ser_list("macro_background", buckets.get("macro_background", []), limit=10),
    }

    # Cross-evidence candidate bundles (ids only; synthesizer decides insufficient)
    bundles = _build_cross_bundles(groups)

    # Deduplicate exclusions
    excl_rows = []
    seen_excl = set()
    for ex in exclusions:
        key = (ex.evidence_id, ex.reason)
        if key in seen_excl:
            continue
        seen_excl.add(key)
        excl_rows.append(ex.to_dict())

    return {
        "agent": agent,
        "stock_code": pack.stock_code,
        "time_context": time_ctx.to_dict(),
        "research_as_of_date": as_of_date.isoformat(),
        "evidence_groups": groups,
        "cross_evidence_bundles": bundles,
        "excluded_audit": excl_rows,
        "notes": [
            "retrieved_at is never used as business event time for window membership",
            "weight = reliability × freshness for ranking and candidate selection",
            "news_current_7d only includes stock_specific; industry → industry_30d; macro → macro_background",
            "news_current_7d and news_previous_8_30d are non-overlapping",
        ],
    }


def _bundle(name: str, items: list[dict], *, min_n: int = 2, research_question: str = "") -> dict[str, Any]:
    present = [x for x in items if x is not None]
    return {
        "bundle": name,
        "research_question": research_question,
        "status": "ready" if len(present) >= min_n else "insufficient_evidence",
        "evidence_ids": [x["evidence_id"] for x in present],
        "claims": [x["claim"] for x in present],
        "subtypes": [x["subtype"] for x in present],
        "weights": [x.get("weight") for x in present],
        "selected": present,
    }


def _build_cross_bundles(groups: dict[str, list[dict]]) -> list[dict[str, Any]]:
    fin = groups.get("financial_latest") or []
    spot = groups.get("market_spot") or []
    # Weight-aware per-subtype selection (also considers history pool as lower-priority candidates)
    fin_pool = list(fin) + list(groups.get("financial_history") or [])
    spot_pool = list(spot) + list(groups.get("market_trend") or [])

    return [
        _bundle(
            "profitability_x_growth",
            select_best_per_subtype(fin_pool, ["roe", "gross_margin", "net_profit_yoy", "revenue_yoy"]),
            min_n=2,
            research_question="盈利能力是否仍强，增长动能是否承压？",
        ),
        _bundle(
            "cashflow_x_earnings_quality",
            select_best_per_subtype(
                fin_pool, ["ocf_to_net_profit", "operating_cash_flow", "net_profit_parent"]
            ),
            min_n=2,
            research_question="利润质量是否得到经营现金流支持？",
        ),
        _bundle(
            "balance_sheet_x_operating_risk",
            select_best_per_subtype(
                fin_pool,
                ["debt_to_asset_ratio", "cash_and_equivalents", "operating_revenue", "net_profit_parent"],
            ),
            min_n=2,
            research_question="财务缓冲与经营规模如何共同约束风险判断？",
        ),
        _bundle(
            "valuation_x_earnings_or_growth",
            select_best_per_subtype(spot_pool, ["pe", "pb"])
            + select_best_per_subtype(fin_pool, ["roe", "net_profit_yoy", "revenue_yoy"]),
            min_n=2,
            research_question="当前估值需要怎样的盈利/增长假设才能成立？",
        ),
        _bundle(
            "price_x_moving_averages",
            select_best_per_subtype(spot_pool, ["close_price", "ma5", "ma20", "ma60", "ma250"]),
            min_n=2,
            research_question="价格相对均线结构处于什么状态？",
        ),
        _bundle(
            "short_trend_x_long_trend",
            select_best_per_subtype(spot_pool, ["ma5", "ma20", "ma60", "ma250", "close_price"]),
            min_n=2,
            research_question="短中期趋势与长期均线是否冲突？",
        ),
        _bundle(
            "valuation_x_market_price",
            select_best_per_subtype(
                spot_pool, ["pe", "pb", "close_price", "price_position_in_52w_range"]
            ),
            min_n=2,
            research_question="估值与价格位置如何共同描述定价状态？",
        ),
    ]


# Back-compat helpers used by agents/tests
def build_fundamental_context(pack: EvidencePack, *, as_of: str | date | None = None) -> dict[str, Any]:
    return build_research_context(pack, as_of=as_of, agent="fundamental")


def build_market_context(pack: EvidencePack, *, as_of: str | date | None = None) -> dict[str, Any]:
    return build_research_context(pack, as_of=as_of, agent="market")
