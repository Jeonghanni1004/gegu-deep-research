"""Deterministic Final Analyst — Debate resolution drives judgment."""

from __future__ import annotations

from research.citation import extract_fact_tokens
from research.schemas import CanonicalFinding

from final_analyst.calibration import (
    calibrate_assessment,
    calibrated_frame_phrase,
    classify_inference_status,
    evidence_pressure,
    judgment_amplitude_rank,
)
from final_analyst.contract import FinalAnalystInput, all_canonical
from final_analyst.resolution import (
    challenges_for,
    claims_for_tension,
    rebuttals_for,
    resolve_debate_for_tension,
)
from final_analyst.schemas import (
    AnalyzedStatement,
    AssessmentBasis,
    DebateResolution,
    FinalAnalystMeta,
    FinalAnalystOutput,
    ResolutionKind,
    Scenario,
    TensionDebateLink,
    TensionResolution,
    TraceLink,
    ViewChanger,
)

_PRIORITY = [
    "PROFIT_VS_GROWTH",
    "VALUATION_VS_GROWTH",
    "SHORT_VS_LONG",
    "CASH_QUALITY",
    "PRICE_MA",
    "VAL_PRICE",
    "NEWS_NARRATIVE",
]


def _nums(c: CanonicalFinding) -> list[str]:
    return list(c.numbers_preserved or extract_fact_tokens(c.claim or ""))


def _pick_tensions(inp: FinalAnalystInput, *, max_n: int = 3) -> list[CanonicalFinding]:
    all_c = all_canonical(inp)
    tensions = [c for c in all_c if c.finding_kind == "tension"]
    if not tensions:
        tensions = [c for c in all_c if c.finding_kind == "cross"]
    ranked: list[CanonicalFinding] = []
    for key in _PRIORITY:
        for c in tensions:
            if key in c.finding_id and c not in ranked:
                ranked.append(c)
    for c in tensions:
        if c not in ranked:
            ranked.append(c)
    return ranked[:max_n]


def _fact_anchor(c: CanonicalFinding) -> AnalyzedStatement:
    nums = _nums(c)
    bits = "、".join(nums[:6]) if nums else "（见 cited evidence）"
    return AnalyzedStatement(
        kind="FACT",
        text=f"支撑命题 {c.finding_id} 的关键事实数字：{bits}。",
        canonical_finding_ids=[c.finding_id],
        evidence_ids=list(c.evidence_ids),
        numbers_used=nums[:8],
    )


def _bull_interpretation(c: CanonicalFinding, dr: DebateResolution, nums: list[str]) -> AnalyzedStatement:
    """FA meaning — not a copy of Bull claim text."""
    n = "、".join(nums[:4]) if nums else "既有数字事实"
    if "PROFIT" in c.finding_id or "VALUATION" in c.finding_id:
        text = (
            f"若增长压力主要来自阶段性需求或渠道因素，则高盈利缓冲（{n}）仍可约束“盈利崩塌”叙事；"
            f"但该解释目前仅是条件假设。Debate resolution={dr.resolution}："
            f"{'不足以验证阶段性假设' if dr.resolution in {'unresolved', 'partially_resolved'} else 'Bull 侧解释边界相对更受支持'}。"
        )
    elif "SHORT" in c.finding_id:
        text = (
            "若短中期价格结构改善被解读为动能线索，它最多提供市场尺度旁证，"
            "不能单独证明财务增长争议已解决；该解读的可用性取决于 Debate 是否关闭证据不足挑战。"
        )
    else:
        text = (
            f"Bull 立场若成立，将提高对既有事实（{n}）的建设性解读权重；"
            f"但其成立依赖未被 Challenge 阻断的条件，当前 resolution={dr.resolution}。"
        )
    return AnalyzedStatement(
        kind="INFERENCE",
        text=text,
        canonical_finding_ids=[c.finding_id],
        evidence_ids=list(c.evidence_ids),
        debate_refs=list(dr.bull_reference_ids),
        numbers_used=nums[:4],
        assessment_strength=dr.assessment_strength,
    )


def _bear_interpretation(c: CanonicalFinding, dr: DebateResolution, nums: list[str]) -> AnalyzedStatement:
    n = "、".join(nums[:4]) if nums else "既有数字事实"
    if "PROFIT" in c.finding_id or "VALUATION" in c.finding_id:
        text = (
            f"若同比下滑反映更持久的需求/结构压力，则增长不确定性应主导解释框架，"
            f"估值对恢复的依赖上升（事实锚点含 {n}）；"
            f"但把单期同比直接升级为结构性恶化，仍受 Challenge 约束。"
            f"当前 resolution={dr.resolution}。"
        )
    elif "SHORT" in c.finding_id:
        text = (
            "若长期均线压力被赋予更高权重，则短中期多头排列不能外推为趋势已确认；"
            "该谨慎框架是否成为主解释，取决于相关 Challenge 是否被有效 rebut。"
        )
    else:
        text = (
            f"Bear 立场若成立，将提高对既有事实（{n}）的谨慎解读权重；"
            f"当前 resolution={dr.resolution}，不得把假设写成已发生事实。"
        )
    return AnalyzedStatement(
        kind="INFERENCE",
        text=text,
        canonical_finding_ids=[c.finding_id],
        evidence_ids=list(c.evidence_ids),
        debate_refs=list(dr.bear_reference_ids),
        numbers_used=nums[:4],
        assessment_strength=dr.assessment_strength,
    )


def _assessment_from_resolution(
    c: CanonicalFinding,
    dr: DebateResolution,
    nums: list[str],
) -> AnalyzedStatement:
    n = "、".join(nums[:5]) if nums else "关键事实"
    support = dr.support_strength
    if dr.resolution == "unresolved":
        text = (
            f"Debate 未裁定 {c.finding_id}：事实（{n}）清楚，但 Bull/Bear 解释无法被当前 "
            f"Challenge/Rebuttal 有效区分。assessment_strength={dr.assessment_strength}。"
            f"原因：{dr.resolution_reason}"
        )
        kind = "UNCERTAINTY"
    elif dr.resolution == "bull_supported":
        if support == "weak":
            text = (
                f"Debate bull_supported/weak：阶段性压力解释获得一定支持（有限幅度）；"
                f"不得写成基本面已经改善。事实（{n}）。依据：{dr.resolution_reason}"
            )
        elif support == "strong":
            text = (
                f"Debate bull_supported/strong：主导解释更明确偏向盈利缓冲框架，"
                f"但仍不得写成已经证明。事实（{n}）。依据：{dr.resolution_reason}"
            )
        else:
            text = (
                f"在 Debate resolution=bull_supported 下，主解释框架更偏向："
                f"既有高盈利事实构成缓冲，增长压力尚未被证明为结构性恶化；"
                f"但仍是解释框架选择，不是买卖建议。strength={dr.assessment_strength}。"
                f"依据：{dr.resolution_reason}"
            )
        kind = "INFERENCE"
    elif dr.resolution == "bear_supported":
        if support == "weak":
            text = (
                f"Debate bear_supported/weak：谨慎解释获得一定支持（有限幅度）；"
                f"不得写成增长逻辑已经失效。事实（{n}）。依据：{dr.resolution_reason}"
            )
        elif support == "strong":
            text = (
                f"Debate bear_supported/strong：主导解释更明确偏向增长不确定性优先，"
                f"但仍不得写成已经证明崩塌。事实（{n}）。依据：{dr.resolution_reason}"
            )
        else:
            text = (
                f"在 Debate resolution=bear_supported 下，主解释框架更偏向："
                f"增长承压应主导当前叙事，估值与乐观假设需更高验证门槛；"
                f"高盈利不自动解除该约束。strength={dr.assessment_strength}。"
                f"依据：{dr.resolution_reason}"
            )
        kind = "INFERENCE"
    else:
        text = (
            f"Debate resolution=partially_resolved：部分争议收敛，但 {c.finding_id} 仍有残余未决；"
            f"因此 Base 只能采用有限收敛的解释框架。strength={dr.assessment_strength}。"
            f"依据：{dr.resolution_reason}"
        )
        kind = "INFERENCE"

    return _stmt(
        kind=kind,
        text=text,
        canonical_finding_ids=[c.finding_id],
        evidence_ids=list(c.evidence_ids),
        debate_refs=dr.unresolved_challenges[:3]
        + dr.accepted_rebuttals[:2]
        + dr.rejected_rebuttals[:2]
        + dr.partially_accepted_rebuttals[:2],
        numbers_used=nums[:6],
        assessment_strength=dr.assessment_strength,
    )


def _build_tension(inp: FinalAnalystInput, c: CanonicalFinding) -> TensionResolution:
    dr = resolve_debate_for_tension(inp, c)
    bull_claims, bear_claims = claims_for_tension(inp, c.finding_id)
    claim_ids = {x.claim_id for x in bull_claims + bear_claims}
    challenges = challenges_for(inp, claim_ids)
    rebuttals = rebuttals_for(inp, {ch.challenge_id for ch in challenges})
    nums = _nums(c)

    ch_links = [
        TensionDebateLink(
            challenge_id=ch.challenge_id,
            claim_id=ch.target_claim_id,
            challenge_type=ch.challenge_type,
            summary=ch.argument[:160],
        )
        for ch in challenges[:4]
    ]
    rb_links = [
        TensionDebateLink(
            rebuttal_id=rb.rebuttal_id,
            challenge_id=rb.target_challenge_id,
            response_type=rb.response_type,
            summary=rb.argument[:160],
        )
        for rb in rebuttals[:4]
    ]

    return TensionResolution(
        tension_id=c.finding_id,
        research_question=c.research_question,
        fact_anchor=_fact_anchor(c),
        bull_reference=bull_claims[0].claim_id if bull_claims else "",
        bear_reference=bear_claims[0].claim_id if bear_claims else "",
        bull_interpretation=_bull_interpretation(c, dr, nums),
        bear_interpretation=_bear_interpretation(c, dr, nums),
        challenges=ch_links,
        rebuttals=rb_links,
        debate_resolution=dr,
        current_assessment=_assessment_from_resolution(c, dr, nums),
        conditions_to_change=[
            "连续报告期收入/净利润同比方向可核对切换 → 可能把 unresolved 推向单边收敛",
            "客户结构/渠道批价等 gap 被填补 → 改变阶段性 vs 结构性权重",
            "关键 Challenge 的 Rebuttal 从 partially_accept 转为 reject（或相反）→ 应触发 judgment flip",
        ],
    )


def _stmt(
    *,
    kind: str,
    text: str,
    canonical_finding_ids: list[str],
    evidence_ids: list[str],
    debate_refs: list[str] | None = None,
    numbers_used: list[str] | None = None,
    assessment_strength: str | None = None,
) -> AnalyzedStatement:
    return AnalyzedStatement(
        kind=kind,  # type: ignore[arg-type]
        text=text,
        canonical_finding_ids=canonical_finding_ids,
        evidence_ids=evidence_ids,
        debate_refs=debate_refs or [],
        numbers_used=numbers_used or [],
        assessment_strength=assessment_strength,  # type: ignore[arg-type]
        inference_status=classify_inference_status(text, kind=kind),  # type: ignore[arg-type]
    )


def _cross_tension_bridge(tensions: list[TensionResolution]) -> str:
    ids = [t.tension_id for t in tensions]
    has_profit = any("PROFIT" in i for i in ids)
    has_val = any("VALUATION" in i for i in ids)
    has_mkt = any("SHORT" in i or "MKT" in i for i in ids)
    parts: list[str] = []
    if has_profit and has_val:
        parts.append(
            "跨 tension DERIVED：增长恢复实际上是连接经营表现（PROFIT_VS_GROWTH）与估值解释"
            "（VALUATION_VS_GROWTH）的中间条件——因此增长不确定性不仅影响基本面判断，也抬高估值叙事门槛。"
        )
    if has_mkt and (has_profit or has_val):
        parts.append(
            "跨 tension：短期价格/均线结构改善（SHORT_VS_LONG）最多提供市场尺度旁证，"
            "不能自动解除基本面增长争议；价格改善≠增长争议已关闭。"
        )
    if not parts and len(tensions) >= 2:
        parts.append(
            f"跨 tension：同时消费 {[t.tension_id for t in tensions[:3]]}，"
            "解释优先级由 Debate resolution 与事实压力共同决定，而非罗列。"
        )
    return " ".join(parts)


def _primary_bundle(tensions: list[TensionResolution], findings: list[CanonicalFinding]):
    if not tensions:
        cal = calibrate_assessment("unresolved", None, "mild", None)
        return (
            "unresolved",
            cal.assessment_strength,
            None,
            "mild",
            cal.rationale,
            0,
        )
    dr = tensions[0].debate_resolution
    pressure = evidence_pressure(findings)
    cal = calibrate_assessment(dr.resolution, dr.support_strength, pressure, None)
    frame = calibrated_frame_phrase(
        resolution=dr.resolution,
        support=dr.support_strength,
        pressure=pressure,
    )
    amp = judgment_amplitude_rank(dr.support_strength, resolution=dr.resolution)
    return dr.resolution, cal.assessment_strength, cal.support_strength, pressure, frame, amp


def _executive(
    inp: FinalAnalystInput,
    tensions: list[TensionResolution],
    primary: CanonicalFinding,
    *,
    res: ResolutionKind,
    strength: str,
    support,
    pressure: str,
    frame: str,
) -> AnalyzedStatement:
    nums = _nums(primary)
    n = "、".join(nums[:5]) if nums else "关键事实"
    ids = [t.tension_id for t in tensions]
    bridge = _cross_tension_bridge(tensions)
    support_bit = f"support_strength={support}" if support else "support_strength=n/a"
    if res == "unresolved":
        text = (
            f"as_of={inp.research_as_of_date}：Debate 主 resolution=unresolved（{support_bit}）。"
            f"事实（{n}）支持“高盈利与增长承压并存”，但 Challenge/Rebuttal 未能裁定解释框架；"
            f"校准后主判断：{frame}。assessment_strength={strength}；evidence_pressure={pressure}。"
            f"删除 Debate 将无法得到该未决裁定。"
        )
    else:
        text = (
            f"as_of={inp.research_as_of_date}：Debate 主 resolution={res}（{support_bit}）。"
            f"在事实（{n}）与 Research pressure={pressure} 约束下，校准后主判断：{frame}。"
            f"assessment_strength={strength}。Debate resolution 是解释输入而非答案；"
            f"不得把弱支持写成强结论，也不得忽略仍有效的 Challenge。"
        )
    if bridge:
        text = f"{text} {bridge}"
    # Debate consumption semantics
    if tensions:
        dr = tensions[0].debate_resolution
        lim = dr.unresolved_challenges[:2]
        acc = dr.accepted_rebuttals[:2] or dr.rejected_rebuttals[:2] or dr.partially_accepted_rebuttals[:2]
        text += (
            f" Debate 语义：仍有效/未关闭 Challenge={lim or ['无']}；"
            f"关键 Rebuttal 处理={acc or ['无']}；"
            f"因此结论强度受 Challenge 限制，而非 Bull/Bear 条数。"
        )
    return _stmt(
        kind="INFERENCE" if res != "unresolved" else "UNCERTAINTY",
        text=text,
        canonical_finding_ids=ids,
        evidence_ids=sorted({eid for t in tensions for eid in t.fact_anchor.evidence_ids})[:16]
        if tensions
        else list(primary.evidence_ids)[:8],
        debate_refs=[t.debate_resolution.resolution for t in tensions],
        numbers_used=nums[:6],
        assessment_strength=strength,
    )


def _thesis(res: ResolutionKind, strength: str, primary: CanonicalFinding, frame: str) -> AnalyzedStatement:
    text = f"Core thesis（校准）：{frame}。strength={strength}。"
    if res == "unresolved":
        text += "不得把 Bull/Bear 条数平均成中性。"
    return _stmt(
        kind="INFERENCE",
        text=text,
        canonical_finding_ids=[primary.finding_id],
        evidence_ids=list(primary.evidence_ids)[:8],
        numbers_used=_nums(primary)[:4],
        assessment_strength=strength,
    )


def _basis(
    tensions: list[TensionResolution],
    res: ResolutionKind,
    *,
    support,
    pressure: str,
    frame: str,
) -> AssessmentBasis:
    primary = tensions[0] if tensions else None
    facts = []
    unresolved = []
    active = []
    accepted = []
    limiting = ""
    if primary:
        facts.append(primary.fact_anchor.text)
        dr = primary.debate_resolution
        unresolved.extend(dr.unresolved_challenges)
        active = list(dr.unresolved_challenges[:4])
        accepted = list(dr.accepted_rebuttals[:3] + dr.rejected_rebuttals[:3] + dr.partially_accepted_rebuttals[:3])
        limiting = active[0] if active else ("无开放 Challenge" if res != "unresolved" else "解释未决")
        reason = (
            f"Base 选择依据 Debate resolution={res} + support_strength={support} + "
            f"evidence_pressure={pressure}：{dr.resolution_reason}；校准框架：{frame}"
        )
        adv = {
            "bull_supported": "Bull 解释边界相对更受 Challenge/Rebuttal 结果支持（仍受 Research pressure 约束）",
            "bear_supported": "Bear 解释边界相对更受 Challenge/Rebuttal 结果支持（仍受 Research pressure 约束）",
            "unresolved": "无解释优势；优势在于诚实保留未决",
            "partially_resolved": "仅有限解释优势，残余争议仍在",
        }[res]
    else:
        reason = "无 tension"
        adv = ""
    return AssessmentBasis(
        supported_facts=facts,
        interpretation_advantage=adv,
        unresolved=unresolved[:6],
        reason_base_case_selected=reason,
        primary_resolution=res,
        debate_support_strength=support,
        evidence_pressure=pressure,  # type: ignore[arg-type]
        calibrated_frame=frame,
        active_challenges=active,
        accepted_rebuttals=accepted,
        limiting_challenge=limiting,
    )


def _scenarios(
    inp: FinalAnalystInput,
    primary: CanonicalFinding,
    res: ResolutionKind,
    strength: str,
    *,
    support,
    pressure: str,
    frame: str,
) -> tuple[Scenario, Scenario, Scenario]:
    nums = _nums(primary)
    eids = list(primary.evidence_ids)
    cid = [primary.finding_id]
    n = "、".join(nums[:5]) if nums else "关键事实"

    base_text = (
        f"Base（非机械）：resolution={res}、support_strength={support}、"
        f"evidence_pressure={pressure}。最符合当前证据且不过度补全的解释：{frame}。"
        f"事实锚点（{n}）；strength={strength}。"
    )

    base = Scenario(
        label="base",
        thesis=_stmt(
            kind="INFERENCE" if res != "unresolved" else "UNCERTAINTY",
            text=base_text,
            canonical_finding_ids=cid,
            evidence_ids=eids[:8],
            numbers_used=nums[:6],
            assessment_strength=strength,
        ),
        supporting_canonical_ids=cid,
        required_assumptions=[],
        inconsistent_with=[
            "把 Bull/Bear claim 条数平均成中性",
            "把 Debate resolution 直接当作最终答案",
            "在 weak support 时宣称基本面已经改善/增长逻辑已经失效",
        ],
        explanation_shift_variable="Debate support_strength × Research evidence_pressure",
    )

    bull = Scenario(
        label="bull",
        thesis=_stmt(
            kind="INFERENCE",
            text=(
                "Bull 边界：仅当出现可核对的新证据——连续报告期收入与利润同比改善——"
                "之后，Bull 解释才获得更强支持，主解释才可移向“阶段性承压得到验证”。"
                "在该新证据出现前，不得把乐观描述当作 Base。"
            ),
            canonical_finding_ids=cid,
            evidence_ids=eids[:6],
            numbers_used=nums[:4],
        ),
        supporting_canonical_ids=cid,
        required_assumptions=[
            _stmt(
                kind="ASSUMPTION",
                text="假设后续出现可核对的多期增长改善（当前未成立）。",
                canonical_finding_ids=cid,
                evidence_ids=eids[:2],
            )
        ],
        inconsistent_with=["声称增长已经恢复", "忽略现有同比压力事实", "仅用乐观措辞替代触发条件"],
        explanation_shift_variable="多期收入/净利润同比方向（新证据触发）",
    )
    bear = Scenario(
        label="bear",
        thesis=_stmt(
            kind="INFERENCE",
            text=(
                "Bear 边界：仅当出现可核对的新证据——多期增长持续恶化且无对冲证据——"
                "之后，Bear 解释才获得更强支持，主解释才可移向“增长压力权重进一步上升”。"
                "在该新证据出现前，不得把悲观描述当作 Base。"
            ),
            canonical_finding_ids=cid,
            evidence_ids=eids[:6],
            numbers_used=nums[:4],
        ),
        supporting_canonical_ids=cid,
        required_assumptions=[
            _stmt(
                kind="ASSUMPTION",
                text="假设后续多期增长持续恶化且缺乏对冲证据（当前仅为条件分支）。",
                canonical_finding_ids=cid,
                evidence_ids=eids[:2],
            )
        ],
        inconsistent_with=["把高 ROE 写成增长驱动仍强", "抹掉 evidence_insufficient 挑战", "仅用悲观措辞替代触发条件"],
        explanation_shift_variable="多期增长恶化是否持续（新证据触发）",
    )
    return base, bull, bear


def _drivers(tensions: list[TensionResolution]) -> list[AnalyzedStatement]:
    out = []
    for t in tensions[:3]:
        out.append(
            AnalyzedStatement(
                kind="INFERENCE",
                text=(
                    f"驱动（{t.tension_id}）：Debate resolution={t.debate_resolution.resolution} "
                    f"决定该命题在最终判断中的权重；{t.debate_resolution.resolution_reason[:120]}"
                ),
                canonical_finding_ids=[t.tension_id],
                evidence_ids=list(t.fact_anchor.evidence_ids),
                debate_refs=t.debate_resolution.bull_reference_ids + t.debate_resolution.bear_reference_ids,
                numbers_used=[],
                assessment_strength=t.debate_resolution.assessment_strength,
            )
        )
    return out


def _view_changers(primary: CanonicalFinding, res: ResolutionKind) -> list[ViewChanger]:
    return [
        ViewChanger(
            trigger_evidence_description="连续≥2个报告期营业收入与归母净利润同比同向改善或恶化（可核对）",
            would_affect="primary_resolution / base_case",
            direction="unresolved_to_resolved",
            related_gap_or_boundary="单期同比不足以区分阶段性与结构性",
            canonical_finding_ids=[primary.finding_id],
        ),
        ViewChanger(
            trigger_evidence_description="关键 Challenge 的 Rebuttal 从 partially_accept/accept 变为 reject（或相反）",
            would_affect="debate_resolution",
            direction="more_constructive" if res == "unresolved" else "more_cautious",
            related_gap_or_boundary="Debate Challenge/Rebuttal 状态是 judgment driver",
            canonical_finding_ids=[primary.finding_id],
        ),
        ViewChanger(
            trigger_evidence_description="公司披露可核对客户结构/集中度或渠道库存与批价",
            would_affect="research_gaps",
            direction="unresolved_to_resolved",
            related_gap_or_boundary="客户结构等 Research gap",
            canonical_finding_ids=[primary.finding_id],
        ),
    ]


def _gaps_unc(inp: FinalAnalystInput, primary_ids: list[str]) -> tuple[list[AnalyzedStatement], list[AnalyzedStatement]]:
    gaps = []
    for g in list(inp.fundamental.research_gaps) + list(inp.market.research_gaps):
        if g.status != "insufficient_evidence":
            continue
        gaps.append(
            AnalyzedStatement(
                kind="UNCERTAINTY",
                text=f"继承 Research gap：{g.claim} FA 不得补全为已确认事实。",
                canonical_finding_ids=[],
                evidence_ids=[],
            )
        )
    unc = []
    for u in inp.debate.debate_summary.unresolved_issues or []:
        unc.append(
            AnalyzedStatement(
                kind="UNCERTAINTY",
                text=f"Debate unresolved survival：{u}",
                canonical_finding_ids=primary_ids,
                evidence_ids=[],
                debate_refs=["debate_summary.unresolved_issues"],
            )
        )
    seen = set()
    uniq = []
    for g in gaps:
        if g.text not in seen:
            seen.add(g.text)
            uniq.append(g)
    return uniq[:6], unc[:6]


def synthesize_final_analyst(inp: FinalAnalystInput) -> FinalAnalystOutput:
    selected = _pick_tensions(inp, max_n=3)
    if not selected:
        raise ValueError("insufficient_evidence: no canonical findings for Final Analyst")

    tensions = [_build_tension(inp, c) for c in selected]
    primary = selected[0]
    all_findings = all_canonical(inp)
    res, strength, support, pressure, frame, _amp = _primary_bundle(tensions, selected)
    # Prefer selected tensions for pressure; if mild/severe fixtures mutate claim, reflect that.
    # Fallback blend: if selected alone is mild but full set is severe, keep elevated floor from selected only.
    _ = all_findings  # contract still consumed via selected from all_canonical pick
    exec_s = _executive(
        inp, tensions, primary, res=res, strength=strength, support=support, pressure=pressure, frame=frame
    )
    thesis = _thesis(res, strength, primary, frame)
    basis = _basis(tensions, res, support=support, pressure=pressure, frame=frame)
    base, bull, bear = _scenarios(
        inp, primary, res, strength, support=support, pressure=pressure, frame=frame
    )
    drivers = _drivers(tensions)
    changers = _view_changers(primary, res)
    gaps, unc = _gaps_unc(inp, [c.finding_id for c in selected])

    for t in tensions:
        if t.debate_resolution.resolution == "unresolved":
            unc.insert(
                0,
                _stmt(
                    kind="UNCERTAINTY",
                    text=f"Primary tension {t.tension_id} Debate unresolved：{t.debate_resolution.resolution_reason}",
                    canonical_finding_ids=[t.tension_id],
                    evidence_ids=list(t.debate_resolution.decisive_evidence_ids)[:4],
                    debate_refs=t.debate_resolution.unresolved_challenges[:3],
                    assessment_strength="unresolved",
                ),
            )
            break

    traces = [
        TraceLink(
            conclusion_ref="executive_assessment",
            canonical_finding_ids=[t.tension_id for t in tensions],
            evidence_ids=list(tensions[0].debate_resolution.decisive_evidence_ids)[:10],
            debate_refs=[t.debate_resolution.resolution for t in tensions],
        ),
        TraceLink(
            conclusion_ref="assessment_basis",
            canonical_finding_ids=[primary.finding_id],
            evidence_ids=list(primary.evidence_ids)[:8],
            debate_refs=list(tensions[0].debate_resolution.unresolved_challenges)[:4],
        ),
    ]
    for t in tensions:
        traces.append(
            TraceLink(
                conclusion_ref=f"core_tensions:{t.tension_id}",
                canonical_finding_ids=[t.tension_id],
                evidence_ids=list(t.debate_resolution.decisive_evidence_ids)[:8],
                debate_refs=[t.debate_resolution.resolution] + t.debate_resolution.unresolved_challenges[:2],
            )
        )

    used_eids = sorted({e for t in tensions for e in t.debate_resolution.decisive_evidence_ids} | set(primary.evidence_ids))
    used_canon = [c.finding_id for c in selected]

    return FinalAnalystOutput(
        stock_code=inp.stock_code,
        research_as_of_date=inp.research_as_of_date,
        analyst_mode=inp.mode if inp.mode in {"grounded", "openai"} else "grounded",
        executive_assessment=exec_s,
        core_thesis=thesis,
        key_drivers=drivers,
        core_tensions=tensions,
        assessment_basis=basis,
        base_case=base,
        bull_case=bull,
        bear_case=bear,
        what_would_change_my_view=changers,
        uncertainty=unc[:8],
        research_gaps=gaps,
        evidence_trace=traces,
        canonical_finding_ids=used_canon,
        evidence_ids=used_eids,
        meta=FinalAnalystMeta(
            no_trade_advice=True,
            grounded_is_not_autonomous=True,
            selected_tension_ids=used_canon,
            primary_resolution=res,
            assessment_strength=strength,  # type: ignore[arg-type]
            debate_support_strength=support,
            evidence_pressure=pressure,  # type: ignore[arg-type]
            notes=[
                "Debate resolution is an input, not the answer",
                "support_strength calibrates claim amplitude (not probability)",
                "evidence_pressure from Research prevents mechanical Debate following",
                "Grounded synthesizer is deterministic, not autonomous research",
            ],
        ),
    )
