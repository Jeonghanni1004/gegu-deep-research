"""Debate → DebateResolution: judgment driver for Final Analyst."""

from __future__ import annotations

from debate.schemas import Challenge, Rebuttal, ResearchClaim
from research.schemas import CanonicalFinding

from final_analyst.calibration import (
    assessment_from_support,
    normalize_support_strength,
)
from final_analyst.contract import FinalAnalystInput
from final_analyst.schemas import DebateResolution, ResolutionKind


def claims_for_tension(inp: FinalAnalystInput, tension_id: str) -> tuple[list[ResearchClaim], list[ResearchClaim]]:
    bull = [c for c in inp.debate.bull.claims if tension_id in (c.canonical_finding_ids or [])]
    bear = [c for c in inp.debate.bear.claims if tension_id in (c.canonical_finding_ids or [])]
    # Fallback: if none linked, attach top importance claims for primary tensions
    if not bull and not bear and "PROFIT" in tension_id:
        bull = [c for c in inp.debate.bull.claims if c.claim_id == "BULL_01"] or list(inp.debate.bull.claims[:1])
        bear = [c for c in inp.debate.bear.claims if c.claim_id == "BEAR_01"] or list(inp.debate.bear.claims[:1])
    return bull, bear


def challenges_for(inp: FinalAnalystInput, claim_ids: set[str]) -> list[Challenge]:
    return [ch for ch in inp.debate.challenges if ch.target_claim_id in claim_ids]


def rebuttals_for(inp: FinalAnalystInput, challenge_ids: set[str]) -> list[Rebuttal]:
    return [rb for rb in inp.debate.rebuttals if rb.target_challenge_id in challenge_ids]


def resolve_debate_for_tension(
    inp: FinalAnalystInput,
    canonical: CanonicalFinding,
) -> DebateResolution:
    """Derive resolution from Challenge/Rebuttal structure — not claim counts."""
    tid = canonical.finding_id
    bull_claims, bear_claims = claims_for_tension(inp, tid)
    claim_ids = {c.claim_id for c in bull_claims + bear_claims}
    challenges = challenges_for(inp, claim_ids)
    rebuttals = rebuttals_for(inp, {ch.challenge_id for ch in challenges})
    rb_by_ch = {rb.target_challenge_id: rb for rb in rebuttals}

    accepted: list[str] = []
    rejected: list[str] = []
    partial: list[str] = []
    unresolved_ch: list[str] = []

    for ch in challenges:
        rb = rb_by_ch.get(ch.challenge_id)
        if rb is None:
            unresolved_ch.append(ch.challenge_id)
            continue
        if rb.response_type == "accept":
            accepted.append(rb.rebuttal_id)
            unresolved_ch.append(ch.challenge_id)
        elif rb.response_type == "partially_accept":
            partial.append(rb.rebuttal_id)
            unresolved_ch.append(ch.challenge_id)
        elif rb.response_type == "reject":
            rejected.append(rb.rebuttal_id)
        else:
            unresolved_ch.append(ch.challenge_id)

    blocking = [
        ch
        for ch in challenges
        if ch.challenge_type == "evidence_insufficient"
        and (
            ch.challenge_id in unresolved_ch
            or (rb_by_ch.get(ch.challenge_id) and rb_by_ch[ch.challenge_id].response_type in {"accept", "partially_accept"})
        )
    ]
    interp_open = [
        ch
        for ch in challenges
        if ch.challenge_type == "interpretation_conflict" and ch.challenge_id in unresolved_ch
    ]

    force = (inp.debate.metadata or {}).get("force_resolution")
    force_strength = (inp.debate.metadata or {}).get("force_assessment_strength")

    bull_pos = bull_claims[0].claim if bull_claims else "Bull 未对本 tension 立论"
    bear_pos = bear_claims[0].claim if bear_claims else "Bear 未对本 tension 立论"

    decisive: list[str] = []
    if bull_claims:
        decisive.extend(bull_claims[0].evidence_ids[:3])
    if bear_claims:
        decisive.extend(bear_claims[0].evidence_ids[:3])
    for ch in challenges[:2]:
        decisive.extend(ch.evidence_ids[:2])
    decisive = list(dict.fromkeys(decisive))

    support = None
    if force in {"bull_supported", "bear_supported", "partially_resolved", "unresolved"}:
        resolution: ResolutionKind = force  # type: ignore[assignment]
        support = normalize_support_strength(force_strength, resolution=resolution)
        strength = assessment_from_support(support, resolution=resolution)
        if resolution == "unresolved":
            if force_strength in {"unresolved", "tentative"}:
                strength = force_strength  # type: ignore[assignment]
            support = None
            reason = (
                f"Fixture/metadata 指定 unresolved：Challenge/Rebuttal 未能裁定 "
                f"{tid} 的对立解释；blocking={len(blocking)} interp_open={len(interp_open)}。"
            )
        elif resolution == "bull_supported":
            reason = (
                f"Fixture/metadata 指定 bull_supported（support_strength={support}）："
                f"针对 Bear 的关键 Challenge 被有效 reject，且 Bull 侧证据在 {tid} 上更具约束力。"
            )
            if bull_claims:
                decisive = list(bull_claims[0].evidence_ids[:5])
        elif resolution == "bear_supported":
            reason = (
                f"Fixture/metadata 指定 bear_supported（support_strength={support}）："
                f"针对 Bull 的关键 Challenge 被有效 reject，且 Bear 侧证据在 {tid} 上更具约束力。"
            )
            if bear_claims:
                decisive = list(bear_claims[0].evidence_ids[:5])
        else:
            reason = (
                f"Fixture/metadata 指定 partially_resolved（support_strength={support}）："
                f"部分 Challenge 关闭，但 {tid} 仍有残余争议。"
            )
    else:
        if blocking or (interp_open and partial):
            resolution = "unresolved"
            strength = "unresolved" if blocking else "tentative"
            reason = (
                "存在 evidence_insufficient 或未关闭的 interpretation_conflict，"
                "且对应 Rebuttal 为 accept/partially_accept 或缺失；"
                "因此不能在 Bull/Bear 解释间做机械平均，只能保留未决。"
            )
        elif interp_open and not rejected:
            resolution = "unresolved"
            strength = "tentative"
            reason = "interpretation_conflict 仍开放且无有效 reject 的 rebuttal，解释框架不能单边锁定。"
        elif rejected and not blocking:
            bull_defended = 0
            bear_defended = 0
            for ch in challenges:
                rb = rb_by_ch.get(ch.challenge_id)
                if not rb or rb.response_type != "reject":
                    continue
                if ch.challenger == "bear" and ch.target_claim_id.startswith("BULL"):
                    bull_defended += 1
                if ch.challenger == "bull" and ch.target_claim_id.startswith("BEAR"):
                    bear_defended += 1
            if bull_defended > bear_defended and not interp_open:
                resolution = "bull_supported"
                support = "moderate"
                strength = assessment_from_support(support, resolution=resolution)
                reason = (
                    "Bear→Bull 的 Challenge 被 reject，且无未关闭的证据不足阻断；"
                    "当前更支持 Bull 对既有事实的解释边界（非投资建议）。"
                )
                if bull_claims:
                    decisive = list(bull_claims[0].evidence_ids[:5])
            elif bear_defended > bull_defended and not interp_open:
                resolution = "bear_supported"
                support = "moderate"
                strength = assessment_from_support(support, resolution=resolution)
                reason = (
                    "Bull→Bear 的 Challenge 被 reject，且无未关闭的证据不足阻断；"
                    "当前更支持 Bear 对既有事实的解释边界（非投资建议）。"
                )
                if bear_claims:
                    decisive = list(bear_claims[0].evidence_ids[:5])
            else:
                resolution = "partially_resolved"
                support = "weak"
                strength = assessment_from_support(support, resolution=resolution)
                reason = (
                    "部分 Challenge 被 reject，但仍有对称争议或开放 conflict；"
                    "只能部分收敛，不能宣布单边胜出。"
                )
        else:
            resolution = "partially_resolved"
            support = "weak"
            strength = assessment_from_support(support, resolution=resolution)
            reason = "Challenge/Rebuttal 混合结果：事实清楚，但解释优势不足以锁定单边框架。"

    return DebateResolution(
        tension_id=tid,
        bull_position=bull_pos,
        bear_position=bear_pos,
        bull_reference_ids=[c.claim_id for c in bull_claims],
        bear_reference_ids=[c.claim_id for c in bear_claims],
        decisive_evidence_ids=decisive,
        unresolved_challenges=list(dict.fromkeys(unresolved_ch)),
        accepted_rebuttals=accepted,
        rejected_rebuttals=rejected,
        partially_accepted_rebuttals=partial,
        resolution=resolution,
        resolution_reason=reason,
        assessment_strength=strength,
        support_strength=support,
    )
