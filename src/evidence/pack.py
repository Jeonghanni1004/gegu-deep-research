"""EvidencePack: queryable collection of Evidence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .schema import Evidence, EvidenceType, assert_no_opinion_fields, utc_now_iso


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if " " in text else text[:10], fmt)
        except ValueError:
            continue
    return None


def _event_sort_key(e: Evidence) -> str:
    return e.time.published_at or e.time.data_date or e.time.report_date or e.time.retrieved_at or ""


class EvidencePack:
    def __init__(
        self,
        *,
        stock_code: str,
        evidence: list[Evidence] | None = None,
        generated_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.stock_code = stock_code
        self.generated_at = generated_at or utc_now_iso()
        self.evidence: list[Evidence] = list(evidence or [])
        self.metadata = metadata or {}

    def add(self, item: Evidence) -> None:
        self.evidence.append(item)

    def extend(self, items: Iterable[Evidence]) -> None:
        self.evidence.extend(items)

    def get_by_type(self, evidence_type: EvidenceType | str) -> list[Evidence]:
        et = EvidenceType(evidence_type)
        return [e for e in self.evidence if e.evidence_type == et]

    def get_by_subtype(self, subtype: str) -> list[Evidence]:
        return [e for e in self.evidence if e.subtype == subtype]

    def get_by_source(self, provider: str) -> list[Evidence]:
        provider_l = provider.lower()
        return [e for e in self.evidence if provider_l in e.source.provider.lower()]

    def get_recent(self, *, hours: float = 24 * 7) -> list[Evidence]:
        out = []
        for e in self.evidence:
            age = e.freshness.age_hours
            if age is None:
                continue
            if age <= hours:
                out.append(e)
        return out

    def get_by_date_range(self, start: str, end: str) -> list[Evidence]:
        start_dt = _parse_date(start)
        end_dt = _parse_date(end)
        if not start_dt or not end_dt:
            return []
        out = []
        for e in self.evidence:
            candidates = [
                e.time.published_at,
                e.time.data_date,
                e.time.report_date,
            ]
            hit = False
            for c in candidates:
                dt = _parse_date(c)
                if dt and start_dt <= dt <= end_dt:
                    hit = True
                    break
            if hit:
                out.append(e)
        return out

    def get_company_events(self) -> list[Evidence]:
        return [
            e
            for e in self.get_by_type(EvidenceType.EVENT)
            if e.subtype in {"announcement", "shareholder_change", "company_news"}
            or (e.value or {}).get("category") == "company"
        ]

    def get_expectations(self) -> list[Evidence]:
        return self.get_by_type(EvidenceType.EXPECTATION)

    def get_fundamental_facts(self) -> list[Evidence]:
        fund_subtypes = {
            "operating_revenue",
            "operating_cost",
            "operating_profit",
            "net_profit_parent",
            "gross_profit",
            "eps_basic",
            "total_assets",
            "total_liabilities",
            "total_equity",
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
            "main_business_segment",
            "industry",
            "total_shares",
            "float_shares",
            "total_market_cap",
            "revenue_yoy",
            "net_profit_yoy",
            "gross_margin",
            "net_margin",
            "roe",
            "debt_to_asset_ratio",
            "ocf_to_net_profit",
        }
        return [
            e
            for e in self.evidence
            if e.evidence_type in {EvidenceType.FACT, EvidenceType.DERIVED} and e.subtype in fund_subtypes
        ]

    def get_market_facts(self) -> list[Evidence]:
        market_subtypes = {
            "close_price",
            "latest_price",
            "pe",
            "pb",
            "ps",
            "turnover_rate",
            "float_market_cap",
            "ma5",
            "ma20",
            "ma60",
            "ma250",
            "macd_dif",
            "macd_dea",
            "macd_hist",
            "rsi_14",
            "high_52w",
            "low_52w",
            "price_position_in_52w_range",
        }
        return [
            e
            for e in self.evidence
            if e.evidence_type in {EvidenceType.FACT, EvidenceType.DERIVED} and e.subtype in market_subtypes
        ]

    def validate(self) -> None:
        ids = [e.evidence_id for e in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence_id must be unique within EvidencePack")
        payload = self.to_dict()
        assert_no_opinion_fields(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "generated_at": self.generated_at,
            "evidence_count": len(self.evidence),
            "counts_by_type": {
                t.value: len(self.get_by_type(t)) for t in EvidenceType
            },
            "evidence": [e.to_public_dict() for e in self.evidence],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidencePack":
        items = [Evidence.model_validate(e) for e in payload.get("evidence") or []]
        return cls(
            stock_code=str(payload.get("stock_code") or ""),
            evidence=items,
            generated_at=payload.get("generated_at"),
            metadata=payload.get("metadata") or {},
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "EvidencePack":
        import json

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def summary_for_recent_facts(self, *, days: int = 30) -> list[dict[str, Any]]:
        """Helper for humans/agents: recent events + always-on fundamentals snapshot pointers."""
        end = datetime.now()
        start = end.fromordinal(end.toordinal() - days)
        recent_events = sorted(
            self.get_by_date_range(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d %H:%M:%S")),
            key=_event_sort_key,
            reverse=True,
        )
        recent_events = [e for e in recent_events if e.evidence_type == EvidenceType.EVENT]
        return [
            {
                "evidence_id": e.evidence_id,
                "type": e.evidence_type.value,
                "subtype": e.subtype,
                "claim": e.claim,
                "source": e.source.provider,
                "url": e.source.url,
                "published_at": e.time.published_at,
                "report_date": e.time.report_date,
            }
            for e in recent_events
        ]
