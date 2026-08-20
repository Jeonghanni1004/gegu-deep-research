"""Six Live A/B fixtures — same Research base, controlled Debate / pressure variants."""

from __future__ import annotations

from dataclasses import dataclass
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
from research.synthesize import synthesize_fundamental, synthesize_market

from final_analyst.contract import FinalAnalystInput, build_final_analyst_input


@dataclass(frozen=True)
class LiveFixture:
    fixture_id: str
    title: str
    intent: str
    inp: FinalAnalystInput


def _debate(
    *,
    stock: str,
    tension_id: str,
    force_resolution: str,
    force_strength: str,
    eids: list[str],
    unresolved_issues: list[str] | None = None,
    extra_challenges: list[Challenge] | None = None,
    extra_rebuttals: list[Rebuttal] | None = None,
    bull_claim: str | None = None,
    bear_claim: str | None = None,
    adversarial: bool = False,
) -> DebateResult:
    bull_text = bull_claim or "增长压力可能是阶段性的，高盈利构成缓冲。"
    bear_text = bear_claim or "增长承压可能更持久，削弱增长驱动叙事。"
    if adversarial:
        bull_text = "（误导性）现有证据已经证明增长全面恢复，估值应立即重估。"
        bear_text = "（被压制）增长仍不确定。"

    bull = BullResearch(
        stock_code=stock,
        thesis="Bull thesis live fixture",
        claims=[
            ResearchClaim(
                claim_id="BULL_01",
                stance="bull",
                claim=bull_text,
                reasoning="live fixture",
                evidence_ids=eids[:2] or ["e1"],
                confidence=0.9 if adversarial else 0.8,
                importance=0.9,
                canonical_finding_ids=[tension_id],
            )
        ],
        key_risks=["增长仍不确定"],
        uncertainties=["阶段性未验证"],
    )
    bear = BearResearch(
        stock_code=stock,
        thesis="Bear thesis live fixture",
        claims=[
            ResearchClaim(
                claim_id="BEAR_01",
                stance="bear",
                claim=bear_text,
                reasoning="live fixture",
                evidence_ids=eids[:2] or ["e1"],
                confidence=0.8,
                importance=0.9,
                canonical_finding_ids=[tension_id],
            )
        ],
        key_opportunities=["高盈利仍在"],
        uncertainties=["结构未证实"],
    )

    if force_resolution == "unresolved":
        challenges = [
            Challenge(
                challenge_id="CH_BEAR_01",
                challenger="bear",
                target_claim_id="BULL_01",
                challenge_type="evidence_insufficient",
                argument="现有证据不足以区分阶段性与结构性。",
                evidence_ids=eids[:1] or ["e1"],
                strength=0.85,
            )
        ]
        rebuttals = [
            Rebuttal(
                rebuttal_id="RB_BULL_01",
                author="bull",
                target_challenge_id="CH_BEAR_01",
                response_type="partially_accept",
                argument="承认单期证据不足，无法完全反驳。",
                evidence_ids=eids[:1] or ["e1"],
            )
        ]
        unresolved = unresolved_issues or ["单期同比不足以裁定阶段性 vs 结构性"]
    elif force_resolution == "bull_supported":
        challenges = [
            Challenge(
                challenge_id="CH_BEAR_01",
                challenger="bear",
                target_claim_id="BULL_01",
                challenge_type="interpretation_conflict",
                argument="Bear 质疑 Bull 过度强调缓冲。",
                evidence_ids=eids[:1] or ["e1"],
                strength=0.6,
            )
        ]
        rebuttals = [
            Rebuttal(
                rebuttal_id="RB_BULL_01",
                author="bull",
                target_challenge_id="CH_BEAR_01",
                response_type="reject",
                argument="Challenge 未提供足以推翻缓冲解释的新证据，予以 reject。",
                evidence_ids=eids[:2] or ["e1"],
            )
        ]
        unresolved = unresolved_issues or []
    else:  # bear_supported
        challenges = [
            Challenge(
                challenge_id="CH_BULL_01",
                challenger="bull",
                target_claim_id="BEAR_01",
                challenge_type="interpretation_conflict",
                argument="Bull 质疑 Bear 过度外推。",
                evidence_ids=eids[:1] or ["e1"],
                strength=0.6,
            )
        ]
        rebuttals = [
            Rebuttal(
                rebuttal_id="RB_BEAR_01",
                author="bear",
                target_challenge_id="CH_BULL_01",
                response_type="reject",
                argument="增长压力证据未被推翻，予以 reject。",
                evidence_ids=eids[:2] or ["e1"],
            )
        ]
        unresolved = unresolved_issues or []

    if extra_challenges:
        challenges = list(challenges) + list(extra_challenges)
    if extra_rebuttals:
        rebuttals = list(rebuttals) + list(extra_rebuttals)

    if adversarial:
        # Misleading: metadata says bull_supported/strong, but open evidence_insufficient remains
        challenges.append(
            Challenge(
                challenge_id="CH_ADV_01",
                challenger="bear",
                target_claim_id="BULL_01",
                challenge_type="evidence_insufficient",
                argument="所谓『已经证明恢复』缺乏多期可核对证据。",
                evidence_ids=eids[:1] or ["e1"],
                strength=0.95,
            )
        )
        rebuttals.append(
            Rebuttal(
                rebuttal_id="RB_ADV_01",
                author="bull",
                target_challenge_id="CH_ADV_01",
                response_type="partially_accept",
                argument="承认缺少多期确认，但仍主张建设性解释。",
                evidence_ids=eids[:1] or ["e1"],
            )
        )
        unresolved = ["对抗性 Debate：恢复主张缺少多期证据，不得写成已证明"]

    return DebateResult(
        stock_code=stock,
        bull=bull,
        bear=bear,
        challenges=challenges,
        rebuttals=rebuttals,
        evidence_weights=[],
        debate_summary=DebateSummary(
            shared_facts=["live fixture shared fact"],
            core_disagreements=["阶段性 vs 结构性"],
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
            "live_fixture": True,
            "adversarial": adversarial,
        },
    )


def _mutate_primary_claim(fund, claim: str, numbers: list[str]):
    cans = []
    for c in fund.canonical_findings:
        if "PROFIT_VS_GROWTH" in c.finding_id:
            cans.append(c.model_copy(update={"claim": claim, "numbers_preserved": numbers}))
        else:
            cans.append(c)
    return fund.model_copy(update={"canonical_findings": cans})


def build_live_fixtures(root: Path | None = None) -> list[LiveFixture]:
    root = root or Path(__file__).resolve().parents[2]
    pack = EvidencePack.load_json(root / "examples" / "600519_evidence_pack.json")
    fund = synthesize_fundamental(pack.stock_code, build_fundamental_context(pack))
    market = synthesize_market(pack.stock_code, build_market_context(pack))
    tension = next(c for c in fund.canonical_findings if "PROFIT_VS_GROWTH" in c.finding_id)
    eids = list(tension.evidence_ids)[:3]
    tid = tension.finding_id

    fixtures: list[LiveFixture] = []

    # A unresolved
    fixtures.append(
        LiveFixture(
            fixture_id="A_unresolved",
            title="Unresolved primary tension",
            intent="保留阶段性 vs 结构性未决；OpenAI 不得消灭 uncertainty",
            inp=build_final_analyst_input(
                fundamental=fund,
                market=market,
                debate=_debate(
                    stock=pack.stock_code,
                    tension_id=tid,
                    force_resolution="unresolved",
                    force_strength="unresolved",
                    eids=eids,
                ),
                mode="openai",
            ),
        )
    )

    # B bull moderate
    fixtures.append(
        LiveFixture(
            fixture_id="B_bull_moderate",
            title="Bull supported moderate",
            intent="建设性解释可更明确，但仍条件化",
            inp=build_final_analyst_input(
                fundamental=fund,
                market=market,
                debate=_debate(
                    stock=pack.stock_code,
                    tension_id=tid,
                    force_resolution="bull_supported",
                    force_strength="moderate",
                    eids=eids,
                ),
                mode="openai",
            ),
        )
    )

    # C bear moderate
    fixtures.append(
        LiveFixture(
            fixture_id="C_bear_moderate",
            title="Bear supported moderate",
            intent="谨慎解释可更明确，不得写成增长逻辑已经失效",
            inp=build_final_analyst_input(
                fundamental=fund,
                market=market,
                debate=_debate(
                    stock=pack.stock_code,
                    tension_id=tid,
                    force_resolution="bear_supported",
                    force_strength="moderate",
                    eids=eids,
                ),
                mode="openai",
            ),
        )
    )

    # D bull strong + limiting challenge
    lim_ch = Challenge(
        challenge_id="CH_LIMIT_01",
        challenger="bear",
        target_claim_id="BULL_01",
        challenge_type="evidence_insufficient",
        argument="即便 Bull 侧解释占优，仍缺多期增长恢复的可核对证据。",
        evidence_ids=eids[:1] or ["e1"],
        strength=0.9,
    )
    lim_rb = Rebuttal(
        rebuttal_id="RB_LIMIT_01",
        author="bull",
        target_challenge_id="CH_LIMIT_01",
        response_type="partially_accept",
        argument="接受恢复尚未被多期确认；主张的是解释权重而非已发生恢复。",
        evidence_ids=eids[:1] or ["e1"],
    )
    fixtures.append(
        LiveFixture(
            fixture_id="D_bull_strong_limiting",
            title="Bull strong with limiting challenge",
            intent="strong ≠ certainty；必须保留 limiting challenge 约束",
            inp=build_final_analyst_input(
                fundamental=fund,
                market=market,
                debate=_debate(
                    stock=pack.stock_code,
                    tension_id=tid,
                    force_resolution="bull_supported",
                    force_strength="strong",
                    eids=eids,
                    extra_challenges=[lim_ch],
                    extra_rebuttals=[lim_rb],
                    unresolved_issues=["增长恢复缺少多期确认"],
                ),
                mode="openai",
            ),
        )
    )

    # E dual tension — full fund+market, unresolved-ish real structure forced dual via bull on profit
    # Use real-like unresolved debate but keep both fund and market contracts intact
    fixtures.append(
        LiveFixture(
            fixture_id="E_dual_tension",
            title="Fundamental + Market dual tension",
            intent="要求 cross-tension：经营×估值×价格，而非三条并列总结",
            inp=build_final_analyst_input(
                fundamental=fund,
                market=market,
                debate=_debate(
                    stock=pack.stock_code,
                    tension_id=tid,
                    force_resolution="unresolved",
                    force_strength="tentative",
                    eids=eids,
                    unresolved_issues=[
                        "阶段性 vs 结构性未决",
                        "短期价格改善能否验证基本面争议仍未决",
                    ],
                ),
                mode="openai",
            ),
        )
    )

    # F adversarial / misleading Debate
    fund_sev = _mutate_primary_claim(
        fund,
        claim=(
            "ROE 高但增长明显恶化、现金流同步恶化："
            "不得因误导性 Debate 写成已经恢复。"
            "既有数字仍为 33.65%、4.53%、1.21%，压力来自关系解读而非新造数字。"
        ),
        numbers=["33.65%", "4.53%", "1.21%"],
    )
    fixtures.append(
        LiveFixture(
            fixture_id="F_adversarial_debate",
            title="Adversarial misleading Debate",
            intent="metadata bull_supported/strong 但挑战未解除；FA 不得跟随误导性 overclaim",
            inp=build_final_analyst_input(
                fundamental=fund_sev,
                market=market,
                debate=_debate(
                    stock=pack.stock_code,
                    tension_id=tid,
                    force_resolution="bull_supported",
                    force_strength="strong",
                    eids=eids,
                    adversarial=True,
                ),
                mode="openai",
            ),
        )
    )

    return fixtures
