"""Validators for Final Analyst v2 (Debate-driven judgment)."""

from __future__ import annotations

import re

from evidence.pack import EvidencePack
from evidence.schema import Evidence
from research.citation import extract_fact_tokens, tokens_supported

from final_analyst.calibration import (
    calibrate_assessment,
    detect_overclaim,
    detect_unsupported_inference,
    judgment_amplitude_rank,
)
from final_analyst.contract import FinalAnalystInput, all_canonical
from final_analyst.schemas import AnalyzedStatement, FinalAnalystOutput
from final_analyst.semantic import (
    has_frame_shift_semantics,
    phrase_seal_dependency_count,
    validate_all_semantics,
)


def _iter_statements(out: FinalAnalystOutput) -> list[AnalyzedStatement]:
    rows: list[AnalyzedStatement] = [
        out.executive_assessment,
        out.core_thesis,
        *out.key_drivers,
        out.base_case.thesis,
        out.bull_case.thesis,
        out.bear_case.thesis,
        *out.uncertainty,
        *out.research_gaps,
    ]
    for t in out.core_tensions:
        rows.extend(
            [
                t.fact_anchor,
                t.bull_interpretation,
                t.bear_interpretation,
                t.current_assessment,
            ]
        )
    for s in (out.base_case, out.bull_case, out.bear_case):
        rows.extend(s.required_assumptions)
    return rows


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def validate_final_analyst(
    out: FinalAnalystOutput,
    inp: FinalAnalystInput,
    *,
    pack: EvidencePack | None = None,
) -> list[str]:
    errors: list[str] = []
    by_id: dict[str, Evidence] = {}
    if pack is not None:
        by_id = {e.evidence_id: e for e in pack.evidence}

    canon_ids = {c.finding_id for c in all_canonical(inp)}
    canon_claims = [c.claim.strip() for c in all_canonical(inp)]
    bull_claims = [c.claim.strip() for c in inp.debate.bull.claims]
    bear_claims = [c.claim.strip() for c in inp.debate.bear.claims]

    if not inp.fundamental.canonical_findings and not inp.market.canonical_findings:
        errors.append("contract_consumption: no canonical findings")

    if out.analyst_mode == "grounded" and not out.meta.grounded_is_not_autonomous:
        errors.append("mode_boundary: grounded_is_not_autonomous required")
    if not out.meta.no_trade_advice:
        errors.append("mode_boundary: no_trade_advice required")

    authored = set(out.canonical_finding_ids) - canon_ids
    if authored:
        errors.append(f"fa_finding_namespace: {sorted(authored)[:5]}")

    for i, s in enumerate(_iter_statements(out)):
        if s.kind == "FACT" and not s.evidence_ids:
            errors.append(f"evidence_traceability: FACT[{i}] missing evidence_ids")
        if s.kind == "INFERENCE" and not s.canonical_finding_ids:
            errors.append(f"canonical_traceability: INFERENCE[{i}] missing canonical ids")
        if s.kind == "FACT" and any(k in s.text for k in ("主导解释框架", "解释优先级", "resolution=")):
            errors.append(f"fact_inference_separation: FACT[{i}] inference language")
        if s.kind == "ASSUMPTION" and any(k in s.text for k in ("已经恢复", "已经恶化", "已经确认")):
            errors.append(f"scenario_assumption_boundary: ASSUMPTION[{i}] as fact")
        if "Autonomous" in s.text or "自主研究" in s.text:
            errors.append("mode_boundary: autonomous wording")

        if pack is not None and s.evidence_ids:
            tokens = extract_fact_tokens(s.text)
            cited = [by_id[e] for e in s.evidence_ids if e in by_id]
            if tokens and cited:
                filtered = [t for t in tokens if not re.fullmatch(r"\d{1,2}", t) and t != out.research_as_of_date]
                _, missing = tokens_supported(filtered, cited)
                if missing:
                    errors.append(f"no_unsupported_inference: [{i}] {missing[:3]}")

        nt = _normalize(s.text)
        for cc in canon_claims:
            nc = _normalize(cc)
            if len(nc) > 40 and (nc in nt or nt == nc):
                errors.append(f"no_research_duplication: statement[{i}] clones canonical")
                break

    # interpretation must not be claim copy
    for t in out.core_tensions:
        for label, interp in [("bull", t.bull_interpretation), ("bear", t.bear_interpretation)]:
            for claim in bull_claims + bear_claims:
                if claim and _normalize(interp.text) == _normalize(claim):
                    errors.append(f"interpretation_not_claim_copy: {t.tension_id} {label}")
                if claim and len(claim) > 20 and _normalize(claim) in _normalize(interp.text) and "resolution=" not in interp.text:
                    # allow partial reference only if FA meaning markers present
                    if not any(k in interp.text for k in ("若", "条件", "resolution", "权重", "不能单独")):
                        errors.append(f"interpretation_not_claim_copy: weak increment {t.tension_id}")

    # debate resolution required
    if not out.core_tensions:
        errors.append("debate_consumption: no core_tensions")
    for t in out.core_tensions:
        if t.debate_resolution is None:
            errors.append("debate_consumption: missing debate_resolution")
        else:
            if not t.debate_resolution.resolution_reason:
                errors.append("debate_consumption: empty resolution_reason")
            if t.debate_resolution.resolution not in {
                "bull_supported",
                "bear_supported",
                "partially_resolved",
                "unresolved",
            }:
                errors.append("debate_consumption: bad resolution kind")

    if inp.debate.challenges and not any(t.challenges for t in out.core_tensions):
        errors.append("debate_consumption: challenges ignored")
    if inp.debate.rebuttals and not any(t.rebuttals for t in out.core_tensions):
        errors.append("debate_consumption: rebuttals ignored")

    # assessment strength
    if out.meta.assessment_strength not in {"strong", "moderate", "tentative", "unresolved"}:
        errors.append("assessment_strength: missing/invalid on meta")
    if out.executive_assessment.assessment_strength is None:
        errors.append("assessment_strength: missing on executive")

    # base case selection
    if not out.assessment_basis.reason_base_case_selected:
        errors.append("base_case_selection: missing reason")
    if out.assessment_basis.primary_resolution is None:
        errors.append("base_case_selection: missing primary_resolution")
    if "平均" in out.base_case.thesis.text or "中性综合" in out.base_case.thesis.text:
        errors.append("bull_bear_not_mechanical_balance: base averages sides")
    # Round-5: unresolved / challenge / scenario / cross-tension → semantic.py

    # scenarios
    if not out.bull_case.explanation_shift_variable or not out.bear_case.explanation_shift_variable:
        errors.append("scenario_variable_link: missing explanation_shift_variable")
    if not has_frame_shift_semantics(out.bull_case.thesis.text):
        errors.append("scenario_explanation_shift: bull lacks frame-shift intent")
    if not out.bull_case.required_assumptions or out.bull_case.required_assumptions[0].kind != "ASSUMPTION":
        errors.append("scenario_assumption_boundary: bull")
    if not out.bear_case.required_assumptions:
        errors.append("scenario_assumption_boundary: bear")

    # what would change specificity
    for w in out.what_would_change_my_view:
        if not w.related_gap_or_boundary.strip():
            errors.append("view_changer_specificity: empty gap link")
        if w.trigger_evidence_description.strip() in {"更多数据", "需要更多信息"}:
            errors.append("view_changer_specificity: too vague")

    if not out.what_would_change_my_view:
        errors.append("what_would_change: empty")

    # uncertainty preservation — gaps must not be "completed"
    for g in out.research_gaps:
        if any(m in g.text for m in ("稳定", "风险较低", "已确认良好")):
            errors.append("uncertainty_preservation: gap completed")

    # analytical increment v2 — broad debate-driven markers (not seal-only keywords)
    incr = (
        "resolution",
        "Debate",
        "strength",
        "若",
        "条件",
        "校准",
        "解释",
        "优先",
        "挑战",
        "Challenge",
        "不足以",
        "未决",
        "跨",
        "中间条件",
        "不一致",
    )
    if not any(k in out.executive_assessment.text for k in incr):
        errors.append("analytical_increment_v2: executive lacks debate-driven increment")

    errors.extend(validate_all_semantics(out, inp))

    # inference boundary / unsupported market claims
    for i, s in enumerate(_iter_statements(out)):
        for err in detect_unsupported_inference(s.text):
            errors.append(f"{err} @stmt[{i}]")
        if s.inference_status == "UNSUPPORTED":
            errors.append(f"inference_boundary: UNSUPPORTED stmt[{i}]")

    # judgment calibration / overclaim
    support = out.meta.debate_support_strength
    res = out.meta.primary_resolution or "unresolved"
    pressure = out.meta.evidence_pressure or out.assessment_basis.evidence_pressure or "elevated"
    for err in detect_overclaim(out.executive_assessment.text, support, resolution=res):  # type: ignore[arg-type]
        errors.append(err)
    for err in detect_overclaim(out.base_case.thesis.text, support, resolution=res):  # type: ignore[arg-type]
        errors.append(err)
    if out.assessment_basis.calibrated_frame and out.assessment_basis.evidence_pressure is None:
        errors.append("judgment_calibration: missing evidence_pressure")

    if res and pressure:
        from final_analyst.calibration import assessment_rank

        boundaries = list(inp.fundamental.uncertainty_boundaries or [])[:4]
        boundaries += list(inp.market.uncertainty_boundaries or [])[:2]
        expected = calibrate_assessment(
            res,  # type: ignore[arg-type]
            support,
            pressure,  # type: ignore[arg-type]
            boundaries,
        )
        if out.meta.assessment_strength:
            got = assessment_rank(out.meta.assessment_strength)
            exp = assessment_rank(expected.assessment_strength)
            if abs(got - exp) > 1:
                errors.append(
                    f"calibration_matrix_drift: got={out.meta.assessment_strength} "
                    f"expected≈{expected.assessment_strength}"
                )

    # limiting_challenge field when challenges exist
    if not out.assessment_basis.limiting_challenge and res != "partially_resolved":
        if out.assessment_basis.limiting_challenge == "" and out.core_tensions:
            if inp.debate.challenges or any(
                t.debate_resolution.unresolved_challenges for t in out.core_tensions
            ):
                errors.append("debate_resolution_semantics: missing limiting_challenge")

    # numeric preservation
    if any(c.numbers_preserved for c in all_canonical(inp)):
        if not out.executive_assessment.numbers_used and not any(ch.isdigit() for ch in out.executive_assessment.text):
            errors.append("numeric_preservation: executive missing numbers")

    # duplicate scenario detection
    if _normalize(out.bull_case.thesis.text) == _normalize(out.bear_case.thesis.text):
        errors.append("duplicate_scenario_detection: bull==bear")
    if _normalize(out.base_case.thesis.text) == _normalize(out.bull_case.thesis.text):
        errors.append("duplicate_scenario_detection: base==bull")

    # Production hard gates (Round 5)
    if phrase_seal_dependency_count(out.meta.notes) > 0 and out.analyst_mode == "openai":
        errors.append("phrase_seal_dependency: seal must not be required for pass")
    if any("information_loss=true" in n for n in (out.meta.notes or [])):
        errors.append("number_scrub_information_loss: scrubbed output not production-quality")

    return errors


def judgment_signature(out: FinalAnalystOutput) -> str:
    """Compact signature for flip / calibration / non-mechanical tests."""
    res = out.meta.primary_resolution or ""
    strength = out.meta.assessment_strength or ""
    support = out.meta.debate_support_strength or ""
    pressure = out.meta.evidence_pressure or ""
    base = out.base_case.thesis.text[:100]
    return f"{res}|{strength}|{support}|{pressure}|{base}"


def calibration_rank(out: FinalAnalystOutput) -> int:
    return judgment_amplitude_rank(
        out.meta.debate_support_strength,
        resolution=out.meta.primary_resolution or "unresolved",  # type: ignore[arg-type]
    )