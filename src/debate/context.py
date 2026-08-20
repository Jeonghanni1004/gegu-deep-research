"""Shared debate context: identical inputs for Bull and Bear."""

from __future__ import annotations

from typing import Any

from evidence.pack import EvidencePack
from evidence.schema import Evidence
from research.schemas import FundamentalResearch, MarketResearch


def index_pack(pack: EvidencePack) -> dict[str, Evidence]:
    return {e.evidence_id: e for e in pack.evidence}


def find_by_subtype(pack: EvidencePack, subtypes: set[str]) -> list[Evidence]:
    items = [e for e in pack.evidence if e.subtype in subtypes]

    def sort_key(e: Evidence) -> str:
        return e.time.report_date or e.time.data_date or e.time.published_at or ""

    items.sort(key=sort_key, reverse=True)
    return items


def first_by_subtype(pack: EvidencePack, subtype: str) -> Evidence | None:
    items = find_by_subtype(pack, {subtype})
    return items[0] if items else None


def serialize_evidence(e: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": e.evidence_id,
        "evidence_type": e.evidence_type.value,
        "subtype": e.subtype,
        "claim": e.claim,
        "value": e.value,
        "source": {
            "provider": e.source.provider,
            "source_type": e.source.source_type,
            "url": e.source.url,
        },
        "time": {
            "data_date": e.time.data_date,
            "report_date": e.time.report_date,
            "published_at": e.time.published_at,
        },
        "freshness": e.freshness.status.value,
        "reliability": e.reliability.value,
    }


def build_shared_context(
    pack: EvidencePack,
    fundamental: FundamentalResearch,
    market: MarketResearch,
) -> dict[str, Any]:
    """Bull and Bear must receive this identical payload."""
    # Focused evidence pool from research used ids + key subtypes
    wanted_subtypes = {
        "roe",
        "gross_margin",
        "net_margin",
        "revenue_yoy",
        "net_profit_yoy",
        "operating_revenue",
        "net_profit_parent",
        "debt_to_asset_ratio",
        "ocf_to_net_profit",
        "operating_cash_flow",
        "close_price",
        "ma5",
        "ma20",
        "ma60",
        "ma250",
        "rsi_14",
        "macd_hist",
        "price_position_in_52w_range",
        "high_52w",
        "low_52w",
        "pe",
        "pb",
        "eps_consensus",
        "stock_name",
        "industry",
        "main_business_segment",
        "announcement",
        "shareholder_change",
    }
    focused = find_by_subtype(pack, wanted_subtypes)
    used = set(fundamental.used_evidence_ids) | set(market.used_evidence_ids)
    by_id = index_pack(pack)
    extra = [by_id[i] for i in used if i in by_id]
    merged: dict[str, Evidence] = {e.evidence_id: e for e in focused + extra}

    return {
        "stock_code": pack.stock_code,
        "evidence": [serialize_evidence(e) for e in merged.values()],
        "fundamental": fundamental.model_dump(mode="json"),
        "market": market.model_dump(mode="json"),
        # Explicit FA-facing spine: debate may reference these ids; must not re-author them
        "canonical_findings": {
            "fundamental": [c.model_dump(mode="json") for c in fundamental.canonical_findings],
            "market": [c.model_dump(mode="json") for c in market.canonical_findings],
        },
        "input_fingerprint": {
            "evidence_count": len(pack.evidence),
            "fundamental_used": sorted(fundamental.used_evidence_ids),
            "market_used": sorted(market.used_evidence_ids),
            "fundamental_canonical_ids": [c.finding_id for c in fundamental.canonical_findings],
            "market_canonical_ids": [c.finding_id for c in market.canonical_findings],
        },
    }
