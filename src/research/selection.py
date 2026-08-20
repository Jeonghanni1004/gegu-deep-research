"""Weight-aware candidate selection for research findings.

Does not redefine weight; reuses debate.evidence_weight via priority.
"""

from __future__ import annotations

from typing import Any, Iterable


def select_by_weight(
    candidates: Iterable[dict[str, Any]],
    *,
    n: int = 1,
    min_weight: float | None = None,
) -> list[dict[str, Any]]:
    """Pick top-n candidates by weight (desc). Optional min_weight filter."""
    rows = [c for c in candidates if c is not None]
    if min_weight is not None:
        rows = [c for c in rows if float(c.get("weight") or 0) >= min_weight]
    rows.sort(key=lambda c: float(c.get("weight") or 0), reverse=True)
    return rows[: max(n, 0)]


def select_best_per_subtype(
    candidates: Iterable[dict[str, Any]],
    subtypes: list[str],
) -> list[dict[str, Any]]:
    """For each subtype, keep the highest-weight row (if any)."""
    by_sub: dict[str, list[dict[str, Any]]] = {s: [] for s in subtypes}
    for c in candidates:
        if not c:
            continue
        sub = str(c.get("subtype") or "")
        if sub in by_sub:
            by_sub[sub].append(c)
    out: list[dict[str, Any]] = []
    for sub in subtypes:
        picked = select_by_weight(by_sub[sub], n=1)
        if picked:
            out.append(picked[0])
    return out


def explain_selection(selected: dict[str, Any], rejected: list[dict[str, Any]]) -> str:
    """Short audit note: why this evidence was chosen."""
    w = selected.get("weight")
    eid = selected.get("evidence_id")
    if not rejected:
        return f"selected {eid} weight={w}"
    top_rej = rejected[0]
    return (
        f"selected {eid} weight={w} over {top_rej.get('evidence_id')} "
        f"weight={top_rej.get('weight')} (higher research priority)"
    )
