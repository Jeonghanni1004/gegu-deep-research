"""Research Time Context: as_of date + role-specific windows + PIT filter.

Business event time MUST NOT use retrieved_at.
- news / company events / industry / macro → published_at
- financial statements → report_date
- market spot / derived → data_date
- expectations → published_at or data_date (never retrieved_at alone)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

from evidence.pack import EvidencePack
from evidence.schema import Evidence, EvidenceType

ExclusionReason = Literal[
    "post_as_of",
    "out_of_window",
    "irrelevant",
    "time_incomplete",
]

WindowBucket = Literal[
    "news_current_7d",
    "news_previous_8_30d",
    "company_events_90d",
    "industry_30d",
    "macro_background",
    "financial_latest",
    "financial_history",
    "market_spot",
    "market_trend",
    "expectation_latest",
    "company_profile",
    "excluded",
]

EvidenceRole = Literal[
    "news_flash",
    "company_event",
    "industry_news",
    "macro_news",
    "financial_statement",
    "market_spot",
    "market_derived",
    "expectation",
    "company_profile",
    "other",
]

TimeBasis = Literal["published_at", "report_date", "data_date", "none"]

COMPANY_EVENT_SUBTYPES = {"announcement", "shareholder_change", "company_news"}
NEWS_FLASH_SUBTYPES = {"market_news"}
INDUSTRY_SUBTYPES = {"industry_news"}
MACRO_SUBTYPES = {"macro_news"}

FINANCIAL_SUBTYPES = {
    "operating_revenue",
    "operating_cost",
    "operating_profit",
    "net_profit_parent",
    "gross_profit",
    "eps_basic",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "accounts_receivable",
    "inventory",
    "cash_and_equivalents",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "revenue_yoy",
    "net_profit_yoy",
    "gross_margin",
    "net_margin",
    "roe",
    "debt_to_asset_ratio",
    "ocf_to_net_profit",
    "main_business_segment",
}

MARKET_SPOT_SUBTYPES = {
    "close_price",
    "latest_price",
    "pe",
    "pb",
    "ps",
    "turnover_rate",
    "float_market_cap",
    "total_market_cap",
    "high_52w",
    "low_52w",
    "price_position_in_52w_range",
}

MARKET_DERIVED_SUBTYPES = {
    "ma5",
    "ma20",
    "ma60",
    "ma250",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "rsi_14",
}

PROFILE_SUBTYPES = {
    "stock_name",
    "industry",
    "listing_date",
    "total_shares",
    "float_shares",
}

EXPECTATION_SUBTYPES = {"eps_consensus"}


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    for fmt, n in (("%Y-%m-%d", 10), ("%Y/%m/%d", 10)):
        try:
            return datetime.strptime(text[:n], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def default_as_of_from_pack(pack: EvidencePack) -> date:
    d = parse_date(pack.generated_at)
    if d:
        return d
    return date.today()


def resolve_as_of(pack: EvidencePack, as_of: str | date | None = None) -> date:
    if as_of is None:
        return default_as_of_from_pack(pack)
    if isinstance(as_of, date):
        return as_of
    parsed = parse_date(str(as_of))
    if not parsed:
        raise ValueError(f"Invalid research_as_of_date: {as_of}")
    return parsed


@dataclass
class ResearchWindowPolicy:
    news_current_days: int = 7
    news_recent_days: int = 30  # previous upper bound; previous = 8..30
    company_event_days: int = 90
    industry_news_days: int = 30
    financial_history_years: int = 5
    market_trend_months: int = 6


@dataclass
class ResearchTimeContext:
    research_as_of_date: date
    policy: ResearchWindowPolicy = field(default_factory=ResearchWindowPolicy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_as_of_date": self.research_as_of_date.isoformat(),
            "policy": {
                "news_current_days": self.policy.news_current_days,
                "news_recent_days": self.policy.news_recent_days,
                "news_previous_range": "8-30d_non_overlapping",
                "company_event_days": self.policy.company_event_days,
                "industry_news_days": self.policy.industry_news_days,
                "financial_history_years": self.policy.financial_history_years,
                "market_trend_months": self.policy.market_trend_months,
            },
            "point_in_time_rule": "event_time.date <= research_as_of_date; retrieved_at is never business time",
        }


@dataclass
class ExclusionRecord:
    evidence_id: str
    reason: ExclusionReason
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "reason": self.reason,
            "detail": self.detail,
        }


def classify_role(evidence: Evidence) -> EvidenceRole:
    sub = evidence.subtype
    if sub in PROFILE_SUBTYPES:
        return "company_profile"
    if sub in FINANCIAL_SUBTYPES:
        return "financial_statement"
    if sub in MARKET_SPOT_SUBTYPES:
        return "market_spot"
    if sub in MARKET_DERIVED_SUBTYPES:
        return "market_derived"
    if sub in EXPECTATION_SUBTYPES or evidence.evidence_type == EvidenceType.EXPECTATION:
        return "expectation"
    if sub in COMPANY_EVENT_SUBTYPES:
        return "company_event"
    if sub in INDUSTRY_SUBTYPES:
        return "industry_news"
    if sub in MACRO_SUBTYPES:
        return "macro_news"
    if sub in NEWS_FLASH_SUBTYPES:
        return "news_flash"
    if evidence.evidence_type == EvidenceType.EVENT:
        return "news_flash"
    return "other"


def business_event_time(evidence: Evidence) -> tuple[date | None, TimeBasis]:
    """Return (event_date, basis). Never uses retrieved_at as business time."""
    role = classify_role(evidence)
    if role in {"news_flash", "company_event", "industry_news", "macro_news"}:
        d = parse_date(evidence.time.published_at)
        return d, ("published_at" if d else "none")
    if role == "financial_statement":
        d = parse_date(evidence.time.report_date)
        return d, ("report_date" if d else "none")
    if role in {"market_spot", "market_derived"}:
        d = parse_date(evidence.time.data_date)
        return d, ("data_date" if d else "none")
    if role == "expectation":
        d = parse_date(evidence.time.published_at) or parse_date(evidence.time.data_date)
        if parse_date(evidence.time.published_at):
            return d, "published_at"
        if parse_date(evidence.time.data_date):
            return d, "data_date"
        return None, "none"
    if role == "company_profile":
        # Profile facts: prefer data_date/report_date; listing_date may sit in claim/value
        d = parse_date(evidence.time.data_date) or parse_date(evidence.time.report_date)
        if d:
            return d, "data_date" if evidence.time.data_date else "report_date"
        # Allow profile without strict event day (static attributes) — treat as as_of-valid
        return None, "none"
    d = parse_date(evidence.time.published_at) or parse_date(evidence.time.data_date) or parse_date(
        evidence.time.report_date
    )
    basis: TimeBasis = "none"
    if evidence.time.published_at and parse_date(evidence.time.published_at):
        basis = "published_at"
    elif evidence.time.data_date and parse_date(evidence.time.data_date):
        basis = "data_date"
    elif evidence.time.report_date and parse_date(evidence.time.report_date):
        basis = "report_date"
    return d, basis


def is_post_as_of(evidence: Evidence, as_of: date) -> bool:
    event_dt, basis = business_event_time(evidence)
    if basis == "none" and classify_role(evidence) == "company_profile":
        return False  # static profile allowed
    if event_dt is None:
        return False  # handled as time_incomplete separately for windowed roles
    return event_dt > as_of


def age_days(event_dt: date, as_of: date) -> int:
    return (as_of - event_dt).days


def assign_window_bucket(
    evidence: Evidence,
    time_ctx: ResearchTimeContext,
) -> tuple[WindowBucket | None, ExclusionRecord | None]:
    """Assign a research window bucket, or exclusion reason."""
    as_of = time_ctx.research_as_of_date
    policy = time_ctx.policy
    role = classify_role(evidence)
    event_dt, basis = business_event_time(evidence)

    if event_dt is not None and event_dt > as_of:
        return None, ExclusionRecord(
            evidence.evidence_id,
            "post_as_of",
            f"event_time={event_dt.isoformat()} basis={basis} > as_of={as_of.isoformat()}",
        )

    # Static company profile: always company_profile if not post_as_of
    if role == "company_profile":
        return "company_profile", None

    if event_dt is None:
        # Windowed roles require business time
        if role in {
            "news_flash",
            "company_event",
            "industry_news",
            "macro_news",
            "financial_statement",
            "market_spot",
            "market_derived",
            "expectation",
        }:
            return None, ExclusionRecord(
                evidence.evidence_id,
                "time_incomplete",
                f"role={role} missing business event time (retrieved_at ignored)",
            )
        return None, ExclusionRecord(evidence.evidence_id, "out_of_window", f"role={role} unscoped")

    days = age_days(event_dt, as_of)

    if role == "news_flash":
        if 0 <= days <= policy.news_current_days - 1:
            # current: as_of-6 .. as_of for 7d inclusive → days 0..6
            return "news_current_7d", None
        if policy.news_current_days <= days <= policy.news_recent_days - 1:
            # previous 8-30d: days 7..29
            return "news_previous_8_30d", None
        return None, ExclusionRecord(
            evidence.evidence_id, "out_of_window", f"news age_days={days} outside 0-29"
        )

    if role == "company_event":
        if 0 <= days <= policy.company_event_days:
            return "company_events_90d", None
        return None, ExclusionRecord(
            evidence.evidence_id, "out_of_window", f"company_event age_days={days}"
        )

    if role == "industry_news":
        if 0 <= days <= policy.industry_news_days:
            return "industry_30d", None
        return None, ExclusionRecord(
            evidence.evidence_id, "out_of_window", f"industry age_days={days}"
        )

    if role == "macro_news":
        if 0 <= days <= policy.news_recent_days:
            return "macro_background", None
        return None, ExclusionRecord(
            evidence.evidence_id, "out_of_window", f"macro age_days={days}"
        )

    if role == "financial_statement":
        years = policy.financial_history_years
        if days <= years * 366:
            # Context builder promotes newest report_date rows to financial_latest
            return "financial_history", None
        return None, ExclusionRecord(
            evidence.evidence_id, "out_of_window", f"financial age_days={days}"
        )

    if role in {"market_spot", "market_derived"}:
        # spot: prefer latest day <= as_of; trend: within N months
        months = policy.market_trend_months
        if days <= months * 31:
            return "market_trend", None  # context builder splits spot vs trend
        return None, ExclusionRecord(
            evidence.evidence_id, "out_of_window", f"market age_days={days}"
        )

    if role == "expectation":
        # latest cross-section among <= as_of; allow within recent_days as soft bound
        if days <= max(policy.news_recent_days, 365):
            return "expectation_latest", None
        return None, ExclusionRecord(
            evidence.evidence_id, "out_of_window", f"expectation age_days={days}"
        )

    return None, ExclusionRecord(evidence.evidence_id, "out_of_window", f"role={role}")


def news_windows_non_overlapping(as_of: date, policy: ResearchWindowPolicy | None = None) -> dict[str, tuple[date, date]]:
    """Return inclusive date ranges for current vs previous news windows (non-overlapping)."""
    policy = policy or ResearchWindowPolicy()
    current_start = as_of - timedelta(days=policy.news_current_days - 1)  # 7d: as_of-6..as_of
    previous_end = as_of - timedelta(days=policy.news_current_days)  # as_of-7
    previous_start = as_of - timedelta(days=policy.news_recent_days - 1)  # as_of-29
    return {
        "news_current_7d": (current_start, as_of),
        "news_previous_8_30d": (previous_start, previous_end),
    }
