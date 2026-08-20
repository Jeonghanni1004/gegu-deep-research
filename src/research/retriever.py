"""Evidence Retriever: structured filtering over EvidencePack (no embeddings)."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Sequence

from evidence.pack import EvidencePack
from evidence.schema import Evidence, EvidenceType, FreshnessStatus


def _as_list(value: str | EvidenceType | FreshnessStatus | Sequence | None) -> list | None:
    if value is None:
        return None
    if isinstance(value, (str, EvidenceType, FreshnessStatus)):
        return [value]
    return list(value)


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


class EvidenceRetriever:
    """MVP structured filter. No semantic search / embedding / vector DB."""

    def __init__(self, pack: EvidencePack):
        self.pack = pack

    def query(
        self,
        *,
        stock_code: str | None = None,
        evidence_type: str | EvidenceType | Sequence[str | EvidenceType] | None = None,
        subtype: str | Sequence[str] | None = None,
        date_range: tuple[str, str] | None = None,
        freshness: str | FreshnessStatus | Sequence[str | FreshnessStatus] | None = None,
        source: str | Sequence[str] | None = None,
        limit: int | None = None,
    ) -> list[Evidence]:
        types = _as_list(evidence_type)
        subtypes = _as_list(subtype)
        freshness_list = _as_list(freshness)
        sources = _as_list(source)

        type_set: set[str] | None = None
        if types is not None:
            type_set = {
                (t.value if isinstance(t, EvidenceType) else str(t).upper()) for t in types
            }

        subtype_set: set[str] | None = None
        if subtypes is not None:
            subtype_set = {str(s) for s in subtypes}

        freshness_set: set[str] | None = None
        if freshness_list is not None:
            freshness_set = {
                (f.value if isinstance(f, FreshnessStatus) else str(f)) for f in freshness_list
            }

        source_list: list[str] | None = None
        if sources is not None:
            source_list = [str(s).lower() for s in sources]

        start_dt = end_dt = None
        if date_range is not None:
            start_dt = _parse_date(date_range[0])
            end_dt = _parse_date(date_range[1])

        out: list[Evidence] = []
        for e in self.pack.evidence:
            if stock_code is not None:
                code = e.stock_code or self.pack.stock_code
                if code != stock_code:
                    continue
            if type_set is not None and e.evidence_type.value not in type_set:
                continue
            if subtype_set is not None and e.subtype not in subtype_set:
                continue
            if freshness_set is not None and e.freshness.status.value not in freshness_set:
                continue
            if source_list is not None:
                provider = (e.source.provider or "").lower()
                if not any(s in provider for s in source_list):
                    continue
            if start_dt is not None and end_dt is not None:
                hit = False
                for c in (e.time.published_at, e.time.data_date, e.time.report_date):
                    dt = _parse_date(c)
                    if dt and start_dt <= dt <= end_dt:
                        hit = True
                        break
                if not hit:
                    continue
            out.append(e)

        if limit is not None and limit >= 0:
            out = out[:limit]
        return out

    def get_by_type(self, evidence_type: str | EvidenceType | Sequence[str | EvidenceType]) -> list[Evidence]:
        return self.query(evidence_type=evidence_type)

    def get_by_subtype(self, subtype: str | Sequence[str]) -> list[Evidence]:
        return self.query(subtype=subtype)

    def get_recent(self, *, hours: float = 24 * 7, limit: int | None = None) -> list[Evidence]:
        out = []
        for e in self.pack.evidence:
            age = e.freshness.age_hours
            if age is None:
                continue
            if age <= hours:
                out.append(e)
        if limit is not None:
            out = out[:limit]
        return out

    def get_by_date_range(self, start: str, end: str, *, limit: int | None = None) -> list[Evidence]:
        return self.query(date_range=(start, end), limit=limit)

    def get_by_source(self, source: str | Sequence[str], *, limit: int | None = None) -> list[Evidence]:
        return self.query(source=source, limit=limit)

    def serialize(self, items: Iterable[Evidence]) -> list[dict]:
        """Compact evidence payload for LLM context."""
        rows = []
        for e in items:
            rows.append(
                {
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
            )
        return rows
