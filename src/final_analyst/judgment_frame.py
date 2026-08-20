"""JudgmentFrame — structured judgment signature for benchmark / drift.

Round 7: primary_axis is Research/Debate structure-first; keyword text is last resort.
Derived from FinalAnalystOutput (+ optional Input); does not extend FA business schema.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from final_analyst.contract import FinalAnalystInput, all_canonical
from final_analyst.live_quality import analytical_increment_signals, scenario_boundary_ok
from final_analyst.schemas import FinalAnalystOutput
from final_analyst.semantic import (
    has_cross_tension_semantics,
    has_new_evidence_boundary,
    has_unresolved_semantics,
)

PrimaryAxis = Literal[
    "growth_vs_profitability",
    "valuation_vs_growth",
    "volume_vs_margin",
    "utilization_vs_asp",
    "fundamental_vs_market",
    "cycle_vs_capex",
    "unknown",
]
DebateState = Literal["unresolved", "bull_supported", "bear_supported", "partially_resolved", "unknown"]
ScenarioDirection = Literal["conditional", "factual_overclaim", "unknown"]
UncertaintyState = Literal["preserved", "erased", "unknown"]


class JudgmentFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_axis: PrimaryAxis = "unknown"
    secondary_axis: str = ""
    assessment_strength: str = "unknown"
    debate_state: DebateState = "unknown"
    support_strength: str | None = None
    pressure_level: str | None = None
    scenario_direction: ScenarioDirection = "unknown"
    cross_tension: bool = False
    contradiction_handling: bool = False
    decision_boundary: bool = False
    uncertainty_state: UncertaintyState = "unknown"
    valuation_dependency: str = ""
    market_signal_role: str = ""


class JudgmentCompareResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acceptable: bool
    score: float
    mismatches: list[str] = Field(default_factory=list)
    actual: JudgmentFrame | None = None
    expected: JudgmentFrame | None = None


# Structure markers (finding / tension ids) — prefer over fragile wording
_STRUCTURE_AXIS: list[tuple[PrimaryAxis, tuple[str, ...]]] = [
    ("volume_vs_margin", ("VOLUME_VS_MARGIN", "MFG_VOLUME", "量增利不增")),
    ("utilization_vs_asp", ("SEMI_UTIL", "UTIL_VS_ASP", "UTILIZATION_VS_ASP")),
    ("growth_vs_profitability", ("PROFIT_VS_GROWTH", "GROWTH_VS_PROFIT")),
    ("valuation_vs_growth", ("VALUATION_VS_GROWTH",)),
    ("fundamental_vs_market", ("SHORT_VS_LONG", "FUND_VS_MKT", "FUNDAMENTAL_VS_MARKET")),
    ("cycle_vs_capex", ("CYCLE_VS_CAPEX", "CAPEX_VS_CYCLE")),
]

# Text fallback — intentionally stricter than Round 6 (no bare 毛利率/销量 → volume)
_TEXT_AXIS_FALLBACK: list[tuple[PrimaryAxis, tuple[str, ...]]] = [
    ("volume_vs_margin", ("量增利不增", "VOLUME_VS_MARGIN")),
    ("utilization_vs_asp", ("产能利用率", "SEMI_UTIL", "利用率与ASP", "ASP 承压")),
    ("growth_vs_profitability", ("盈利强", "增长弱", "增长承压", "PROFIT_VS_GROWTH", "营收同比", "净利润同比")),
    ("valuation_vs_growth", ("估值与增长", "VALUATION_VS_GROWTH")),
    ("fundamental_vs_market", ("基本面与市场", "SHORT_VS_LONG")),
    ("cycle_vs_capex", ("资本开支与周期", "CAPEX")),
]


def _collect_structure_ids(out: FinalAnalystOutput, inp: FinalAnalystInput | None) -> str:
    parts: list[str] = [t.tension_id for t in out.core_tensions]
    parts.extend(out.meta.selected_tension_ids or [])
    if inp is not None:
        parts.extend(c.finding_id for c in all_canonical(inp))
    return " ".join(parts)


def _infer_primary_axis(out: FinalAnalystOutput, inp: FinalAnalystInput | None = None) -> PrimaryAxis:
    struct = _collect_structure_ids(out, inp)
    for axis, keys in _STRUCTURE_AXIS:
        if any(k in struct for k in keys):
            return axis

    blob = " ".join(
        [
            out.executive_assessment.text,
            out.core_thesis.text,
            " ".join(t.tension_id for t in out.core_tensions),
        ]
    )
    for axis, keys in _TEXT_AXIS_FALLBACK:
        if any(k in blob for k in keys):
            return axis
    return "unknown"


def extract_judgment_frame(
    out: FinalAnalystOutput,
    inp: FinalAnalystInput | None = None,
) -> JudgmentFrame:
    sig = analytical_increment_signals(out)
    res = out.meta.primary_resolution or out.assessment_basis.primary_resolution or "unknown"
    # If input provided, prefer contract resolution for debate_state (hard contract)
    if inp is not None:
        from final_analyst.contract_pin import contract_resolution

        pinned_res, _, _ = contract_resolution(inp)
        res = pinned_res
    debate_state: DebateState = (
        res if res in {"unresolved", "bull_supported", "bear_supported", "partially_resolved"} else "unknown"
    )
    unc_blob = " ".join(u.text for u in out.uncertainty) + out.executive_assessment.text + out.base_case.thesis.text
    if debate_state == "unresolved":
        uncertainty_state: UncertaintyState = "preserved" if has_unresolved_semantics(unc_blob) else "erased"
    else:
        uncertainty_state = "preserved" if out.uncertainty or out.research_gaps else "unknown"

    scenario_direction: ScenarioDirection = (
        "conditional"
        if scenario_boundary_ok(out)
        or (
            has_new_evidence_boundary(out.bull_case.thesis.text)
            and has_new_evidence_boundary(out.bear_case.thesis.text)
        )
        else "factual_overclaim"
    )

    return JudgmentFrame(
        primary_axis=_infer_primary_axis(out, inp),
        secondary_axis=",".join(t.tension_id for t in out.core_tensions[1:3]),
        assessment_strength=out.meta.assessment_strength or "unknown",
        debate_state=debate_state,
        support_strength=out.meta.debate_support_strength,
        pressure_level=out.meta.evidence_pressure or out.assessment_basis.evidence_pressure,
        scenario_direction=scenario_direction,
        cross_tension=bool(sig.get("cross_tension")) or has_cross_tension_semantics(out.executive_assessment.text),
        contradiction_handling=bool(sig.get("contradiction")),
        decision_boundary=bool(sig.get("decision_boundary")),
        uncertainty_state=uncertainty_state,
        valuation_dependency="growth_recovery"
        if "估值" in out.executive_assessment.text or "PE" in out.executive_assessment.text
        else "",
        market_signal_role="corroborative"
        if "市场" in out.executive_assessment.text or "均线" in out.executive_assessment.text
        else "",
    )


def judgment_signature(frame: JudgmentFrame) -> str:
    return "|".join(
        [
            frame.primary_axis,
            frame.assessment_strength,
            frame.debate_state,
            frame.scenario_direction,
            frame.pressure_level or "",
            frame.support_strength or "",
            "xt" if frame.cross_tension else "",
            frame.uncertainty_state,
        ]
    )


_STRENGTH_RANK = {"unresolved": 0, "tentative": 1, "moderate": 2, "strong": 3, "unknown": -1}


def compare_judgment_frame(actual: JudgmentFrame, expected: JudgmentFrame) -> JudgmentCompareResult:
    """Structural compare — not full-text. Allows wording-equivalent axes.

    Round 7: thresholds UNCHANGED from Round 6 (do not widen to manufacture pass).
    """
    mismatches: list[str] = []
    score = 1.0

    if expected.primary_axis != "unknown" and actual.primary_axis != expected.primary_axis:
        if not (
            expected.primary_axis == "growth_vs_profitability"
            and actual.primary_axis in {"valuation_vs_growth", "fundamental_vs_market"}
        ):
            mismatches.append(f"primary_axis:{actual.primary_axis}!={expected.primary_axis}")
            score -= 0.25

    if expected.debate_state != "unknown" and actual.debate_state != expected.debate_state:
        mismatches.append(f"debate_state:{actual.debate_state}!={expected.debate_state}")
        score -= 0.3

    if expected.assessment_strength != "unknown":
        ar = _STRENGTH_RANK.get(actual.assessment_strength, -1)
        er = _STRENGTH_RANK.get(expected.assessment_strength, -1)
        if ar >= 0 and er >= 0 and abs(ar - er) > 1:
            mismatches.append(f"assessment_strength:{actual.assessment_strength}!~{expected.assessment_strength}")
            score -= 0.25

    if expected.scenario_direction == "conditional" and actual.scenario_direction != "conditional":
        mismatches.append("scenario_direction:not_conditional")
        score -= 0.2

    if expected.uncertainty_state == "preserved" and actual.uncertainty_state == "erased":
        mismatches.append("uncertainty_erased")
        score -= 0.3

    if expected.pressure_level == "severe" and actual.assessment_strength == "strong":
        if (actual.pressure_level or "") == "severe":
            mismatches.append("severe_pressure_uncapped_strong")
            score -= 0.2

    if expected.cross_tension and not actual.cross_tension:
        mismatches.append("cross_tension_missing")
        score -= 0.15

    score = max(0.0, min(1.0, score))
    acceptable = score >= 0.7 and "uncertainty_erased" not in ",".join(mismatches) and not any(
        m.startswith("debate_state:") for m in mismatches
    )
    return JudgmentCompareResult(
        acceptable=acceptable,
        score=score,
        mismatches=mismatches,
        actual=actual,
        expected=expected,
    )


def frames_structurally_equal(a: JudgmentFrame, b: JudgmentFrame) -> bool:
    """Drift check: same core signature ignoring secondary wording fields."""
    return judgment_signature(a) == judgment_signature(b)
