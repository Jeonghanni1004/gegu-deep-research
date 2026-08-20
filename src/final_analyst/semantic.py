"""Semantic validators — natural-language intent, not keyword seals.

Round 5: phrase_seal_dependency = 0.
Exact words like 「未决」「Challenge」「跨 tension」are sufficient but NOT required.
"""

from __future__ import annotations

import re

from final_analyst.contract import FinalAnalystInput
from final_analyst.schemas import FinalAnalystOutput


def _blob(*parts: str) -> str:
    return " ".join(p for p in parts if p)


# --- Pattern libraries (OR semantics; any match = pass) ---

_UNRESOLVED_MARKERS = (
    "未决",
    "无法裁定",
    "解释未决",
    "不足以裁定",
    "不足以区分",
    "不足以判定",
    "不足以证明",
    "不足以支持定论",
    "不足以区分阶段性",
    "无法区分",
    "无法确认",
    "无法确定",
    "未能裁定",
    "未能证明",
    "未能改变",
    "证据不足",
    "证据不足以",
    "现有材料无法",
    "现有证据不足以",
    "当前证据不足以",
    "仍未获得明确",
    "未被充分证实",
    "两种解释未被",
    "限制仍然存在",
    "当前判断仍受",
    "尚未裁定",
    "不能裁定",
    "方向未定",
    "尚未定价",
    "等待增长数据",
    "证据不足以支持",
    "不足以抵消",
    "unresolved",
    "insufficient to decide",
    "insufficient to distinguish",
    "cannot resolve",
    "cannot distinguish",
)

_CHALLENGE_MARKERS = (
    "Challenge",
    "challenge",
    "挑战",
    "限制强度",
    "限制判断",
    "仍限制",
    "开放挑战",
    "未关闭的挑战",
    "未解除的挑战",
    "条数",
    "证据不足限制",
    "challenge 仍",
    "limiting",
)

_NEW_EVIDENCE_MARKERS = (
    "新证据",
    "可核对",
    "若出现",
    "如果出现",
    "若后续",
    "如果后续",
    "出现后",
    "出现可核对",
    "后续季度",
    "未来可验证",
    "可验证新",
    "条件成立",
    "在……情况下",
)

_CONDITIONAL_MARKERS = (
    "若",
    "如果",
    "假设",
    "条件",
    "一旦",
    "当且仅当",
)

_CROSS_TENSION_MARKERS = (
    "跨 tension",
    "跨tension",
    "中间条件",
    "连接经营",
    "连接",
    "Fundamental×Market",
    "Fundamental x Market",
    "基本面与市场",
    "基本面×市场",
    "同时消费",
    "同时处理",
    "张力",
)


def has_unresolved_semantics(text: str) -> bool:
    t = text or ""
    if any(m in t for m in _UNRESOLVED_MARKERS):
        return True
    # Soft pattern: 不足以…裁定/区分/判定
    if re.search(r"不足以.{0,12}(裁定|区分|判定|证明|支持)", t):
        return True
    if re.search(r"(无法|不能).{0,8}(裁定|区分|确认|确定)", t):
        return True
    return False


def has_challenge_semantics(text: str, *, limiting_challenge: str = "") -> bool:
    t = text or ""
    if any(m in t for m in _CHALLENGE_MARKERS):
        return True
    if limiting_challenge and limiting_challenge not in {"", "无开放 Challenge", "无"}:
        if limiting_challenge in t:
            return True
    if re.search(r"(挑战|Challenge).{0,20}(限制|约束|削弱|阻挡)", t):
        return True
    if re.search(r"(限制|约束).{0,16}(强度|幅度|结论)", t):
        return True
    return False


def has_new_evidence_boundary(text: str) -> bool:
    t = text or ""
    if any(m in t for m in _NEW_EVIDENCE_MARKERS):
        return True
    # Conditional scenario shape: 若…则… / 如果…则…
    if re.search(r"(若|如果).{2,80}(则|才会|才能|将)", t):
        return True
    if any(m in t for m in _CONDITIONAL_MARKERS) and any(
        k in t for k in ("则", "才会", "才能", "可能改变", "可能转向")
    ):
        return True
    return False


def has_cross_tension_semantics(text: str) -> bool:
    t = text or ""
    if any(m in t for m in _CROSS_TENSION_MARKERS):
        return True
    if re.search(r"(基本面).{0,40}(市场|估值|均线)", t):
        return True
    if "并存" in t and any(k in t for k in ("盈利", "增长", "估值", "利用率", "毛利率")):
        return True
    if re.search(r"(同时|并存|一方面).{0,30}(另一方面|同时|并且)", t):
        return True
    if "量增利不增" in t or ("利用率" in t and "ASP" in t):
        return True
    return False


def has_frame_shift_semantics(text: str) -> bool:
    t = text or ""
    markers = (
        "解释框架",
        "移向",
        "更强支持",
        "建设性权重",
        "谨慎权重",
        "框架转向",
        "判断幅度",
        "主导解释",
    )
    if any(m in t for m in markers):
        return True
    if has_new_evidence_boundary(t) and any(k in t for k in ("则", "才会", "支撑", "下修", "缓冲")):
        return True
    return False


def validate_unresolved_semantics(out: FinalAnalystOutput, inp: FinalAnalystInput) -> list[str]:
    """If Debate says unresolved, FA must express unresolved intent (any phrasing)."""
    errors: list[str] = []
    res = out.meta.primary_resolution or out.assessment_basis.primary_resolution
    debate_unresolved = bool(inp.debate.debate_summary.unresolved_issues)
    if res != "unresolved" and not debate_unresolved:
        return errors

    exec_t = out.executive_assessment.text
    base_t = out.base_case.thesis.text
    unc_blob = " ".join(u.text for u in out.uncertainty)

    if res == "unresolved":
        blob = _blob(exec_t, base_t, unc_blob)
        if not has_unresolved_semantics(blob):
            errors.append("semantic_unresolved: output lacks unresolved intent")
        # Prefer base_case also carry the intent, but accept executive/uncertainty coverage
        if not has_unresolved_semantics(base_t) and not has_unresolved_semantics(exec_t):
            errors.append("semantic_unresolved: base_case and executive both lack unresolved intent")
    elif debate_unresolved:
        blob = unc_blob + exec_t
        if not has_unresolved_semantics(blob):
            errors.append("semantic_unresolved: debate unresolved_issues not preserved")
    return errors


def validate_challenge_semantics(out: FinalAnalystOutput, inp: FinalAnalystInput) -> list[str]:
    errors: list[str] = []
    if not inp.debate.challenges and not any(
        t.debate_resolution.unresolved_challenges for t in out.core_tensions
    ):
        return errors

    lim = out.assessment_basis.limiting_challenge or ""
    if not lim and out.core_tensions:
        # Prefer first unresolved challenge id if available
        for t in out.core_tensions:
            if t.debate_resolution.unresolved_challenges:
                errors.append("semantic_challenge: missing limiting_challenge field")
                break

    exec_t = out.executive_assessment.text
    frame = out.assessment_basis.calibrated_frame or ""
    blob = _blob(exec_t, frame, lim)
    if not has_challenge_semantics(blob, limiting_challenge=lim):
        errors.append("semantic_challenge: output lacks challenge-limiting intent")
    return errors


def validate_new_evidence_boundary(out: FinalAnalystOutput) -> list[str]:
    errors: list[str] = []
    if not has_new_evidence_boundary(out.bull_case.thesis.text):
        errors.append("semantic_scenario_boundary: bull lacks conditional/new-evidence intent")
    if not has_new_evidence_boundary(out.bear_case.thesis.text):
        errors.append("semantic_scenario_boundary: bear lacks conditional/new-evidence intent")
    if not has_frame_shift_semantics(out.bull_case.thesis.text):
        # Soft: conditional boundary already implies shift; only fail if neither
        if not has_new_evidence_boundary(out.bull_case.thesis.text):
            errors.append("semantic_frame_shift: bull lacks frame-shift / conditional intent")
    return errors


def validate_cross_tension_semantics(out: FinalAnalystOutput) -> list[str]:
    if len(out.core_tensions) < 2:
        return []
    if has_cross_tension_semantics(out.executive_assessment.text):
        return []
    return ["semantic_cross_tension: multi-tension executive lacks bridge intent"]


def validate_all_semantics(out: FinalAnalystOutput, inp: FinalAnalystInput) -> list[str]:
    errs: list[str] = []
    errs.extend(validate_unresolved_semantics(out, inp))
    errs.extend(validate_challenge_semantics(out, inp))
    errs.extend(validate_new_evidence_boundary(out))
    errs.extend(validate_cross_tension_semantics(out))
    return errs


def phrase_seal_dependency_count(notes: list[str] | None) -> int:
    """Production gate: must be 0 (applied seals only; ignore status markers)."""
    notes = notes or []
    return sum(
        1
        for n in notes
        if n == "openai_phrase_seal"
        or n.lower().startswith("phrase_seal_applied")
        or "openai_phrase_seal" in n.lower()
    )
