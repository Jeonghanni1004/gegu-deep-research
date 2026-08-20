"""Citation completeness for research findings.

Facts mentioned in claim/reasoning/interpretation must be supportable by the
finding's own evidence_ids — not merely present somewhere in the pack.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from evidence.pack import EvidencePack
from evidence.schema import Evidence

from research.schemas import CitedFinding, FundamentalResearch, MarketResearch, ResearchSection

# Numbers like 33.65, 4.53%, 1341.99, 2025-12-31 (dates handled separately lightly)
_NUM_RE = re.compile(
    r"(?<![A-Za-z0-9_])"  # avoid evidence_id fragments roughly
    r"("
    r"\d{4}-\d{2}-\d{2}"  # dates
    r"|\d+\.\d+%?"  # decimals / pct
    r"|\d{2,}%?"  # integers length>=2 (skip 1-digit noise)
    r")"
)


def extract_fact_tokens(text: str) -> list[str]:
    if not text:
        return []
    found = _NUM_RE.findall(text)
    # Keep tokens exactly as they appear in text (do not invent '%' variants here).
    seen = set()
    uniq: list[str] = []
    for t in found:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def evidence_support_blob(evidence: Evidence) -> str:
    return " ".join(
        [
            evidence.claim or "",
            json.dumps(evidence.value or {}, ensure_ascii=False),
            evidence.time.report_date or "",
            evidence.time.data_date or "",
            evidence.time.published_at or "",
        ]
    )


def _token_in_blob(token: str, blob: str) -> bool:
    if token in blob:
        return True
    # Allow percentage written as ratio in value e.g. 0.3365 for 33.65%
    if token.endswith("%"):
        try:
            pct = float(token[:-1])
            candidates = [
                f"{pct / 100:.6f}".rstrip("0").rstrip("."),
                f"{pct / 100:.4f}",
                f"{pct / 100:.2f}",
                str(pct / 100),
            ]
            return any(c and c in blob for c in candidates)
        except ValueError:
            return False
    # Bare decimal may appear with trailing % in claim
    if re.fullmatch(r"\d+\.\d+", token) and (token + "%") in blob:
        return True
    return False


def tokens_supported(tokens: Iterable[str], evidences: list[Evidence]) -> tuple[list[str], list[str]]:
    blob = " ".join(evidence_support_blob(e) for e in evidences)
    ok: list[str] = []
    missing: list[str] = []
    for t in tokens:
        if _token_in_blob(t, blob):
            ok.append(t)
        else:
            missing.append(t)
    return ok, missing


def validate_finding_citations(
    finding: CitedFinding,
    pack: EvidencePack,
) -> list[str]:
    """Return list of error messages (empty if ok)."""
    errors: list[str] = []
    if finding.status == "insufficient_evidence":
        return errors
    # Reference stubs point at canonical findings; citation checked on the canonical.
    if getattr(finding, "finding_kind", None) == "reference":
        return errors
    if not finding.evidence_ids:
        errors.append("supported finding missing evidence_ids")
        return errors

    by_id = {e.evidence_id: e for e in pack.evidence}
    cited: list[Evidence] = []
    for eid in finding.evidence_ids:
        if eid not in by_id:
            errors.append(f"unknown evidence_id={eid}")
        else:
            cited.append(by_id[eid])
    if errors:
        return errors

    text = " ".join(
        [
            finding.claim or "",
            getattr(finding, "reasoning", "") or "",
            finding.interpretation or "",
        ]
    )
    tokens = extract_fact_tokens(text)
    # Filter tokens that are too generic / claim_id style noise
    filtered = []
    for t in tokens:
        if re.fullmatch(r"\d{1,2}", t):  # 1-2 digit bare ints often noise
            continue
        if t in {"20", "14", "5", "60", "250"}:  # MA window labels often appear without being data
            # still require support if they appear as MA values — keep if decimal
            continue
        filtered.append(t)

    _, missing = tokens_supported(filtered, cited)
    for m in missing:
        errors.append(
            f"fact token {m!r} in finding text not supported by cited evidence_ids={finding.evidence_ids}"
        )
    return errors


def iter_findings(research: FundamentalResearch | MarketResearch) -> list[CitedFinding]:
    out: list[CitedFinding] = []
    data = research.model_dump()
    for key, val in data.items():
        if key in {
            "cross_evidence_findings",
            "research_tensions",
            "key_strengths",
            "key_weaknesses",
            "key_uncertainties",
            "core_facts",
            "key_research_findings",
            "evidence_gaps",
            "canonical_findings",
        }:
            if isinstance(val, list):
                for item in val:
                    out.append(CitedFinding.model_validate(item))
        elif isinstance(val, dict) and "findings" in val:
            out.extend(ResearchSection.model_validate(val).findings)
    return out


def validate_research_citations(
    research: FundamentalResearch | MarketResearch,
    pack: EvidencePack,
) -> list[str]:
    errors: list[str] = []
    for i, f in enumerate(iter_findings(research)):
        for err in validate_finding_citations(f, pack):
            errors.append(f"finding[{i}] {err}")
    return errors
