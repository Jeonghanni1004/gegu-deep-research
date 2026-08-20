"""OpenAI Live prompt — analytical freedom under FACT freedom = 0.

Compact prompts to avoid truncated JSON from large schema dumps.
"""

from __future__ import annotations

import json
from typing import Any

from final_analyst.contract import FinalAnalystInput, all_canonical


SYSTEM_PROMPT = """你是 A-share Final Analyst（非 Autonomous Research）。

## 边界（硬约束）
1. 只能使用 INPUT 中的 Research + Debate。
2. FACT freedom = 0：禁止契约外事实/新闻/未出现数字。
3. ANALYTICAL freedom > 0：允许组织、解释、连接、排序。
4. 禁止 BUY/SELL/HOLD、目标价、概率、投资评级、Autonomous Research。
5. 禁止创造新的 canonical_finding_id / evidence_id（只能用 ALLOWED_* 列表）。
6. Debate resolution 不是事实；strong≠certainty；bull_supported≠已经改善。

## 必须回答
1. 最重要矛盾是什么？为何优先？
2. Debate 改变了什么 / 为何没改变？
3. 哪些解释获支持？哪个 Challenge 仍限制强度？
4. Fundamental×Market 是否一致？不一致意味着什么？
5. 什么可验证新证据会改变判断？

## Analytical Increment（executive 至少体现 2 类）
PRIORITIZATION / IMPLICATION / CROSS-TENSION / DEBATE RESOLUTION /
DECISION BOUNDARY / CONTRADICTION INTERPRETATION
禁止：同义改写 Research、消灭 uncertainty。

## 输出规则
- 只输出一个 JSON 对象（不要 markdown）。
- analyst_mode 必须是 "openai"。
- meta.no_trade_advice=true；grounded_is_not_autonomous=true。
- 文本尽量紧凑：executive≤400字；各 scenario thesis≤120字；core_tensions≤2；key_drivers≤2；what_would_change≤2。
- inference_status ∈ SUPPORTED|DERIVED|CONDITIONAL。
- FACT 需 evidence_ids；INFERENCE 需 canonical_finding_ids。
- direction 只能是 more_constructive / more_cautious / unresolved_to_resolved 三者之一（不要组合写法）。
- 正文数字必须来自 INPUT canonical numbers_preserved / 已引用 evidence；禁止自造小数位。

## 语义要求（不是关键词 seal）
- unresolved：用自然语言表达「证据不足以裁定 / 两种解释未被充分证实 / 限制仍在」即可（不必出现「未决」二字）。
- Challenge：表达挑战对判断强度的限制即可（可用「挑战」「证据不足限制」等，不必固定英文 Challenge）。
- 多 tension：表达跨主题连接或中间条件即可。
- Bull/Bear scenario：必须是条件句（若/如果…则…），依赖未来可验证证据，不是已发生事实。
- 禁止为过校验而机械插入固定关键词。

## 数字与引用
- 正文数字必须来自 INPUT.ALLOWED_NUMBERS（或 numbers_preserved）；若引用数字，必须挂上 ALLOWED evidence_ids / canonical_finding_ids。
- 禁止编造小数、比率、区间位置（如自造 0.5016）；宁可少写数字也不要写无法 grounding 的数字。
- FIXED_DEBATE_CONTRACT.primary_resolution 是固定输入：禁止改写为其他 resolution。
"""


OUTPUT_SKELETON = {
    "stock_code": "STRING",
    "research_as_of_date": "YYYY-MM-DD",
    "analyst_mode": "openai",
    "executive_assessment": {
        "kind": "INFERENCE|UNCERTAINTY|FACT",
        "text": "synthesis...",
        "canonical_finding_ids": ["..."],
        "evidence_ids": ["..."],
        "debate_refs": [],
        "numbers_used": [],
        "assessment_strength": "strong|moderate|tentative|unresolved",
        "inference_status": "DERIVED|CONDITIONAL|SUPPORTED",
    },
    "core_thesis": {"kind": "INFERENCE", "text": "...", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "assessment_strength": "tentative", "inference_status": "DERIVED"},
    "key_drivers": [
        {"kind": "INFERENCE", "text": "...", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "inference_status": "DERIVED"}
    ],
    "core_tensions": [
        {
            "tension_id": "TENSION_...",
            "research_question": "...",
            "fact_anchor": {"kind": "FACT", "text": "...", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "numbers_used": []},
            "bull_reference": "BULL_01",
            "bear_reference": "BEAR_01",
            "bull_interpretation": {"kind": "INFERENCE", "text": "若...则...", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "inference_status": "CONDITIONAL"},
            "bear_interpretation": {"kind": "INFERENCE", "text": "若...则...", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "inference_status": "CONDITIONAL"},
            "challenges": [{"challenge_id": "CH_...", "claim_id": "BULL_01", "challenge_type": "...", "summary": "..."}],
            "rebuttals": [{"rebuttal_id": "RB_...", "challenge_id": "CH_...", "response_type": "...", "summary": "..."}],
            "debate_resolution": {
                "tension_id": "TENSION_...",
                "bull_position": "...",
                "bear_position": "...",
                "bull_reference_ids": ["BULL_01"],
                "bear_reference_ids": ["BEAR_01"],
                "decisive_evidence_ids": ["..."],
                "unresolved_challenges": [],
                "accepted_rebuttals": [],
                "rejected_rebuttals": [],
                "partially_accepted_rebuttals": [],
                "resolution": "unresolved|bull_supported|bear_supported|partially_resolved",
                "resolution_reason": "...",
                "assessment_strength": "tentative",
                "support_strength": None,
            },
            "current_assessment": {"kind": "INFERENCE|UNCERTAINTY", "text": "...", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "inference_status": "DERIVED"},
            "conditions_to_change": ["..."],
        }
    ],
    "assessment_basis": {
        "supported_facts": ["..."],
        "interpretation_advantage": "...",
        "unresolved": ["..."],
        "reason_base_case_selected": "...",
        "primary_resolution": "unresolved",
        "debate_support_strength": None,
        "evidence_pressure": "mild|elevated|severe",
        "calibrated_frame": "...",
        "active_challenges": [],
        "accepted_rebuttals": [],
        "limiting_challenge": "...",
    },
    "base_case": {
        "label": "base",
        "thesis": {"kind": "INFERENCE|UNCERTAINTY", "text": "...", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "inference_status": "DERIVED"},
        "supporting_canonical_ids": ["..."],
        "required_assumptions": [],
        "inconsistent_with": ["..."],
        "explanation_shift_variable": "...",
    },
    "bull_case": {
        "label": "bull",
        "thesis": {"kind": "INFERENCE", "text": "若出现可核对新证据...则...", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "inference_status": "CONDITIONAL"},
        "supporting_canonical_ids": ["..."],
        "required_assumptions": [
            {"kind": "ASSUMPTION", "text": "假设...", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "inference_status": "CONDITIONAL"}
        ],
        "inconsistent_with": ["..."],
        "explanation_shift_variable": "...",
    },
    "bear_case": {
        "label": "bear",
        "thesis": {"kind": "INFERENCE", "text": "若出现可核对新证据...则...", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "inference_status": "CONDITIONAL"},
        "supporting_canonical_ids": ["..."],
        "required_assumptions": [
            {"kind": "ASSUMPTION", "text": "假设...", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "inference_status": "CONDITIONAL"}
        ],
        "inconsistent_with": ["..."],
        "explanation_shift_variable": "...",
    },
    "what_would_change_my_view": [
        {
            "trigger_evidence_description": "可核对指标+方向+时间尺度",
            "would_affect": "primary_resolution / base_case",
            "direction": "unresolved_to_resolved",
            "related_gap_or_boundary": "...",
            "canonical_finding_ids": ["..."],
        }
    ],
    "uncertainty": [
        {"kind": "UNCERTAINTY", "text": "...", "canonical_finding_ids": ["..."], "evidence_ids": []}
    ],
    "research_gaps": [
        {"kind": "UNCERTAINTY", "text": "...", "canonical_finding_ids": [], "evidence_ids": []}
    ],
    "evidence_trace": [
        {"conclusion_ref": "executive_assessment", "canonical_finding_ids": ["..."], "evidence_ids": ["..."], "debate_refs": []}
    ],
    "canonical_finding_ids": ["..."],
    "evidence_ids": ["..."],
    "meta": {
        "no_trade_advice": True,
        "grounded_is_not_autonomous": True,
        "selected_tension_ids": ["..."],
        "primary_resolution": "unresolved",
        "assessment_strength": "tentative",
        "debate_support_strength": None,
        "evidence_pressure": "elevated",
        "notes": ["openai_live"],
    },
}


def _canon_brief(c) -> dict[str, Any]:
    return {
        "finding_id": c.finding_id,
        "finding_kind": c.finding_kind,
        "research_question": (c.research_question or "")[:160],
        "claim": (c.claim or "")[:320],
        "numbers_preserved": list(c.numbers_preserved or [])[:8],
        "evidence_ids": list(c.evidence_ids)[:8],
        "status": c.status,
    }


def _gap_brief(g) -> dict[str, Any]:
    return {
        "claim": (g.claim or "")[:200],
        "status": getattr(g, "status", None),
        "evidence_ids": list(getattr(g, "evidence_ids", []) or [])[:4],
    }


def compact_input_for_llm(inp: FinalAnalystInput) -> dict[str, Any]:
    """Minimal analytical payload — no full pydantic schema, no compat dump."""
    from final_analyst.contract_pin import contract_resolution

    fund = inp.fundamental
    mkt = inp.market
    debate = inp.debate

    allowed_canon = [c.finding_id for c in all_canonical(inp)]
    allowed_eids: list[str] = []
    allowed_numbers: list[str] = []
    for c in all_canonical(inp):
        allowed_eids.extend(c.evidence_ids)
        allowed_numbers.extend(list(c.numbers_preserved or []))
    for cl in list(debate.bull.claims) + list(debate.bear.claims):
        allowed_eids.extend(cl.evidence_ids)
    for ch in debate.challenges:
        allowed_eids.extend(ch.evidence_ids)
    for rb in debate.rebuttals:
        allowed_eids.extend(rb.evidence_ids)
    allowed_eids = list(dict.fromkeys(allowed_eids))
    allowed_numbers = list(dict.fromkeys(str(n) for n in allowed_numbers if n))[:48]
    res, support, pressure = contract_resolution(inp)

    return {
        "stock_code": inp.stock_code,
        "research_as_of_date": inp.research_as_of_date,
        "mode": "openai",
        "ALLOWED_CANONICAL_IDS": allowed_canon,
        "ALLOWED_EVIDENCE_IDS": allowed_eids[:40],
        "ALLOWED_NUMBERS": allowed_numbers,
        "FIXED_DEBATE_CONTRACT": {
            "primary_resolution": res,
            "support_strength": support,
            "evidence_pressure": pressure,
            "note": "禁止改写 primary_resolution；assessment 由 calibration 决定",
        },
        "fundamental": {
            "canonical_findings": [_canon_brief(c) for c in fund.canonical_findings],
            "research_gaps": [_gap_brief(g) for g in fund.research_gaps[:6]],
            "uncertainty_boundaries": list(fund.uncertainty_boundaries or [])[:6],
        },
        "market": {
            "canonical_findings": [_canon_brief(c) for c in mkt.canonical_findings],
            "research_gaps": [_gap_brief(g) for g in mkt.research_gaps[:4]],
            "uncertainty_boundaries": list(mkt.uncertainty_boundaries or [])[:4],
        },
        "debate": {
            "metadata": debate.metadata or {},
            "bull_claims": [
                {
                    "claim_id": c.claim_id,
                    "claim": c.claim[:220],
                    "evidence_ids": list(c.evidence_ids)[:4],
                    "canonical_finding_ids": list(c.canonical_finding_ids or [])[:4],
                }
                for c in debate.bull.claims
            ],
            "bear_claims": [
                {
                    "claim_id": c.claim_id,
                    "claim": c.claim[:220],
                    "evidence_ids": list(c.evidence_ids)[:4],
                    "canonical_finding_ids": list(c.canonical_finding_ids or [])[:4],
                }
                for c in debate.bear.claims
            ],
            "challenges": [
                {
                    "challenge_id": ch.challenge_id,
                    "challenger": ch.challenger,
                    "target_claim_id": ch.target_claim_id,
                    "challenge_type": ch.challenge_type,
                    "argument": ch.argument[:200],
                    "evidence_ids": list(ch.evidence_ids)[:3],
                }
                for ch in debate.challenges
            ],
            "rebuttals": [
                {
                    "rebuttal_id": rb.rebuttal_id,
                    "author": rb.author,
                    "target_challenge_id": rb.target_challenge_id,
                    "response_type": rb.response_type,
                    "argument": rb.argument[:200],
                    "evidence_ids": list(rb.evidence_ids)[:3],
                }
                for rb in debate.rebuttals
            ],
            "summary": {
                "shared_facts": list(debate.debate_summary.shared_facts or [])[:6],
                "core_disagreements": list(debate.debate_summary.core_disagreements or [])[:4],
                "unresolved_issues": list(debate.debate_summary.unresolved_issues or [])[:6],
            },
        },
    }


def build_user_prompt(inp: FinalAnalystInput) -> str:
    payload = compact_input_for_llm(inp)
    return (
        "INPUT（压缩版 FinalAnalystInput）：\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "OUTPUT 必须是符合下列骨架的单一 JSON（字段名必须齐全；用真实分析替换占位符）：\n"
        f"{json.dumps(OUTPUT_SKELETON, ensure_ascii=False)}\n\n"
        "约束提醒：只使用 ALLOWED_* id 与 ALLOWED_NUMBERS；executive 先写 synthesis；"
        "FIXED_DEBATE_CONTRACT.primary_resolution 必须原样写入 meta/assessment_basis/core_tensions；"
        "Bull/Bear 必须条件化；不得消灭 unresolved 语义；文本保持紧凑以免截断；"
        "unresolved 时 support_strength 用 JSON null，禁止字符串 'null'；"
        "用自然语言表达未裁定/挑战限制/跨主题连接，不要为过校验堆关键词；"
        "数字必须来自 ALLOWED_NUMBERS 并能 evidence grounding，并挂上对应 evidence_ids；"
        "禁止自造比率/小数位。"
    )
