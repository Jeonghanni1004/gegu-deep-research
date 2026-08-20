"""Freshness computation for Evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schema import EvidenceType, Freshness, FreshnessStatus


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("T", " ").replace("Z", "")
    for fmt in (
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    ):
        try:
            raw = text
            if fmt.endswith("%z") and len(text) >= 19 and "+" not in text[19:] and text.count("-") <= 2:
                # skip timezone format if no offset
                continue
            if fmt.endswith("%z"):
                # normalize +00:00
                candidate = text
                if candidate.endswith("+00:00"):
                    candidate = candidate[:-6] + "+0000"
                return datetime.strptime(candidate[:22], fmt)
            return datetime.strptime(text[:19] if len(text) >= 19 and " " in text else text[:10], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_freshness(
    *,
    evidence_type: EvidenceType,
    subtype: str | None = None,
    reference_time: str | None = None,
    retrieved_at: str | None = None,
    now: datetime | None = None,
) -> Freshness:
    """Compute freshness.

    Financial statements / consensus snapshots use ``periodic`` and do not
    mechanically age from report_date like news events.
    """
    periodic_subtypes = {
        "revenue",
        "operating_revenue",
        "net_profit_parent",
        "operating_profit",
        "gross_profit",
        "eps_basic",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "operating_cash_flow",
        "revenue_yoy",
        "net_profit_yoy",
        "gross_margin",
        "net_margin",
        "roe",
        "debt_to_asset_ratio",
        "ocf_to_net_profit",
        "eps_consensus",
        "main_business_segment",
        "industry",
        "listing_date",
        "total_shares",
        "float_shares",
    }
    if evidence_type in {EvidenceType.FACT, EvidenceType.DERIVED, EvidenceType.EXPECTATION}:
        if evidence_type == EvidenceType.EXPECTATION or (subtype in periodic_subtypes):
            # Still attach age from retrieved_at when available for auditability
            now_dt = now or datetime.now(timezone.utc)
            retrieved = _parse_dt(retrieved_at)
            age = None
            if retrieved is not None:
                if retrieved.tzinfo is None:
                    retrieved = retrieved.replace(tzinfo=timezone.utc)
                age = max((now_dt - retrieved).total_seconds() / 3600.0, 0.0)
            return Freshness(age_hours=age, status=FreshnessStatus.PERIODIC)

    now_dt = now or datetime.now(timezone.utc)
    ref = _parse_dt(reference_time) or _parse_dt(retrieved_at)
    if ref is None:
        return Freshness(age_hours=None, status=FreshnessStatus.STALE)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=now_dt.tzinfo or timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    age_hours = max((now_dt - ref).total_seconds() / 3600.0, 0.0)
    if age_hours <= 24:
        status = FreshnessStatus.VERY_RECENT
    elif age_hours <= 24 * 7:
        status = FreshnessStatus.RECENT
    elif age_hours <= 24 * 30:
        status = FreshnessStatus.HISTORICAL_RECENT
    else:
        status = FreshnessStatus.STALE
    return Freshness(age_hours=round(age_hours, 2), status=status)


def pick_event_reference_time(item: dict[str, Any]) -> str | None:
    return item.get("published_at") or item.get("notice_date") or item.get("data_date")
