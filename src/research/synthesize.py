"""Deterministic research synthesis: canonical findings + compatibility stubs.

Preserves key numbers in claims. Avoids cloning the same research proposition
across sections. Does not force cross when evidence is insufficient.
"""

from __future__ import annotations

import re
from typing import Any

from research.citation import extract_fact_tokens
from research.schemas import (
    CanonicalFinding,
    CitedFinding,
    EvidenceCitation,
    ExcludedAuditItem,
    FundamentalResearch,
    MarketResearch,
    ResearchSection,
)
from research.selection import select_by_weight


def _excluded(payload: dict[str, Any]) -> list[ExcludedAuditItem]:
    rows = []
    for item in payload.get("excluded_audit") or []:
        try:
            rows.append(ExcludedAuditItem.model_validate(item))
        except Exception:
            continue
    return rows


def _bundle_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {b["bundle"]: b for b in (payload.get("cross_evidence_bundles") or []) if b.get("bundle")}


def _num_phrase(row: dict[str, Any]) -> str:
    """Prefer concise number snippet from claim."""
    claim = str(row.get("claim") or "")
    tokens = extract_fact_tokens(claim)
    # Keep claim as authoritative number-bearing text (already audited)
    return claim


def _ids(rows: list[dict[str, Any]]) -> list[str]:
    return [str(r["evidence_id"]) for r in rows]


def _numbers(rows: list[dict[str, Any]]) -> list[str]:
    nums: list[str] = []
    for r in rows:
        for t in extract_fact_tokens(str(r.get("claim") or "")):
            if t not in nums:
                nums.append(t)
    return nums


def _by_sub(rows: list[dict[str, Any]], subtype: str) -> dict[str, Any] | None:
    matched = [r for r in rows if r.get("subtype") == subtype]
    picked = select_by_weight(matched, n=1)
    return picked[0] if picked else None


def _ref(c: CanonicalFinding) -> CitedFinding:
    return CitedFinding(
        claim=f"[ref:{c.finding_id}] {c.research_question}",
        evidence_ids=list(c.evidence_ids),
        reasoning=f"reference → {c.finding_id}",
        interpretation="详见 canonical_findings；本节不重复同一研究命题全文。",
        confidence=c.confidence,
        status="supported",
        finding_kind="reference",
        ref_finding_id=c.finding_id,
    )


def _gap(topic: str) -> CitedFinding:
    return CitedFinding(
        claim=f"当前 Research Context 缺少足够的{topic}证据，无法形成可靠判断。",
        evidence_ids=[],
        reasoning="insufficient_evidence",
        interpretation="insufficient_evidence",
        confidence=0.9,
        status="insufficient_evidence",
        finding_kind="insufficient",
    )


def _section_ref(narrative: str, canonicals: list[CanonicalFinding], gaps: list[str] | None = None) -> ResearchSection:
    findings = [_ref(c) for c in canonicals]
    if not findings and gaps:
        findings = [_gap(g) for g in gaps]
    return ResearchSection(narrative=narrative, findings=findings, insufficient_topics=gaps or [])


def _citations(findings: list[CitedFinding], idx: dict[str, dict[str, Any]]) -> list[EvidenceCitation]:
    out: list[EvidenceCitation] = []
    for f in findings:
        if f.status != "supported" or not f.evidence_ids:
            continue
        if f.finding_kind == "reference":
            continue
        sources = []
        for eid in f.evidence_ids:
            e = idx.get(eid)
            if not e:
                continue
            t = e.get("time") or {}
            src = e.get("source") or {}
            sources.append(
                {
                    "evidence_id": eid,
                    "provider": src.get("provider"),
                    "url": src.get("url"),
                    "date": e.get("event_time")
                    or t.get("published_at")
                    or t.get("report_date")
                    or t.get("data_date"),
                    "claim": e.get("claim"),
                }
            )
        out.append(EvidenceCitation(statement=f.claim, evidence_ids=list(f.evidence_ids), sources=sources))
    return out


def _index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for items in (payload.get("evidence_groups") or {}).values():
        for e in items or []:
            if e.get("evidence_id"):
                idx[str(e["evidence_id"])] = e
    return idx


def _build_profitability_growth(b: dict[str, Any]) -> CanonicalFinding | CitedFinding:
    q = b.get("research_question") or "盈利能力与增长动能关系"
    if b.get("status") != "ready":
        return _gap("盈利能力×增长对照")
    rows = list(b.get("selected") or [])
    roe = _by_sub(rows, "roe")
    gm = _by_sub(rows, "gross_margin")
    npy = _by_sub(rows, "net_profit_yoy")
    rvy = _by_sub(rows, "revenue_yoy")
    profit_side = [x for x in [roe, gm] if x]
    growth_side = [x for x in [npy, rvy] if x]
    if len(profit_side) < 1 or len(growth_side) < 1:
        return _gap("盈利能力×增长对照")
    used = profit_side + growth_side
    # Dynamic claim with preserved numbers
    profit_bits = "、".join(_num_phrase(x) for x in profit_side)
    growth_bits = "、".join(_num_phrase(x) for x in growth_side)
    claim = (
        f"{profit_bits}；同时 {growth_bits}。"
        f"这表明盈利能力仍处较高水平，但增长端已出现压力，"
        f"基本面主要矛盾在增长动能而非盈利能力本身。"
    )
    interp = (
        "现有证据可以支持“盈利能力仍强、增长承压”的分化判断；"
        "但单期同比不足以判定是短期波动还是结构性问题，需后续验证需求、渠道与管理层指引。"
    )
    return CanonicalFinding(
        finding_id="TENSION_FUND_PROFIT_VS_GROWTH",
        research_question=q,
        claim=claim,
        evidence_ids=_ids(used),
        reasoning="候选证据经 weight 选择后对照盈利能力指标与增长指标。",
        interpretation=interp,
        confidence=0.84,
        status="supported",
        finding_kind="tension",
        numbers_preserved=_numbers(used),
    )


def _build_cash_quality(b: dict[str, Any]) -> CanonicalFinding | CitedFinding:
    q = b.get("research_question") or "利润质量与现金流"
    if b.get("status") != "ready":
        return _gap("现金流×利润质量")
    rows = list(b.get("selected") or [])
    ocf_r = _by_sub(rows, "ocf_to_net_profit")
    ocf = _by_sub(rows, "operating_cash_flow")
    np_ = _by_sub(rows, "net_profit_parent")
    cash_side = [x for x in [ocf_r, ocf] if x]
    earn_side = [x for x in [np_] if x]
    if not cash_side or not earn_side:
        return _gap("现金流×利润质量")
    used = cash_side + earn_side
    claim = (
        f"{'；'.join(_num_phrase(x) for x in used)}。"
        f"经营现金流与净利润对照后，利润质量需要用现金含量来约束，而不能只看利润表结果。"
    )
    return CanonicalFinding(
        finding_id="FINDING_FUND_CASH_QUALITY",
        research_question=q,
        claim=claim,
        evidence_ids=_ids(used),
        reasoning="在同一研究问题下联合经营现金流与净利润证据。",
        interpretation="若现金含量稳定，则利润表波动的说服力更强；反之需提高对利润质量的警惕。边界：未覆盖完整多期趋势时不作趋势定论。",
        confidence=0.78,
        status="supported",
        finding_kind="cross",
        numbers_preserved=_numbers(used),
    )


def _build_balance_op(b: dict[str, Any]) -> CanonicalFinding | CitedFinding:
    q = b.get("research_question") or "财务缓冲与经营规模"
    if b.get("status") != "ready":
        return _gap("资产负债表×经营风险")
    rows = list(b.get("selected") or [])
    debt = _by_sub(rows, "debt_to_asset_ratio")
    cash = _by_sub(rows, "cash_and_equivalents")
    rev = _by_sub(rows, "operating_revenue")
    np_ = _by_sub(rows, "net_profit_parent")
    bs = [x for x in [debt, cash] if x]
    op = [x for x in [rev, np_] if x]
    if not bs or not op:
        return _gap("资产负债表×经营风险")
    used = bs + op
    claim = (
        f"{'；'.join(_num_phrase(x) for x in used)}。"
        f"杠杆/流动性指标需对照经营规模理解：财务缓冲提供风险约束，但不能单独替代增长判断。"
    )
    return CanonicalFinding(
        finding_id="FINDING_FUND_BALANCE_OP",
        research_question=q,
        claim=claim,
        evidence_ids=_ids(used),
        reasoning="资产负债表与经营结果共同约束风险判断。",
        interpretation="财务健康是缓冲维度；与增长压力并存时，二者回答不同问题。",
        confidence=0.74,
        status="supported",
        finding_kind="cross",
        numbers_preserved=_numbers(used),
    )


def _build_valuation_growth(b: dict[str, Any]) -> CanonicalFinding | CitedFinding:
    q = b.get("research_question") or "估值与增长假设"
    if b.get("status") != "ready":
        return _gap("估值×盈利/增长")
    rows = list(b.get("selected") or [])
    pe = _by_sub(rows, "pe")
    pb = _by_sub(rows, "pb")
    roe = _by_sub(rows, "roe")
    npy = _by_sub(rows, "net_profit_yoy")
    rvy = _by_sub(rows, "revenue_yoy")
    val = [x for x in [pe, pb] if x]
    fund = [x for x in [roe, npy, rvy] if x]
    if not val or not fund:
        return _gap("估值×盈利/增长")
    used = val + fund
    claim = (
        f"{'；'.join(_num_phrase(x) for x in used)}。"
        f"估值属于 as_of 市场截面，盈利/增速属于财报期；若增长承压而盈利能力仍高，"
        f"则估值合理性更依赖未来增长恢复，而不能仅由历史盈利能力解释。"
    )
    return CanonicalFinding(
        finding_id="TENSION_FUND_VALUATION_VS_GROWTH",
        research_question=q,
        claim=claim,
        evidence_ids=_ids(used),
        reasoning="跨时间尺度：估值截面 × 财务期盈利/增长。",
        interpretation="这是条件判断而非买卖建议；证据不足以给出目标估值。",
        confidence=0.72,
        status="supported",
        finding_kind="tension",
        numbers_preserved=_numbers(used),
    )


def _build_price_ma(b: dict[str, Any]) -> CanonicalFinding | CitedFinding:
    q = b.get("research_question") or "价格与均线结构"
    if b.get("status") != "ready":
        return _gap("价格×均线")
    rows = list(b.get("selected") or [])
    close = _by_sub(rows, "close_price")
    ma5 = _by_sub(rows, "ma5")
    ma20 = _by_sub(rows, "ma20")
    ma60 = _by_sub(rows, "ma60")
    ma250 = _by_sub(rows, "ma250")
    used = [x for x in [close, ma5, ma20, ma60, ma250] if x]
    if not close or len(used) < 2:
        return _gap("价格×均线")
    structure = "均线与价格关系可观测"
    try:
        if ma5 and ma20 and ma60:
            v5 = float((ma5.get("value") or {}).get("value"))
            v20 = float((ma20.get("value") or {}).get("value"))
            v60 = float((ma60.get("value") or {}).get("value"))
            if v5 > v20 > v60:
                structure = "短中期均线呈多头排列"
            elif v5 < v20 < v60:
                structure = "短中期均线呈空头排列"
            else:
                structure = "短中期均线结构交织"
    except Exception:
        pass
    claim = (
        f"{'；'.join(_num_phrase(x) for x in used)}。"
        f"对照结果显示{structure}；价格相对均线的位置需分短中长期解读，不等于趋势预测。"
    )
    return CanonicalFinding(
        finding_id="FINDING_MKT_PRICE_MA",
        research_question=q,
        claim=claim,
        evidence_ids=_ids(used),
        reasoning="价格与均线在同一 as_of 截面对照。",
        interpretation="描述状态，不给出交易指令。",
        confidence=0.8,
        status="supported",
        finding_kind="cross",
        numbers_preserved=_numbers(used),
    )


def _build_short_long(b: dict[str, Any]) -> CanonicalFinding | CitedFinding:
    q = b.get("research_question") or "短中期 vs 长期趋势"
    if b.get("status") != "ready":
        return _gap("短期趋势×长期趋势")
    rows = list(b.get("selected") or [])
    ma5 = _by_sub(rows, "ma5")
    ma20 = _by_sub(rows, "ma20")
    ma250 = _by_sub(rows, "ma250")
    close = _by_sub(rows, "close_price")
    short = [x for x in [ma5, ma20] if x]
    long = [x for x in [ma250] if x]
    if not short or not long:
        return _gap("短期趋势×长期趋势")
    used = short + long + ([close] if close else [])
    claim = (
        f"{'；'.join(_num_phrase(x) for x in used)}。"
        f"短中期均线与长期均线（MA250）可能指向不同时间尺度状态；"
        f"因此短期动能与长期压力/支撑必须分开表述，避免混用。"
    )
    return CanonicalFinding(
        finding_id="TENSION_MKT_SHORT_VS_LONG",
        research_question=q,
        claim=claim,
        evidence_ids=_ids(used),
        reasoning="不同时间尺度均线对照形成趋势张力。",
        interpretation="冲突存在并不自动指向方向选择；只定义研究问题。",
        confidence=0.82,
        status="supported",
        finding_kind="tension",
        numbers_preserved=_numbers(used),
    )


def _build_val_price(b: dict[str, Any]) -> CanonicalFinding | CitedFinding:
    q = b.get("research_question") or "估值与价格位置"
    if b.get("status") != "ready":
        return _gap("估值×市场价格")
    rows = list(b.get("selected") or [])
    pe = _by_sub(rows, "pe")
    pb = _by_sub(rows, "pb")
    close = _by_sub(rows, "close_price")
    pos = _by_sub(rows, "price_position_in_52w_range")
    val = [x for x in [pe, pb] if x]
    px = [x for x in [close, pos] if x]
    if not val or not px:
        return _gap("估值×市场价格")
    used = val + px
    claim = (
        f"{'；'.join(_num_phrase(x) for x in used)}。"
        f"估值与价格/52周位置同属 as_of 截面，可共同描述定价状态，但不能单独推导涨跌方向。"
    )
    return CanonicalFinding(
        finding_id="FINDING_MKT_VAL_PRICE",
        research_question=q,
        claim=claim,
        evidence_ids=_ids(used),
        reasoning="估值指标与价格位置在同一研究问题下联合。",
        interpretation="状态描述；不作目标价。",
        confidence=0.76,
        status="supported",
        finding_kind="cross",
        numbers_preserved=_numbers(used),
    )


def _atomic_fact(row: dict[str, Any] | None, *, fid: str) -> CitedFinding | None:
    if not row:
        return None
    return CitedFinding(
        claim=str(row.get("claim") or ""),
        evidence_ids=[str(row["evidence_id"])],
        reasoning=f"核心事实锚点 {row.get('evidence_id')}（按 weight 优先选取）。",
        interpretation="仅作事实锚点，分析见 canonical_findings。",
        confidence=0.9,
        status="supported",
        finding_kind="atomic",
        finding_id=fid,
    )


def _theme_tags(claim: str) -> set[str]:
    text = claim or ""
    mapping = {
        "demand": ("需求", "去库存", "经销", "批价", "动销", "渠道"),
        "pricing": ("提价", "涨价", "降价", "价格上调"),
        "volume": ("销量", "放量", "销量恢复", "出货"),
        "management": ("管理层", "指引", "回购", "分红", "高管"),
        "product": ("新品", "产品", "大单品", "系列"),
        "profit_pressure": ("经营压力", "利润下滑", "承压", "下滑"),
    }
    tags: set[str] = set()
    for tag, keys in mapping.items():
        if any(k in text for k in keys):
            tags.add(tag)
    return tags


def _build_news_narrative(
    news_cur: list[dict[str, Any]],
    news_prev: list[dict[str, Any]],
) -> tuple[CanonicalFinding | None, CitedFinding | None]:
    """Return (canonical | None, gap | None)."""
    if not news_cur and not news_prev:
        return None, _gap("新闻 Current/Previous 个股相关资讯")
    if news_cur and not news_prev:
        return None, _gap("新闻 Previous(8–30d)，无法比较 narrative change")
    if news_prev and not news_cur:
        return None, _gap("新闻 Current(7d)，无法比较 narrative change")

    cur = select_by_weight(news_cur, n=2)
    prev = select_by_weight(news_prev, n=2)
    used = cur + prev
    cur_tags: set[str] = set()
    prev_tags: set[str] = set()
    for x in cur:
        cur_tags |= _theme_tags(str(x.get("claim") or ""))
    for x in prev:
        prev_tags |= _theme_tags(str(x.get("claim") or ""))

    theme_changed = bool(cur_tags or prev_tags) and cur_tags != prev_tags
    if theme_changed:
        claim = (
            f"Current(7d)：{'；'.join(str(x.get('claim') or '') for x in cur)}。"
            f"Previous(8–30d)：{'；'.join(str(x.get('claim') or '') for x in prev)}。"
            f"两侧主题标签从 {sorted(prev_tags) or ['未识别']} 转为 {sorted(cur_tags) or ['未识别']}，"
            f"构成 narrative change；但仍属资讯层变化，不能直接外推财务结果。"
        )
        interp = "叙事关注点发生变化；证据边界：快讯主题变化不等于基本面已确认改善/恶化。"
        kind = "tension"
        conf = 0.7
    else:
        claim = (
            f"Current(7d)：{'；'.join(str(x.get('claim') or '') for x in cur)}。"
            f"Previous(8–30d)：{'；'.join(str(x.get('claim') or '') for x in prev)}。"
            f"两侧主题相近（标签={sorted(cur_tags | prev_tags) or ['未识别']}），"
            f"仅有数量/措辞差异，不得强行生成 narrative shift。"
        )
        interp = "双边有料但主题未实质切换；记录为可比资讯，不作叙事转向结论。"
        kind = "cross"
        conf = 0.62

    narr = CanonicalFinding(
        finding_id="TENSION_MKT_NEWS_NARRATIVE",
        research_question="Current 7d vs Previous 8–30d 叙事是否变化？",
        claim=claim,
        evidence_ids=_ids(used),
        reasoning="仅使用 stock_specific 新闻窗；宏观/无关资讯不进入比较。主题变化才记为 narrative change。",
        interpretation=interp,
        confidence=conf,
        status="supported",
        finding_kind=kind,  # type: ignore[arg-type]
        numbers_preserved=_numbers(used),
    )
    return narr, None


def synthesize_fundamental(stock_code: str, payload: dict[str, Any]) -> FundamentalResearch:
    as_of = str(payload.get("research_as_of_date") or "")
    idx = _index(payload)
    groups = payload.get("evidence_groups") or {}
    bundles = _bundle_map(payload)
    fin = groups.get("financial_latest") or []
    profile = groups.get("company_profile") or []
    events = groups.get("company_events_90d") or []
    expect = groups.get("expectation_latest") or []

    canonicals: list[CanonicalFinding] = []
    gaps: list[CitedFinding] = []

    for key, builder in [
        ("profitability_x_growth", _build_profitability_growth),
        ("cashflow_x_earnings_quality", _build_cash_quality),
        ("balance_sheet_x_operating_risk", _build_balance_op),
        ("valuation_x_earnings_or_growth", _build_valuation_growth),
    ]:
        item = builder(bundles.get(key) or {})
        if isinstance(item, CanonicalFinding):
            canonicals.append(item)
        else:
            gaps.append(item)

    # core facts: few anchors with numbers
    name = _by_sub(profile, "stock_name")
    industry = _by_sub(profile, "industry")
    roe = _by_sub(fin, "roe")
    core = [x for x in [
        _atomic_fact(name, fid="FACT_NAME"),
        _atomic_fact(industry, fid="FACT_INDUSTRY"),
        _atomic_fact(roe, fid="FACT_ROE"),
    ] if x]

    tensions = [c for c in canonicals if c.finding_kind == "tension"]
    key_findings = [c for c in canonicals if c.finding_kind == "cross"]
    # promote tensions also into key list? keep separate — key = non-tension cross only
    gaps.append(_gap("客户结构"))
    gaps.append(_gap("管理层展望原文"))

    # Compatibility sections: references only (no full clone)
    profit_c = [c for c in canonicals if "PROFIT_VS_GROWTH" in c.finding_id]
    cash_c = [c for c in canonicals if "CASH_QUALITY" in c.finding_id]
    bal_c = [c for c in canonicals if "BALANCE_OP" in c.finding_id]
    val_c = [c for c in canonicals if "VALUATION_VS_GROWTH" in c.finding_id]

    biz = _section_ref("公司画像锚点；客户结构见 evidence_gaps。", [], ["客户结构"])
    if name and industry:
        biz = ResearchSection(
            narrative="公司身份锚点（不展开业务推断）。",
            findings=[x for x in [_atomic_fact(name, fid="FACT_NAME"), _atomic_fact(industry, fid="FACT_INDUSTRY")] if x],
            insufficient_topics=["客户结构"],
        )

    financial_performance = _section_ref("财务表现命题见 canonical。", profit_c + val_c)
    profitability = _section_ref("盈利能力命题引用 canonical，不重复全文。", profit_c)
    financial_health = _section_ref("财务健康命题引用 canonical。", bal_c)
    cash_flow = _section_ref("现金流命题引用 canonical。", cash_c)

    if events:
        e0 = select_by_weight(events, n=1)[0]
        recent_events = ResearchSection(
            narrative="公司事件使用 90d 窗口。",
            findings=[
                CitedFinding(
                    claim=str(e0.get("claim") or ""),
                    evidence_ids=[str(e0["evidence_id"])],
                    reasoning="事件锚点按 weight 优先选取。",
                    interpretation="单事件不作趋势外推。",
                    confidence=0.65,
                    status="supported",
                    finding_kind="atomic",
                    finding_id="FACT_EVENT",
                )
            ],
        )
    else:
        recent_events = _section_ref("无公司近90天事件。", [], ["公司近90天事件"])

    if expect:
        exp_rows = select_by_weight(expect, n=3)
        market_expectations = ResearchSection(
            narrative="一致预期为截面，非已实现盈利。",
            findings=[
                CitedFinding(
                    claim="；".join(str(r.get("claim") or "") for r in exp_rows),
                    evidence_ids=_ids(exp_rows),
                    reasoning="多期一致预期截面（按 weight 选取）。",
                    interpretation="EXPECTATION，不作买卖建议。",
                    confidence=0.7,
                    status="supported",
                    finding_kind="cross" if len(exp_rows) >= 2 else "atomic",
                    finding_id="FACT_EXPECT",
                    research_question="一致预期截面是什么？",
                )
            ],
        )
    else:
        market_expectations = _section_ref("缺少一致预期。", [], ["一致预期"])

    # strengths/weaknesses / spine lists = short refs only (canonical is sole full expression)
    strengths = [_ref(c) for c in canonicals if "PROFIT" in c.finding_id or "CASH" in c.finding_id][:2]
    weaknesses = [_ref(c) for c in tensions][:2]
    uncertainties = list(gaps)

    used = sorted({eid for c in canonicals for eid in c.evidence_ids} | {eid for f in core for eid in f.evidence_ids})
    summary = (
        f"research_as_of_date={as_of}。已压缩为 canonical 研究命题："
        + "；".join(c.research_question for c in canonicals[:3])
        + "。关键数字保留在 canonical_findings 中。不含买卖建议。"
    )

    all_cite_src: list[CitedFinding] = list(canonicals) + core
    return FundamentalResearch(
        stock_code=stock_code,
        research_as_of_date=as_of,
        summary=summary,
        core_facts=core,
        key_research_findings=[_ref(c) for c in key_findings],
        research_tensions=[_ref(c) for c in tensions],
        evidence_gaps=gaps,
        canonical_findings=canonicals,
        business_model=biz,
        financial_performance=financial_performance,
        profitability=profitability,
        financial_health=financial_health,
        cash_flow=cash_flow,
        recent_events=recent_events,
        market_expectations=market_expectations,
        cross_evidence_findings=[_ref(c) for c in canonicals],
        key_strengths=strengths,
        key_weaknesses=weaknesses,
        key_uncertainties=uncertainties,
        evidence_citations=_citations(all_cite_src, idx),
        used_evidence_ids=used,
        excluded_audit=_excluded(payload),
    )


def synthesize_market(stock_code: str, payload: dict[str, Any]) -> MarketResearch:
    as_of = str(payload.get("research_as_of_date") or "")
    idx = _index(payload)
    groups = payload.get("evidence_groups") or {}
    bundles = _bundle_map(payload)
    spot = groups.get("market_spot") or []
    news_cur = groups.get("news_current_7d") or []
    news_prev = groups.get("news_previous_8_30d") or []
    industry = groups.get("industry_30d") or []
    macro = groups.get("macro_background") or []
    expect = groups.get("expectation_latest") or []

    canonicals: list[CanonicalFinding] = []
    gaps: list[CitedFinding] = []

    for key, builder in [
        ("price_x_moving_averages", _build_price_ma),
        ("short_trend_x_long_trend", _build_short_long),
        ("valuation_x_market_price", _build_val_price),
    ]:
        item = builder(bundles.get(key) or {})
        if isinstance(item, CanonicalFinding):
            canonicals.append(item)
        else:
            gaps.append(item)

    close = _by_sub(spot, "close_price")
    pe = _by_sub(spot, "pe")
    core = [x for x in [_atomic_fact(close, fid="FACT_CLOSE"), _atomic_fact(pe, fid="FACT_PE")] if x]

    tensions = [c for c in canonicals if c.finding_kind == "tension"]
    key_findings = [c for c in canonicals if c.finding_kind == "cross"]

    # Narrative change — only if both windows have stock_specific news
    narr, narr_gap = _build_news_narrative(news_cur, news_prev)
    if narr is not None:
        canonicals.append(narr)
        if narr.finding_kind == "tension":
            tensions.append(narr)
        else:
            key_findings.append(narr)
        news_narrative = _section_ref("叙事比较见 canonical。", [narr])
    else:
        assert narr_gap is not None
        gaps.append(narr_gap)
        news_narrative = ResearchSection(
            narrative="新闻窗不足以支持可靠 narrative change。",
            findings=[narr_gap],
            insufficient_topics=["news_windows"],
        )

    price_c = [c for c in canonicals if c.finding_id == "FINDING_MKT_PRICE_MA"]
    short_c = [c for c in canonicals if c.finding_id == "TENSION_MKT_SHORT_VS_LONG"]
    val_c = [c for c in canonicals if c.finding_id == "FINDING_MKT_VAL_PRICE"]

    price_status = _section_ref("价格/估值状态见 canonical。", price_c + val_c)
    trend = _section_ref("趋势张力见 canonical。", short_c)
    moving_average_structure = _section_ref("均线结构引用价格×均线命题。", price_c)
    momentum = ResearchSection(
        narrative="动量仅在有 RSI/MACD 时补充；本阶段不强制 cross。",
        findings=[],
        insufficient_topics=[],
    )
    rsi = _by_sub(spot, "rsi_14")
    macd = _by_sub(spot, "macd_hist")
    if rsi and macd:
        momentum = ResearchSection(
            narrative="动量补充。",
            findings=[
                CitedFinding(
                    claim=f"{rsi.get('claim')}；{macd.get('claim')}。二者需一并观察，避免单指标结论。",
                    evidence_ids=_ids([rsi, macd]),
                    reasoning="动量指标同截面联合。",
                    interpretation="补充状态，不升级为独立交易信号。",
                    confidence=0.68,
                    status="supported",
                    finding_kind="cross",
                    finding_id="FINDING_MKT_MOMENTUM",
                )
            ],
        )
    technical_signals = _section_ref("技术信号由趋势张力与动量补充构成。", short_c)

    # recent events: stock news only; industry/macro separately noted without fake cross
    event_findings: list[CitedFinding] = []
    if news_cur:
        top = select_by_weight(news_cur, n=2)
        event_findings.append(
            CitedFinding(
                claim="；".join(str(x.get("claim") or "") for x in top),
                evidence_ids=_ids(top),
                reasoning="仅 stock_specific Current 7d 资讯。",
                interpretation="背景信息，不替代财务/价格研究。",
                confidence=0.62,
                status="supported",
                finding_kind="atomic" if len(top) == 1 else "cross",
                finding_id="FACT_NEWS_CUR",
            )
        )
    else:
        event_findings.append(_gap("Current 7d 个股资讯"))
    if industry:
        ind = select_by_weight(industry, n=1)[0]
        event_findings.append(
            CitedFinding(
                claim=f"行业上下文：{ind.get('claim')}",
                evidence_ids=[str(ind["evidence_id"])],
                reasoning="research_role=industry_context",
                interpretation="仅行业背景，不自动升级为核心公司判断。",
                confidence=0.6,
                status="supported",
                finding_kind="atomic",
                finding_id="FACT_INDUSTRY_CTX",
            )
        )
    if macro:
        m0 = select_by_weight(macro, n=1)[0]
        event_findings.append(
            CitedFinding(
                claim=f"宏观背景：{m0.get('claim')}",
                evidence_ids=[str(m0["evidence_id"])],
                reasoning="research_role=macro_background",
                interpretation="宏观背景不得冒充公司基本面证据。",
                confidence=0.7,
                status="supported",
                finding_kind="atomic",
                finding_id="FACT_MACRO_BG",
            )
        )
    recent_market_events = ResearchSection(
        narrative="事件按 research_role 分层，禁止弱相关拼盘伪 cross。",
        findings=event_findings,
    )

    if expect:
        exp_rows = select_by_weight(expect, n=3)
        market_expectations = ResearchSection(
            narrative="一致预期截面。",
            findings=[
                CitedFinding(
                    claim="；".join(str(r.get("claim") or "") for r in exp_rows),
                    evidence_ids=_ids(exp_rows),
                    reasoning="按 weight 选取预期截面。",
                    interpretation="EXPECTATION。",
                    confidence=0.7,
                    status="supported",
                    finding_kind="cross" if len(exp_rows) >= 2 else "atomic",
                    finding_id="FACT_EXPECT",
                )
            ],
        )
    else:
        market_expectations = _section_ref("缺少一致预期。", [], ["一致预期"])

    gaps.extend([_gap("盘口微观结构"), _gap("机构持仓完整时序")])
    strengths = [_ref(c) for c in key_findings][:2]
    weaknesses = [_ref(c) for c in tensions][:2]

    used = sorted({eid for c in canonicals for eid in c.evidence_ids} | {eid for f in core for eid in f.evidence_ids})
    summary = (
        f"research_as_of_date={as_of}。市场研究压缩为 canonical 命题："
        + "；".join(c.research_question for c in canonicals[:3])
        + "。关键数字保留在 canonical_findings。不含买卖建议。"
    )

    return MarketResearch(
        stock_code=stock_code,
        research_as_of_date=as_of,
        summary=summary,
        core_facts=core,
        key_research_findings=[_ref(c) for c in key_findings],
        research_tensions=[_ref(c) for c in tensions],
        evidence_gaps=gaps,
        canonical_findings=canonicals,
        price_status=price_status,
        trend=trend,
        moving_average_structure=moving_average_structure,
        momentum=momentum,
        technical_signals=technical_signals,
        recent_market_events=recent_market_events,
        market_expectations=market_expectations,
        news_narrative=news_narrative,
        cross_evidence_findings=[_ref(c) for c in canonicals],
        key_strengths=strengths,
        key_weaknesses=weaknesses,
        key_uncertainties=gaps,
        evidence_citations=_citations(list(canonicals) + core, idx),
        used_evidence_ids=used,
        excluded_audit=_excluded(payload),
    )
