"""Offline grounded synthesizer for Bull/Bear/Challenge/Rebuttal (no network)."""

from __future__ import annotations

from typing import Any

from evidence.pack import EvidencePack
from research.schemas import FundamentalResearch, MarketResearch

from debate.context import first_by_subtype
from debate.schemas import (
    BearResearch,
    BullResearch,
    Challenge,
    DebateSummary,
    Rebuttal,
    ResearchClaim,
)


def _ids(*items) -> list[str]:
    out = []
    for e in items:
        if e is not None:
            out.append(e.evidence_id)
    return out


def synthesize_bull(
    pack: EvidencePack,
    fundamental: FundamentalResearch,
    market: MarketResearch,
) -> BullResearch:
    roe = first_by_subtype(pack, "roe")
    gm = first_by_subtype(pack, "gross_margin")
    ocf = first_by_subtype(pack, "ocf_to_net_profit")
    ocf_raw = first_by_subtype(pack, "operating_cash_flow")
    debt = first_by_subtype(pack, "debt_to_asset_ratio")
    ma5 = first_by_subtype(pack, "ma5")
    ma20 = first_by_subtype(pack, "ma20")
    ma60 = first_by_subtype(pack, "ma60")
    pos = first_by_subtype(pack, "price_position_in_52w_range")
    eps = first_by_subtype(pack, "eps_consensus")
    np_yoy = first_by_subtype(pack, "net_profit_yoy")

    # Prefer Research canonical tensions as stance anchors (do not re-author research facts)
    profit_tension = next(
        (c for c in fundamental.canonical_findings if "PROFIT_VS_GROWTH" in (c.finding_id or "")),
        None,
    )

    claims: list[ResearchClaim] = []

    if roe or gm:
        eids = _ids(roe, gm)
        if np_yoy:
            eids = _ids(roe, gm, np_yoy)
        reasoning = (
            "Fundamental Research 与 DERIVED 指标显示高 ROE / 高毛利率并存；"
            "这支持“盈利质量仍强”的解释，而非股价必然上涨。"
        )
        if np_yoy:
            reasoning += f" 同时需承认：{np_yoy.claim} 表明短期利润增速承压。"
        if profit_tension:
            reasoning += f" 立场对齐 Research canonical `{profit_tension.finding_id}`（不重复生成同义研究结论）。"
        claims.append(
            ResearchClaim(
                claim_id="BULL_01",
                stance="bull",
                claim="公司盈利能力仍具有较强韧性，资本回报与毛利率水平提供支持性证据。",
                reasoning=reasoning,
                evidence_ids=eids or _ids(roe or gm),
                confidence=0.82,
                importance=0.95,
                canonical_finding_ids=[profit_tension.finding_id] if profit_tension else [],
            )
        )

    if ocf or ocf_raw or debt:
        cash_c = next(
            (c for c in fundamental.canonical_findings if "CASH_QUALITY" in (c.finding_id or "")),
            None,
        )
        claims.append(
            ResearchClaim(
                claim_id="BULL_02",
                stance="bull",
                claim="财务健康与现金流证据支持公司基本面具备抗风险缓冲。",
                reasoning=(
                    "经营现金流及相关比率、资产负债结构可被解释为基本面缓冲；"
                    "Bull Case 将其视为投资价值的支持性事实，同时不否认增速放缓风险。"
                ),
                evidence_ids=_ids(ocf, ocf_raw, debt),
                confidence=0.74,
                importance=0.8,
                canonical_finding_ids=[cash_c.finding_id] if cash_c else [],
            )
        )

    short_long = next(
        (c for c in market.canonical_findings if "SHORT_VS_LONG" in (c.finding_id or "")),
        None,
    )
    if (ma5 and ma20 and ma60) or pos or eps:
        claims.append(
            ResearchClaim(
                claim_id="BULL_03",
                stance="bull",
                claim="短中期价格结构与一致预期快照提供偏积极的市场侧支持线索。",
                reasoning=(
                    "Market Research 中的均线结构/52周位置/一致预期属于可引用证据；"
                    "可解释为短中期动能与机构预期仍存，但不能外推为确定性上涨。"
                ),
                evidence_ids=_ids(ma5, ma20, ma60, pos, eps)[:5],
                confidence=0.68,
                importance=0.7,
                canonical_finding_ids=[short_long.finding_id] if short_long else [],
            )
        )

    claims = claims[:3]
    if not claims:
        # Should be rare; still require evidence — use any available fact
        name = first_by_subtype(pack, "stock_name")
        if not name and pack.evidence:
            name = pack.evidence[0]
        claims = [
            ResearchClaim(
                claim_id="BULL_01",
                stance="bull",
                claim="当前 Evidence 不足以构建强 Bull Case，仅能确认公司身份信息存在。",
                reasoning="insufficient_evidence：缺少盈利能力/现金流/市场结构等核心支持证据。",
                evidence_ids=[name.evidence_id] if name else [pack.evidence[0].evidence_id],
                confidence=0.4,
                importance=0.5,
            )
        ]

    risks = []
    if np_yoy:
        risks.append(f"负面证据需承认：{np_yoy.claim}")
    rev_yoy = first_by_subtype(pack, "revenue_yoy")
    if rev_yoy:
        risks.append(f"营收增速风险：{rev_yoy.claim}")
    ma250 = first_by_subtype(pack, "ma250")
    if ma250:
        risks.append(f"长期均线压力线索：{ma250.claim}")

    unc_texts: list[str] = []
    for u in fundamental.key_uncertainties:
        if getattr(u, "status", None) == "insufficient_evidence" or "insufficient" in (u.claim or ""):
            unc_texts.append(u.claim)
    if not unc_texts:
        unc_texts = ["客户结构等关键商业细节在 Evidence Pack 中不足。"]
    unc_texts.append("短期增速承压是否阶段性，现有 Evidence 无法单独裁定。")

    thesis = (
        "基于相同 Evidence，Bull Case 强调高盈利韧性与财务缓冲，并承认利润同比下滑等负面事实；"
        "立场差异来自 interpretation，而非新造数据。"
    )
    return BullResearch(
        stock_code=pack.stock_code,
        thesis=thesis,
        claims=claims,
        key_risks=risks,
        uncertainties=unc_texts[:4],
    )


def synthesize_bear(
    pack: EvidencePack,
    fundamental: FundamentalResearch,
    market: MarketResearch,
) -> BearResearch:
    np_yoy = first_by_subtype(pack, "net_profit_yoy")
    rev_yoy = first_by_subtype(pack, "revenue_yoy")
    np_ = first_by_subtype(pack, "net_profit_parent")
    rev = first_by_subtype(pack, "operating_revenue")
    ma250 = first_by_subtype(pack, "ma250")
    close = first_by_subtype(pack, "close_price")
    pos = first_by_subtype(pack, "price_position_in_52w_range")
    roe = first_by_subtype(pack, "roe")
    gm = first_by_subtype(pack, "gross_margin")
    rsi = first_by_subtype(pack, "rsi_14")

    claims: list[ResearchClaim] = []

    profit_tension = next(
        (c for c in fundamental.canonical_findings if "PROFIT_VS_GROWTH" in (c.finding_id or "")),
        None,
    )

    if np_yoy or rev_yoy:
        eids = _ids(np_yoy, rev_yoy, np_, rev)[:4]
        if roe and roe.evidence_id not in eids:
            eids = (eids + [roe.evidence_id])[:5]
        reasoning = (
            "归母净利润/营收同比下滑是可核验负面事实；"
            "Bear Case 将其解释为盈利动能恶化信号。"
        )
        if roe:
            reasoning += f" 同时承认：{roe.claim} 显示静态盈利能力仍高。"
        if profit_tension:
            reasoning += f" 风险解读对齐 Research canonical `{profit_tension.finding_id}`（引用张力，不复制全文）。"
        claims.append(
            ResearchClaim(
                claim_id="BEAR_01",
                stance="bear",
                claim="盈利与收入增速承压，削弱“增长驱动”的投资价值叙事。",
                reasoning=reasoning,
                evidence_ids=eids,
                confidence=0.84,
                importance=0.95,
                canonical_finding_ids=[profit_tension.finding_id] if profit_tension else [],
            )
        )

    short_long = next(
        (c for c in market.canonical_findings if "SHORT_VS_LONG" in (c.finding_id or "")),
        None,
    )
    if ma250 or close or pos:
        claims.append(
            ResearchClaim(
                claim_id="BEAR_02",
                stance="bear",
                claim="价格相对长期均线与区间位置显示中期上行仍面临结构压力。",
                reasoning=(
                    "若价格位于长期均线下方或仅处52周中部，可解释为趋势尚未确认强势突破；"
                    "这是对市场结构的风险解读，不是买卖指令。"
                ),
                evidence_ids=_ids(ma250, close, pos),
                confidence=0.72,
                importance=0.78,
                canonical_finding_ids=[short_long.finding_id] if short_long else [],
            )
        )

    # Third claim: expectation uncertainty / event risk / valuation
    pe = first_by_subtype(pack, "pe")
    eps = first_by_subtype(pack, "eps_consensus")
    val_tension = next(
        (c for c in fundamental.canonical_findings if "VALUATION_VS_GROWTH" in (c.finding_id or "")),
        None,
    )
    events = [e for e in pack.evidence if e.subtype in {"announcement", "shareholder_change", "market_news"}][:2]
    if pe or eps or events:
        eids = _ids(pe, eps) + [e.evidence_id for e in events]
        claims.append(
            ResearchClaim(
                claim_id="BEAR_03",
                stance="bear",
                claim="估值与一致预期/事件证据不足以支撑“风险已被充分消化”的乐观假设。",
                reasoning=(
                    "PE 等估值事实与 EXPECTATION/EVENT 仅提供快照；"
                    "Bear Case 强调：在增速承压背景下，乐观定价假设证据不足。"
                    + (f" 同时承认 Bull 可能成立的部分：{gm.claim}" if gm else "")
                ),
                evidence_ids=eids[:5],
                confidence=0.66,
                importance=0.7,
                canonical_finding_ids=[val_tension.finding_id] if val_tension else [],
            )
        )

    claims = claims[:3]
    if not claims:
        name = first_by_subtype(pack, "stock_name") or pack.evidence[0]
        claims = [
            ResearchClaim(
                claim_id="BEAR_01",
                stance="bear",
                claim="当前 Evidence 不足以构建强 Bear Case。",
                reasoning="insufficient_evidence：缺少增速/估值/长期趋势等风险证据。",
                evidence_ids=[name.evidence_id],
                confidence=0.4,
                importance=0.5,
            )
        ]

    opportunities = []
    if roe:
        opportunities.append(f"Bull 可能成立：{roe.claim}")
    if gm:
        opportunities.append(f"Bull 可能成立：{gm.claim}")
    if first_by_subtype(pack, "ma5") and first_by_subtype(pack, "ma20"):
        opportunities.append("短中期均线结构可能被解释为偏积极动能（Market Research）。")

    uncertainties = [
        "利润同比下滑是否阶段性，现有单期 Evidence 无法确认长期恶化。",
        "客户结构与管理层指引在 Evidence Pack 中不足，限制空头因果链条完整性。",
    ]
    if rsi:
        uncertainties.append(f"动量指标解读不稳定：{rsi.claim}")

    thesis = (
        "基于相同 Evidence，Bear Case 强调增速承压与长期价格结构压力，并承认高 ROE/高毛利率等支持性事实；"
        "分歧在 interpretation，不在事实本身。"
    )
    return BearResearch(
        stock_code=pack.stock_code,
        thesis=thesis,
        claims=claims,
        key_opportunities=opportunities,
        uncertainties=uncertainties,
    )


def synthesize_bull_challenges(
    pack: EvidencePack,
    bull: BullResearch,
    bear: BearResearch,
) -> list[Challenge]:
    """Bull challenges Bear claims."""
    out: list[Challenge] = []
    roe = first_by_subtype(pack, "roe")
    gm = first_by_subtype(pack, "gross_margin")
    ma5 = first_by_subtype(pack, "ma5")
    ma20 = first_by_subtype(pack, "ma20")
    ma60 = first_by_subtype(pack, "ma60")

    for i, bc in enumerate(bear.claims, start=1):
        if bc.claim_id == "BEAR_01":
            out.append(
                Challenge(
                    challenge_id=f"CH_BULL_{i:02d}",
                    challenger="bull",
                    target_claim_id=bc.claim_id,
                    challenge_type="interpretation_conflict",
                    argument=(
                        "同比下滑证明短期增长承压，但不能单独证明长期盈利能力已经系统性恶化；"
                        "高 ROE/高毛利率仍是并存事实，Bear 将单期增速外推为趋势恶化存在过度解读风险。"
                    ),
                    evidence_ids=_ids(roe, gm) + bc.evidence_ids[:1],
                    strength=0.78,
                )
            )
        elif bc.claim_id == "BEAR_02":
            out.append(
                Challenge(
                    challenge_id=f"CH_BULL_{i:02d}",
                    challenger="bull",
                    target_claim_id=bc.claim_id,
                    challenge_type="time_sensitivity",
                    argument=(
                        "长期均线压力属于中长期结构描述；短中期均线若呈多头排列，"
                        "则“全面趋势转弱”的结论在时间尺度上可能过宽。"
                    ),
                    evidence_ids=_ids(ma5, ma20, ma60) + bc.evidence_ids[:1],
                    strength=0.7,
                )
            )
        else:
            out.append(
                Challenge(
                    challenge_id=f"CH_BULL_{i:02d}",
                    challenger="bull",
                    target_claim_id=bc.claim_id,
                    challenge_type="assumption",
                    argument=(
                        "“风险未被消化”是假设性判断；估值与一致预期证据只能说明快照状态，"
                        "不足以单独证伪缓冲能力，证据对空头结论的充分性不足。"
                    ),
                    evidence_ids=bc.evidence_ids[:2] or _ids(roe),
                    strength=0.62,
                )
            )
    return out


def synthesize_bear_challenges(
    pack: EvidencePack,
    bull: BullResearch,
    bear: BearResearch,
) -> list[Challenge]:
    """Bear challenges Bull claims."""
    out: list[Challenge] = []
    np_yoy = first_by_subtype(pack, "net_profit_yoy")
    rev_yoy = first_by_subtype(pack, "revenue_yoy")
    ma250 = first_by_subtype(pack, "ma250")
    close = first_by_subtype(pack, "close_price")

    for i, bc in enumerate(bull.claims, start=1):
        if bc.claim_id == "BULL_01":
            out.append(
                Challenge(
                    challenge_id=f"CH_BEAR_{i:02d}",
                    challenger="bear",
                    target_claim_id=bc.claim_id,
                    challenge_type="interpretation_conflict",
                    argument=(
                        "ROE/毛利率较高能够证明当前盈利能力较强，"
                        "但不能单独证明盈利增长趋势已经改善；"
                        + (f"与 {np_yoy.claim} 并存时，‘韧性’解释存在 interpretation conflict。" if np_yoy else "增长趋势证据不足。")
                    ),
                    evidence_ids=_ids(np_yoy, rev_yoy) + bc.evidence_ids[:1],
                    strength=0.8,
                )
            )
        elif bc.claim_id == "BULL_02":
            out.append(
                Challenge(
                    challenge_id=f"CH_BEAR_{i:02d}",
                    challenger="bear",
                    target_claim_id=bc.claim_id,
                    challenge_type="scope",
                    argument=(
                        "财务健康与现金流缓冲不能自动覆盖增长放缓对投资叙事的冲击；"
                        "Bull 将‘抗风险缓冲’扩展为投资价值支持，存在范围外推。"
                    ),
                    evidence_ids=_ids(np_yoy) + bc.evidence_ids[:2],
                    strength=0.68,
                )
            )
        else:
            out.append(
                Challenge(
                    challenge_id=f"CH_BEAR_{i:02d}",
                    challenger="bear",
                    target_claim_id=bc.claim_id,
                    challenge_type="evidence_insufficient",
                    argument=(
                        "短中期均线/一致预期支持偏积极解读，但相对长期均线的压力证据未被充分纳入；"
                        "Bull Case 对市场结构的取证范围可能不完整。"
                    ),
                    evidence_ids=_ids(ma250, close) + bc.evidence_ids[:1],
                    strength=0.72,
                )
            )
    return out


def synthesize_rebuttals(
    pack: EvidencePack,
    bull: BullResearch,
    bear: BearResearch,
    challenges: list[Challenge],
) -> list[Rebuttal]:
    """Authors rebut challenges against their own claims."""
    claim_owner = {c.claim_id: "bull" for c in bull.claims}
    claim_owner.update({c.claim_id: "bear" for c in bear.claims})
    claims_by_id = {c.claim_id: c for c in bull.claims + bear.claims}

    np_yoy = first_by_subtype(pack, "net_profit_yoy")
    roe = first_by_subtype(pack, "roe")
    gm = first_by_subtype(pack, "gross_margin")
    ma250 = first_by_subtype(pack, "ma250")
    ma5 = first_by_subtype(pack, "ma5")

    out: list[Rebuttal] = []
    for i, ch in enumerate(challenges, start=1):
        owner = claim_owner.get(ch.target_claim_id)
        if owner is None:
            continue
        target = claims_by_id[ch.target_claim_id]
        if owner == "bull":
            # Bull rebuts Bear challenges
            if ch.challenge_type == "interpretation_conflict":
                resp = "partially_accept"
                arg = (
                    "接受‘高 ROE 不等于增长已改善’的边界；"
                    "但坚持：在相同 Evidence 下，盈利韧性与增速承压可以并存，"
                    "Bull Claim 强调的是能力水平而非已改善的增长趋势。"
                )
                eids = _ids(roe, gm, np_yoy)
            elif ch.challenge_type == "evidence_insufficient":
                resp = "partially_accept"
                arg = (
                    "接受长期均线应被纳入完整市场结构讨论；"
                    "同时指出短中期结构证据仍然有效，缺失的是‘综合权重’，不是事实虚造。"
                )
                eids = _ids(ma5, ma250) + target.evidence_ids[:1]
            else:
                resp = "reject"
                arg = (
                    "现金流/财务缓冲与增长叙事属于不同分析维度；"
                    "Bull 未声称缓冲可替代增长，仅主张其构成支持性条件之一。"
                )
                eids = target.evidence_ids[:2]
            out.append(
                Rebuttal(
                    rebuttal_id=f"RB_BULL_{i:02d}",
                    author="bull",
                    target_challenge_id=ch.challenge_id,
                    response_type=resp,  # type: ignore[arg-type]
                    argument=arg,
                    evidence_ids=eids or target.evidence_ids[:1],
                )
            )
        else:
            # Bear rebuts Bull challenges
            if ch.challenge_type == "interpretation_conflict":
                resp = "partially_accept"
                arg = (
                    "接受单期增速不能单独证明‘永久性恶化’；"
                    "但坚持：在增长证据转弱时，将高 ROE 解释为已对冲增长风险，证据并不充分。"
                )
                eids = _ids(np_yoy, roe)
            elif ch.challenge_type == "time_sensitivity":
                resp = "accept"
                arg = (
                    "接受时间尺度区分：短中期与长期结构应分开陈述；"
                    "Bear Claim 可收窄为‘长期结构压力仍在’，而非否认短中期动能证据。"
                )
                eids = _ids(ma250, ma5)
            else:
                resp = "partially_accept"
                arg = (
                    "接受‘风险未被消化’含假设成分；"
                    "因此将该点降级为 uncertainties，而非已证伪的事实。"
                )
                eids = target.evidence_ids[:2]
            out.append(
                Rebuttal(
                    rebuttal_id=f"RB_BEAR_{i:02d}",
                    author="bear",
                    target_challenge_id=ch.challenge_id,
                    response_type=resp,  # type: ignore[arg-type]
                    argument=arg,
                    evidence_ids=eids or target.evidence_ids[:1],
                )
            )
    return out


def synthesize_debate_summary(
    pack: EvidencePack,
    bull: BullResearch,
    bear: BearResearch,
    challenges: list[Challenge],
) -> DebateSummary:
    shared = []
    for subtype, label in [
        ("roe", "ROE"),
        ("gross_margin", "毛利率"),
        ("net_profit_yoy", "归母净利润同比"),
        ("revenue_yoy", "营收同比"),
        ("close_price", "最新价格"),
        ("ma250", "MA250"),
    ]:
        e = first_by_subtype(pack, subtype)
        if e:
            shared.append(e.claim)

    disagreements = []
    for ch in challenges:
        if ch.challenge_type == "interpretation_conflict":
            disagreements.append(
                f"{ch.challenger} vs claim {ch.target_claim_id}: interpretation_conflict — {ch.argument[:120]}"
            )
    if not disagreements:
        disagreements.append("双方对增长承压事实的解释方向不同（interpretation_conflict）。")

    unresolved = [
        "单期利润下滑是否阶段性，现有 Evidence 无法裁定。",
        "高盈利能力与低增长并存时，投资叙事权重如何分配，留给 Final Analyst。",
        "客户结构、管理层指引等关键商业细节仍不足。",
    ]
    # merge agent uncertainties (strings)
    unresolved.extend([u for u in bull.uncertainties[:1] + bear.uncertainties[:1]])

    return DebateSummary(
        shared_facts=shared[:8],
        core_disagreements=disagreements[:6],
        unresolved_issues=unresolved[:6],
    )
