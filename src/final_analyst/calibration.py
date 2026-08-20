"""Judgment calibration — Debate support strength vs allowed FA claim amplitude.

Debate resolution is an *input* to judgment, not the answer.
support_strength ∈ {weak, moderate, strong} controls how far FA may move —
never investment probability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from research.schemas import CanonicalFinding

from final_analyst.schemas import AssessmentStrength, ResolutionKind

SupportStrength = Literal["weak", "moderate", "strong"]
EvidencePressure = Literal["mild", "elevated", "severe"]
InferenceStatus = Literal["SUPPORTED", "DERIVED", "CONDITIONAL", "UNSUPPORTED"]

# Map debate support strength → FA assessment_strength vocabulary (v2 compatible)
SUPPORT_TO_ASSESSMENT: dict[SupportStrength, AssessmentStrength] = {
    "weak": "tentative",
    "moderate": "moderate",
    "strong": "strong",
}

# Phrases that overclaim relative to support strength
_OVERCLAIM_WEAK = (
    "已经改善",
    "已经证明",
    "基本面已经",
    "增长逻辑已经失效",
    "已确认结构性",
    "已确认阶段性",
    "无争议",
    "确定性结论",
    "具有确定性",
)
_OVERCLAIM_MODERATE = (
    "已经证明",
    "无争议地",
    "已确认无争议",
    "确定性结论",
    "具有确定性",
)
_OVERCLAIM_STRONG = (
    "已经证明",
    "已确认无争议",
    "百分之百",
    "确定性结论",
)

# External / unsupported narrative markers (must reject)
UNSUPPORTED_MARKET_MARKERS = (
    "投资者愿意给予估值溢价",
    "市场已经重新定价",
    "投资者预期改善",
    "行业景气即将恢复",
    "市场情绪已经逆转",
    "资金已经抢筹",
    "外网研报",
    "必涨",
    "必跌",
)


def normalize_support_strength(raw: str | None, *, resolution: ResolutionKind) -> SupportStrength | None:
    """Accept weak/moderate/strong; map legacy tentative→weak, unresolved→None."""
    if resolution == "unresolved":
        return None
    if not raw:
        return "moderate"
    r = str(raw).lower().strip()
    if r in {"weak", "tentative"}:
        return "weak"
    if r == "moderate":
        return "moderate"
    if r == "strong":
        return "strong"
    if r == "unresolved":
        return None
    return "moderate"


def assessment_from_support(support: SupportStrength | None, *, resolution: ResolutionKind) -> AssessmentStrength:
    if resolution == "unresolved":
        return "unresolved"
    if support is None:
        return "tentative"
    return SUPPORT_TO_ASSESSMENT[support]


def evidence_pressure(findings: list[CanonicalFinding]) -> EvidencePressure:
    """Research-side stress fingerprint — independent of Debate resolution.

    Primary (first) finding dominates so same-resolution / different-evidence
    fixtures can differentiate without mutating every tension.
    """
    if not findings:
        return "mild"

    def _score(blob: str) -> int:
        # Negated stress phrases must not count as stress
        blob = re.sub(r"未见.{0,8}恶化", "", blob)
        blob = re.sub(r"并非.{0,8}恶化", "", blob)
        blob = re.sub(r"没有.{0,8}恶化", "", blob)
        local = 0
        if re.search(r"显著下滑|大幅下降|明显恶化|同步恶化|恶化", blob):
            local += 3
        if re.search(r"现金流.*(下降|恶化|承压)|经营现金流.*(降|负)", blob):
            local += 2
        if re.search(r"同比.*(下降|下滑|减少)|承压|下降", blob):
            local += 1
        if re.search(r"轻微|小幅|稳定|稳健", blob):
            local -= 2
        return local

    score = _score(f"{findings[0].finding_id} {findings[0].claim} {' '.join(findings[0].numbers_preserved or [])}") * 2
    for c in findings[1:3]:
        score += max(0, _score(f"{c.finding_id} {c.claim} {' '.join(c.numbers_preserved or [])}"))
    if score >= 5:
        return "severe"
    if score >= 2:
        return "elevated"
    return "mild"


def calibrated_frame_phrase(
    *,
    resolution: ResolutionKind,
    support: SupportStrength | None,
    pressure: EvidencePressure,
) -> str:
    """Allowed interpretive amplitude — Debate × Research pressure."""
    if resolution == "unresolved":
        return "事实清楚、解释未决；不得机械中性，也不得越权裁定"

    if resolution == "bull_supported":
        if support == "weak":
            core = "阶段性压力解释获得一定支持（有限幅度判断变化）"
        elif support == "strong":
            core = "主导解释更明确偏向盈利缓冲 / 非结构性恶化框架（仍非确定事实）"
        else:
            core = "当前更明确偏向盈利缓冲有效、增长压力尚未被证伪为结构性（仍保留条件）"
        if pressure == "severe":
            return (
                f"{core}；但 Research 事实结构显示增长/现金流压力偏重，"
                f"因此 Debate bull_supported 不能机械等于乐观结论，FA 仅给予受限建设性权重"
            )
        if pressure == "mild":
            return f"{core}；Research 侧增长压力相对温和、缓冲事实更相容，判断幅度可略清晰但仍条件化"
        return core

    if resolution == "bear_supported":
        if support == "weak":
            core = "谨慎解释获得一定支持（有限幅度判断变化），不得写成增长逻辑已经失效"
        elif support == "strong":
            core = "主导解释更明确偏向增长不确定性优先（仍非确定事实）"
        else:
            core = "当前更明确偏向增长不确定性主导、估值依赖恢复验证（仍保留条件）"
        if pressure == "severe":
            return f"{core}；Research 恶化结构与 Debate 同向，谨慎权重可上升但仍不得写成已证明崩塌"
        if pressure == "mild":
            return f"{core}；Research 压力偏温和，故即便 bear_supported 也不得过度翻转"
        return core

    # partially_resolved
    return "解释框架仅部分收敛；增长验证仍是主要变量，单边叙事不得超过 support_strength 允许幅度"


def detect_overclaim(text: str, support: SupportStrength | None, *, resolution: ResolutionKind) -> list[str]:
    errs: list[str] = []
    if resolution == "unresolved":
        for bad in ("已经证明", "基本面已经改善", "增长逻辑已经失效"):
            if bad in text:
                errs.append(f"calibration_overclaim: unresolved+{bad}")
        return errs
    banned = _OVERCLAIM_WEAK if support in {None, "weak"} else _OVERCLAIM_MODERATE if support == "moderate" else _OVERCLAIM_STRONG
    for bad in banned:
        if bad in text:
            # Avoid false positive: 「不确定性」contains 「确定性」as substring — already removed bare 确定性
            errs.append(f"calibration_overclaim: {support or 'weak'}+{bad}")
    return errs


def detect_unsupported_inference(text: str) -> list[str]:
    return [f"unsupported_inference: {m}" for m in UNSUPPORTED_MARKET_MARKERS if m in text]


def classify_inference_status(text: str, *, kind: str) -> InferenceStatus:
    if kind == "FACT":
        return "SUPPORTED"
    if any(m in text for m in UNSUPPORTED_MARKET_MARKERS):
        return "UNSUPPORTED"
    if any(k in text for k in ("若", "如果", "在……情况下", "假设", "条件")):
        return "CONDITIONAL"
    if any(k in text for k in ("连接", "跨 tension", "中间条件", "组合", "因此增长不确定性不仅")):
        return "DERIVED"
    return "DERIVED"


def judgment_amplitude_rank(support: SupportStrength | None, *, resolution: ResolutionKind) -> int:
    """Ordered differentiation for calibration tests (not probability)."""
    if resolution == "unresolved":
        return 0
    base = {"weak": 1, "moderate": 2, "strong": 3}.get(support or "weak", 1)
    if resolution in {"bull_supported", "bear_supported"}:
        return base
    return max(1, base - 1)


# ---------------------------------------------------------------------------
# Round-5 formal calibration matrix
# Resolution × Support × EvidencePressure → Assessment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibratedAssessment:
    assessment_strength: AssessmentStrength
    support_strength: SupportStrength | None
    evidence_pressure: EvidencePressure
    limiting_factors: list[str]
    rationale: str
    inference_status: InferenceStatus


def _pressure_cap(strength: AssessmentStrength, pressure: EvidencePressure) -> AssessmentStrength:
    """severe pressure caps strong → moderate (never certainty)."""
    if pressure != "severe":
        return strength
    if strength == "strong":
        return "moderate"
    return strength


def calibrate_assessment(
    resolution: ResolutionKind,
    support_strength: SupportStrength | None,
    evidence_pressure: EvidencePressure,
    research_boundaries: list[str] | None = None,
) -> CalibratedAssessment:
    """Formal matrix: Debate strength is monotonic but pressure/boundaries clamp amplitude.

    Principles:
    - weak ≠ certainty
    - strong ≠ fact
    - unresolved ≠ neutral average
    - bull_supported ≠ bullish conclusion
    - bear_supported ≠ bearish conclusion
    """
    boundaries = [b for b in (research_boundaries or []) if b]
    limiting: list[str] = []
    support = normalize_support_strength(support_strength, resolution=resolution)
    if resolution == "unresolved":
        strength: AssessmentStrength = "unresolved"
        if evidence_pressure == "severe":
            strength = "tentative"  # severe facts + unresolved → tentative caution frame, still unresolved intent
            # Keep unresolved as primary label when Debate unresolved; pressure elevates limiting factors
            strength = "unresolved"
            limiting.append("severe_evidence_pressure_with_unresolved_debate")
        rationale = (
            "unresolved Debate：不得机械中性，也不得越权裁定；"
            f"evidence_pressure={evidence_pressure}"
        )
        if boundaries:
            limiting.extend(boundaries[:3])
            rationale += "；受 Research uncertainty_boundaries 约束"
        return CalibratedAssessment(
            assessment_strength=strength,
            support_strength=None,
            evidence_pressure=evidence_pressure,
            limiting_factors=limiting,
            rationale=rationale,
            inference_status="CONDITIONAL",
        )

    # Mapped base from support
    base = assessment_from_support(support, resolution=resolution)
    capped = _pressure_cap(base, evidence_pressure)

    if evidence_pressure == "severe":
        limiting.append("severe_research_pressure_caps_amplitude")
    if evidence_pressure == "mild" and support == "strong":
        limiting.append("mild_pressure_allows_clearer_but_still_conditional_frame")
    if boundaries:
        limiting.extend([f"boundary:{b[:40]}" for b in boundaries[:3]])
        # Boundaries force at least one notch down from strong
        if capped == "strong":
            capped = "moderate"
            limiting.append("uncertainty_boundary_blocks_strong")

    if resolution == "bull_supported":
        side = "建设性解释可更清晰，但不得写成已证实改善"
    elif resolution == "bear_supported":
        side = "谨慎解释可更清晰，但不得写成增长逻辑已经失效"
    else:
        side = "部分收敛；单边叙事不得超过 support 允许幅度"

    rationale = (
        f"matrix[{resolution}|{support}|{evidence_pressure}] → {capped}; {side}; "
        f"frame={calibrated_frame_phrase(resolution=resolution, support=support, pressure=evidence_pressure)[:80]}"
    )
    status: InferenceStatus = "CONDITIONAL" if capped in {"tentative", "unresolved"} else "DERIVED"
    return CalibratedAssessment(
        assessment_strength=capped,
        support_strength=support,
        evidence_pressure=evidence_pressure,
        limiting_factors=limiting,
        rationale=rationale,
        inference_status=status,
    )


def assessment_rank(strength: AssessmentStrength | None) -> int:
    return {"unresolved": 0, "tentative": 1, "moderate": 2, "strong": 3}.get(strength or "unresolved", 0)


def is_monotonic_support_to_assessment(
    *,
    resolution: ResolutionKind,
    pressure: EvidencePressure = "elevated",
) -> bool:
    """weak ≤ moderate ≤ strong in assessment rank under fixed pressure/resolution."""
    if resolution == "unresolved":
        return True
    ranks = [
        assessment_rank(
            calibrate_assessment(resolution, s, pressure, None).assessment_strength
        )
        for s in ("weak", "moderate", "strong")
    ]
    return ranks[0] <= ranks[1] <= ranks[2]
