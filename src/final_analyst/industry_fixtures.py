"""Cross-industry FinalAnalystInput fixtures (Round 5).

Reuse 600519 Research skeleton (EvidencePack read-only for synthesize), then mutate
canonical claims / stock_code / boundaries so manufacturing & semiconductor have
distinct Research fingerprints under controllable Debate resolutions.
"""

from __future__ import annotations

from pathlib import Path

from debate.schemas import (
    BearResearch,
    BullResearch,
    Challenge,
    DebateExecutionMeta,
    DebateResult,
    DebateSummary,
    Rebuttal,
    ResearchClaim,
)
from evidence.pack import EvidencePack
from research.context import build_fundamental_context, build_market_context
from research.schemas import CanonicalFinding
from research.synthesize import synthesize_fundamental, synthesize_market

from final_analyst.contract import FinalAnalystInput, build_final_analyst_input


def _debate(
    *,
    stock: str,
    tension_id: str,
    force_resolution: str,
    force_strength: str,
    eids: list[str],
    bull_claim: str,
    bear_claim: str,
    challenge_arg: str,
    unresolved: list[str],
) -> DebateResult:
    bull = BullResearch(
        stock_code=stock,
        thesis="Bull thesis industry fixture",
        claims=[
            ResearchClaim(
                claim_id="BULL_01",
                stance="bull",
                claim=bull_claim,
                reasoning="industry fixture",
                evidence_ids=eids[:2] or ["e1"],
                confidence=0.8,
                importance=0.9,
                canonical_finding_ids=[tension_id],
            )
        ],
        key_risks=["关键不确定性仍在"],
        uncertainties=["条件未验证"],
    )
    bear = BearResearch(
        stock_code=stock,
        thesis="Bear thesis industry fixture",
        claims=[
            ResearchClaim(
                claim_id="BEAR_01",
                stance="bear",
                claim=bear_claim,
                reasoning="industry fixture",
                evidence_ids=eids[:2] or ["e1"],
                confidence=0.8,
                importance=0.9,
                canonical_finding_ids=[tension_id],
            )
        ],
        key_opportunities=["缓冲仍可能存在"],
        uncertainties=["恶化未证实"],
    )
    if force_resolution == "bull_supported":
        challenges = [
            Challenge(
                challenge_id="CH_01",
                challenger="bear",
                target_claim_id="BULL_01",
                challenge_type="interpretation_conflict",
                argument=challenge_arg,
                evidence_ids=eids[:1] or ["e1"],
                strength=0.55,
            )
        ]
        rebuttals = [
            Rebuttal(
                rebuttal_id="RB_01",
                author="bull",
                target_challenge_id="CH_01",
                response_type="reject",
                argument="Challenge 未提供足以推翻建设性解释的新证据，予以 reject。",
                evidence_ids=eids[:1] or ["e1"],
            )
        ]
    elif force_resolution == "bear_supported":
        challenges = [
            Challenge(
                challenge_id="CH_01",
                challenger="bull",
                target_claim_id="BEAR_01",
                challenge_type="interpretation_conflict",
                argument=challenge_arg,
                evidence_ids=eids[:1] or ["e1"],
                strength=0.55,
            )
        ]
        rebuttals = [
            Rebuttal(
                rebuttal_id="RB_01",
                author="bear",
                target_challenge_id="CH_01",
                response_type="reject",
                argument="Challenge 未推翻谨慎解释的核心证据约束，予以 reject。",
                evidence_ids=eids[:1] or ["e1"],
            )
        ]
    else:
        challenges = [
            Challenge(
                challenge_id="CH_01",
                challenger="bear",
                target_claim_id="BULL_01",
                challenge_type="evidence_insufficient",
                argument=challenge_arg,
                evidence_ids=eids[:1] or ["e1"],
                strength=0.85,
            )
        ]
        rebuttals = [
            Rebuttal(
                rebuttal_id="RB_01",
                author="bull",
                target_challenge_id="CH_01",
                response_type="partially_accept",
                argument="承认证据不足，无法完全反驳。",
                evidence_ids=eids[:1] or ["e1"],
            )
        ]

    return DebateResult(
        stock_code=stock,
        bull=bull,
        bear=bear,
        challenges=challenges,
        rebuttals=rebuttals,
        debate_summary=DebateSummary(
            shared_facts=["双方承认核心可核对事实存在"],
            core_disagreements=["解释框架分歧"],
            unresolved_issues=unresolved,
        ),
        execution=DebateExecutionMeta(
            started_at="2026-08-15T00:00:00+00:00",
            finished_at="2026-08-15T00:00:01+00:00",
            duration_ms=1,
            rounds_executed=["claims", "challenges", "rebuttals"],
        ),
        metadata={
            "force_resolution": force_resolution,
            "force_assessment_strength": force_strength,
            "industry_fixture": True,
        },
    )


def _retarget_stock(fund, market, stock: str):
    return fund.model_copy(update={"stock_code": stock}), market.model_copy(update={"stock_code": stock})


def _rewrite_primary(
    fund,
    *,
    claim: str,
    numbers: list[str],
    finding_id: str | None = None,
):
    cans: list[CanonicalFinding] = []
    done = False
    for c in fund.canonical_findings:
        if not done and "PROFIT_VS_GROWTH" in (c.finding_id or ""):
            upd: dict = {"claim": claim, "numbers_preserved": numbers}
            if finding_id:
                upd["finding_id"] = finding_id
                upd["research_question"] = finding_id
            eids = list(c.evidence_ids or [])
            if len(eids) < 2:
                eids = eids + ["eid_pad_industry"]
                upd["evidence_ids"] = eids
            cans.append(c.model_copy(update=upd))
            done = True
        else:
            cans.append(c)
    if not done and cans:
        c0 = cans[0]
        upd = {"claim": claim, "numbers_preserved": numbers}
        if finding_id:
            upd["finding_id"] = finding_id
            upd["research_question"] = finding_id
        cans[0] = c0.model_copy(update=upd)
    return fund.model_copy(update={"canonical_findings": cans, "summary": claim[:180]})


def build_industry_fixtures(root: Path | None = None) -> list[tuple[str, FinalAnalystInput]]:
    root = root or Path(__file__).resolve().parents[2]
    pack = EvidencePack.load_json(root / "examples" / "600519_evidence_pack.json")
    base_fund = synthesize_fundamental(pack.stock_code, build_fundamental_context(pack))
    base_market = synthesize_market(pack.stock_code, build_market_context(pack))
    tension = next(c for c in base_fund.canonical_findings if "PROFIT_VS_GROWTH" in c.finding_id)
    eids = list(tension.evidence_ids)[:3]
    tid = tension.finding_id

    out: list[tuple[str, FinalAnalystInput]] = []

    # 1) Consumer 600519 unresolved
    out.append(
        (
            "consumer_unresolved",
            build_final_analyst_input(
                fundamental=base_fund,
                market=base_market,
                debate=_debate(
                    stock="600519",
                    tension_id=tid,
                    force_resolution="unresolved",
                    force_strength="tentative",
                    eids=eids,
                    bull_claim="高盈利缓冲使增长压力更可能是阶段性",
                    bear_claim="增长承压可能更持久，削弱增长叙事",
                    challenge_arg="现有证据不足以区分阶段性与结构性",
                    unresolved=["阶段性 vs 结构性增长压力仍未裁定"],
                ),
                mode="grounded",
            ),
        )
    )

    # 2) Manufacturing — volume vs margin (bull_supported moderate)
    mfg_fund, mfg_mkt = _retarget_stock(base_fund, base_market, "000338")
    mfg_fund = _rewrite_primary(
        mfg_fund,
        claim=(
            "制造周期：销量同比+8.2%但毛利率降至18.4%（量增利不增）；"
            "在手订单覆盖约9个月、资本开支同比+22%。行业周期位置与扩产回报仍不确定。"
        ),
        numbers=["8.2%", "18.4%", "9", "22%"],
        finding_id="TENSION_MFG_VOLUME_VS_MARGIN",
    )
    out.append(
        (
            "mfg_bull_moderate",
            build_final_analyst_input(
                fundamental=mfg_fund,
                market=mfg_mkt,
                debate=_debate(
                    stock="000338",
                    tension_id="TENSION_MFG_VOLUME_VS_MARGIN",
                    force_resolution="bull_supported",
                    force_strength="moderate",
                    eids=eids,
                    bull_claim="订单与销量改善支持周期回暖，毛利率承压是成本滞后",
                    bear_claim="量增利不增说明价格战，扩产可能加剧回报压力",
                    challenge_arg="订单覆盖不足以证明毛利率修复路径",
                    unresolved=[],
                ),
                mode="grounded",
            ),
        )
    )

    # 3) Semiconductor — util vs ASP (bear_supported moderate)
    semi_fund, semi_mkt = _retarget_stock(base_fund, base_market, "688981")
    semi_fund = _rewrite_primary(
        semi_fund,
        claim=(
            "半导体代工：产能利用率回升至78%，但 ASP 同比-6.5%；"
            "研发与资本开支现金消耗加速，经营现金流/收入约12%。"
            "外生政策与制程验证缺口不可由财务截面单独裁定。"
        ),
        numbers=["78%", "6.5%", "12%"],
        finding_id="TENSION_SEMI_UTIL_VS_ASP",
    )
    out.append(
        (
            "semi_bear_moderate",
            build_final_analyst_input(
                fundamental=semi_fund,
                market=semi_mkt,
                debate=_debate(
                    stock="688981",
                    tension_id="TENSION_SEMI_UTIL_VS_ASP",
                    force_resolution="bear_supported",
                    force_strength="moderate",
                    eids=eids,
                    bull_claim="利用率回升是周期底部信号，ASP 压力过渡性",
                    bear_claim="ASP 下行叠加现金消耗，复苏叙事证据不足",
                    challenge_arg="利用率回升不能覆盖 ASP 与现金约束",
                    unresolved=[],
                ),
                mode="grounded",
            ),
        )
    )

    # 4+5) Same bull_supported/strong, different Research → non-mechanical
    mfg2, mkt2 = _retarget_stock(base_fund, base_market, "000338")
    mfg2 = _rewrite_primary(
        mfg2,
        claim="制造：销量+现金流同步改善，毛利率仅小幅波动；压力偏 mild。",
        numbers=["8.2%", "1.1%"],
        finding_id="TENSION_MFG_VOLUME_VS_MARGIN",
    )
    semi2, smkt2 = _retarget_stock(base_fund, base_market, "688981")
    semi2 = _rewrite_primary(
        semi2,
        claim=(
            "半导体：利用率回升但 ASP 显著下滑、现金消耗加速；"
            "即便 Debate bull_supported，Research 压力偏 severe，不得机械乐观。"
        ),
        numbers=["78%", "6.5%", "12%"],
        finding_id="TENSION_SEMI_UTIL_VS_ASP",
    )
    out.append(
        (
            "mfg_bull_strong_mild",
            build_final_analyst_input(
                fundamental=mfg2,
                market=mkt2,
                debate=_debate(
                    stock="000338",
                    tension_id="TENSION_MFG_VOLUME_VS_MARGIN",
                    force_resolution="bull_supported",
                    force_strength="strong",
                    eids=eids,
                    bull_claim="量价与现金流同向改善",
                    bear_claim="周期仍可能回落",
                    challenge_arg="改善幅度仍需多期确认",
                    unresolved=[],
                ),
                mode="grounded",
            ),
        )
    )
    out.append(
        (
            "semi_bull_strong_severe",
            build_final_analyst_input(
                fundamental=semi2,
                market=smkt2,
                debate=_debate(
                    stock="688981",
                    tension_id="TENSION_SEMI_UTIL_VS_ASP",
                    force_resolution="bull_supported",
                    force_strength="strong",
                    eids=eids,
                    bull_claim="利用率回升支持建设性解释",
                    bear_claim="ASP 与现金约束限制乐观幅度",
                    challenge_arg="强支持仍受现金与 ASP 压力限制",
                    unresolved=["ASP 与政策约束仍在"],
                ),
                mode="grounded",
            ),
        )
    )
    return out
