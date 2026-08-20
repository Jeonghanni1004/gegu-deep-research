"""Simple event deduplication without NLP."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Iterable

from .schema import Evidence, EvidenceType


def normalize_title(title: str | None) -> str:
    text = (title or "").lower().strip()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。！？、；：:“”\"'【】\[\]（）()《》<>·•|｜\-—_]", "", text)
    return text


def title_similarity(a: str, b: str) -> float:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # token-ish bigram Jaccard on characters
    def grams(s: str) -> set[str]:
        if len(s) < 2:
            return {s}
        return {s[i : i + 2] for i in range(len(s) - 1)}

    ga, gb = grams(na), grams(nb)
    inter = len(ga & gb)
    union = len(ga | gb) or 1
    return inter / union


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if " " in text else text[:10], fmt)
        except ValueError:
            continue
    return None


def mark_duplicates(evidences: list[Evidence], *, similarity_threshold: float = 0.82) -> list[Evidence]:
    """Mark suspected duplicate EVENTs; do not drop them."""
    events = [e for e in evidences if e.evidence_type == EvidenceType.EVENT]
    group_counter = 0
    assigned: dict[str, str] = {}

    for i, left in enumerate(events):
        if left.evidence_id in assigned:
            continue
        left_title = str((left.value or {}).get("title") or left.claim)
        left_time = _parse_dt(left.time.published_at)
        members = [left]
        for right in events[i + 1 :]:
            if right.evidence_id in assigned:
                continue
            if (left.stock_code or "") != (right.stock_code or ""):
                # allow both-null macro events to compare
                if left.stock_code or right.stock_code:
                    continue
            right_title = str((right.value or {}).get("title") or right.claim)
            sim = title_similarity(left_title, right_title)
            if sim < similarity_threshold:
                continue
            right_time = _parse_dt(right.time.published_at)
            if left_time and right_time:
                hours = abs((left_time - right_time).total_seconds()) / 3600.0
                if hours > 24:
                    continue
            members.append(right)
        if len(members) == 1:
            continue
        group_counter += 1
        group_id = f"dup_{group_counter:04d}_{hashlib.md5(left.evidence_id.encode()).hexdigest()[:8]}"
        canonical = members[0].evidence_id
        for idx, item in enumerate(members):
            assigned[item.evidence_id] = group_id
            item.metadata["duplicate_group_id"] = group_id
            item.metadata["duplicate_suspected"] = True
            if idx == 0:
                item.metadata["duplicate_canonical"] = True
            else:
                item.metadata["duplicate_of"] = canonical

    return evidences


def short_hash(*parts: str, n: int = 10) -> str:
    raw = "|".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:n]
