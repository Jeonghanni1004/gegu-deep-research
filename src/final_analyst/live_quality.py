"""Live quality checks — structural behavior, not Grounded keyword templates."""

from __future__ import annotations

import re

from final_analyst.calibration import detect_unsupported_inference
from final_analyst.contract import FinalAnalystInput, all_canonical
from final_analyst.schemas import FinalAnalystOutput
from final_analyst.validators import validate_final_analyst


_OVERCERTAIN = (
    "已经证明",
    "已经确认",
    "增长已经恢复",
    "基本面已经改善",
    "增长逻辑已经失效",
    "市场已经重新定价",
    "需求已经恢复",
)


def live_hard_errors(out: FinalAnalystOutput, inp: FinalAnalystInput, *, pack=None) -> list[str]:
    """Fail-closed boundary errors for live OpenAI outputs."""
    errors = list(validate_final_analyst(out, inp, pack=pack))
    canon = {c.finding_id for c in all_canonical(inp)}
    known_eids: set[str] = set()
    for c in all_canonical(inp):
        known_eids.update(c.evidence_ids)
    for cl in list(inp.debate.bull.claims) + list(inp.debate.bear.claims):
        known_eids.update(cl.evidence_ids)
    for ch in inp.debate.challenges:
        known_eids.update(ch.evidence_ids)
    for rb in inp.debate.rebuttals:
        known_eids.update(rb.evidence_ids)

    authored = set(out.canonical_finding_ids) - canon
    if authored:
        errors.append(f"fabricated_canonical: {sorted(authored)[:5]}")

    # evidence ids used in statements
    from final_analyst.validators import _iter_statements

    for i, s in enumerate(_iter_statements(out)):
        bad = [e for e in s.evidence_ids if e not in known_eids and pack is None]
        # If pack provided, pack membership checked elsewhere; here check inventing ids not in input surface
        bad_input = [e for e in s.evidence_ids if e not in known_eids]
        if bad_input and pack is None:
            errors.append(f"fabricated_evidence_hint: stmt[{i}] {bad_input[:3]}")
        for err in detect_unsupported_inference(s.text):
            errors.append(err)
        for phrase in _OVERCERTAIN:
            if phrase in s.text:
                # Negated discussions are OK
                if f"不得写成{phrase}" in s.text or f"不能写成{phrase}" in s.text or f"禁止{phrase}" in s.text:
                    continue
                if "不得" in s.text and phrase in s.text and s.text.find("不得") < s.text.find(phrase):
                    # rough: prohibition before phrase in same sentence window
                    window = s.text[max(0, s.text.find(phrase) - 12) : s.text.find(phrase)]
                    if "不得" in window or "不能" in window or "禁止" in window:
                        continue
                errors.append(f"overcertain_language: {phrase}")

    blob = out.executive_assessment.text + out.base_case.thesis.text
    if inp.debate.debate_summary.unresolved_issues:
        from final_analyst.semantic import has_unresolved_semantics

        if out.meta.primary_resolution == "unresolved" or any(
            "未决" in u or "无法" in u or "不足" in u for u in (inp.debate.debate_summary.unresolved_issues or [])
        ):
            if out.meta.primary_resolution == "unresolved" and not has_unresolved_semantics(blob):
                errors.append("uncertainty_erased: unresolved not reflected")

    if out.meta.no_trade_advice is not True:
        errors.append("trade_advice_flag")

    return list(dict.fromkeys(errors))


def analytical_increment_signals(out: FinalAnalystOutput) -> dict[str, bool]:
    t = out.executive_assessment.text
    return {
        "prioritization": any(k in t for k in ("主判断", "优先", "判断轴", "最重要", "主导")),
        "implication": any(k in t for k in ("意味着", "因此", "从而", "含义", "门槛")),
        "cross_tension": any(k in t for k in ("跨", "连接", "中间条件", "同时", "估值"))
        and len(out.core_tensions) >= 1,
        "debate_resolution": any(k in t for k in ("Debate", "resolution", "Challenge", "Rebuttal", "对抗")),
        "decision_boundary": any(k in t for k in ("若", "如果", "新证据", "可核对", "出现后")),
        "contradiction": any(k in t for k in ("不一致", "冲突", "并不自动", "不能自动", "时间尺度")),
    }


def has_analytical_increment(out: FinalAnalystOutput) -> bool:
    sig = analytical_increment_signals(out)
    return sum(1 for v in sig.values() if v) >= 2


def scenario_boundary_ok(out: FinalAnalystOutput) -> bool:
    return (
        ("若" in out.bull_case.thesis.text or "如果" in out.bull_case.thesis.text or "新证据" in out.bull_case.thesis.text)
        and ("若" in out.bear_case.thesis.text or "如果" in out.bear_case.thesis.text or "新证据" in out.bear_case.thesis.text)
        and out.bull_case.thesis.text != out.bear_case.thesis.text
    )


def structural_invariants(grounded: FinalAnalystOutput, openai: FinalAnalystOutput) -> list[str]:
    errs = []
    if grounded.stock_code != openai.stock_code:
        errs.append("invariant: stock_code")
    if grounded.research_as_of_date != openai.research_as_of_date:
        errs.append("invariant: as_of")
    if not openai.meta.no_trade_advice:
        errs.append("invariant: no_trade_advice")
    # Canonical set should be subset of grounded's available ids (openai may select fewer)
    if set(openai.canonical_finding_ids) - set(grounded.canonical_finding_ids):
        # openai may include same tensions; if extras → error already in live_hard
        pass
    return errs


def extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?%?", text))


def external_number_risk(out: FinalAnalystOutput, inp: FinalAnalystInput) -> list[str]:
    """Numbers in executive that appear nowhere in input surface."""
    allowed: set[str] = set()
    for c in all_canonical(inp):
        allowed.update(extract_numbers(c.claim))
        allowed.update(c.numbers_preserved or [])
    for cl in list(inp.debate.bull.claims) + list(inp.debate.bear.claims):
        allowed.update(extract_numbers(cl.claim))
    allowed.add(inp.research_as_of_date.replace("-", ""))
    # Allow as_of fragments
    allowed.update(extract_numbers(inp.research_as_of_date))
    used = extract_numbers(out.executive_assessment.text)
    # Filter tiny integers that are noise (1, 2, 3)
    suspects = [n for n in used if n not in allowed and not re.fullmatch(r"\d{1,2}", n)]
    return suspects[:8]
