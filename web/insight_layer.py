"""Presentation-only insight synthesis for Deep Research Workspace.

Transforms frozen Evidence / Research artifacts into ranked research signals.
Does not call LLMs, invent facts, or change Final Analyst judgment.
"""

from __future__ import annotations

import re
from typing import Any

_IMPACT_CHANNELS = (
    "收入/销量",
    "成本",
    "利润率",
    "估值/风险溢价",
    "主题预期",
    "竞争格局",
    "供应链",
    "无明显关联",
)

_LINK_STRENGTH = {
    "direct": "与公司主业高度相关",
    "adjacent": "产业链邻接信号",
    "background": "行业/宏观背景",
    "noise": "主题噪音",
    "none": "暂时不构成核心公司变量",
}


def _parse_pct(text: str | None) -> float | None:
    if not text:
        return None
    s = str(text).strip().lstrip("+")
    if not s.endswith("%"):
        return None
    try:
        return float(s.rstrip("%"))
    except ValueError:
        return None


def _yoy_dir(row: dict[str, Any] | None) -> str:
    v = _parse_pct((row or {}).get("value"))
    if v is None:
        return "unknown"
    if v > 0.5:
        return "pos"
    if v < -0.5:
        return "neg"
    return "flat"


def _latest_by_subtype(evidence: list[dict[str, Any]], subtype: str) -> dict[str, Any] | None:
    items = [e for e in evidence if e.get("subtype") == subtype]
    if not items:
        return None

    def _period(e: dict[str, Any]) -> str:
        t = e.get("time") or {}
        v = e.get("value") or {}
        return str(t.get("report_date") or v.get("period") or t.get("data_date") or "")

    return max(items, key=lambda e: _period(e) or "")


def _kpi_from_evidence(evidence: list[dict[str, Any]], subtype: str, label: str) -> dict[str, Any] | None:
    e = _latest_by_subtype(evidence, subtype)
    if not e:
        return None
    claim = e.get("claim") or ""
    m = re.search(r"同比下降\s*([-\d.]+%)", claim)
    if m:
        display = f"-{m.group(1).lstrip('-')}"
    else:
        m = re.search(r"同比(?:上升|增长)\s*([-\d.]+%)", claim)
        if m:
            display = f"+{m.group(1).lstrip('+')}"
        else:
            m = re.search(r"为\s*([-\d.]+%?)(?:\s|$|元|倍)", claim)
            display = m.group(1) if m else ""
    if not display:
        val = (e.get("value") or {}).get("value")
        unit = (e.get("value") or {}).get("unit")
        if isinstance(val, (int, float)):
            if unit == "ratio" and abs(val) <= 2:
                display = f"{val * 100:.2f}%"
            elif abs(val) >= 100:
                display = f"{val:.2f}"
            else:
                display = f"{val:.2f}"
    if not display:
        return None
    t = e.get("time") or {}
    v = e.get("value") or {}
    period = str(t.get("report_date") or v.get("period") or t.get("data_date") or "")
    return {
        "label": label,
        "value": display,
        "period": period,
        "evidence_id": e.get("evidence_id") or "",
        "claim": claim,
        "subtype": subtype,
    }


def _build_kpis(evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    specs = [
        ("roe", "ROE"),
        ("gross_margin", "毛利率"),
        ("revenue_yoy", "营收同比"),
        ("net_profit_yoy", "归母净利同比"),
        ("debt_to_asset_ratio", "资产负债率"),
        ("pe", "PE(TTM)"),
        ("pb", "PB"),
        ("ocf_to_net_profit", "经营现金流/净利"),
        ("operating_cash_flow", "经营现金流"),
        ("net_margin", "净利率"),
    ]
    out: dict[str, dict[str, Any]] = {}
    for subtype, label in specs:
        row = _kpi_from_evidence(evidence, subtype, label)
        if row:
            out[subtype] = row
    return out


def _insight(
    *,
    kind: str,
    source: str,
    headline: str,
    agent_insight: str,
    why: list[str],
    meaning: str,
    research_question: str,
    impact_channels: list[str] | None = None,
    link_strength: str = "direct",
    company_link: str = "",
    key_data: list[dict[str, str]] | None = None,
    evidence_ids: list[str] | None = None,
    score: float = 0.0,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "source": source,
        "headline": headline,
        "event": headline if source == "external" else "",
        "agent_insight": agent_insight,
        "why": why,
        "meaning": meaning,
        "research_question": research_question,
        "impact_channels": impact_channels or [],
        "link_strength": link_strength,
        "link_strength_label": _LINK_STRENGTH.get(link_strength, link_strength),
        "company_link": company_link,
        "key_data": key_data or [],
        "evidence_ids": evidence_ids or [],
        "score": score,
    }


def _fundamental_candidates(kpis: dict[str, dict[str, Any]], evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rev, prof = kpis.get("revenue_yoy"), kpis.get("net_profit_yoy")
    gm, roe = kpis.get("gross_margin"), kpis.get("roe")
    ocf_ratio = kpis.get("ocf_to_net_profit")
    debt = kpis.get("debt_to_asset_ratio")
    pe = kpis.get("pe")
    ocf = kpis.get("operating_cash_flow")

    rv = _parse_pct((rev or {}).get("value"))
    pv = _parse_pct((prof or {}).get("value"))
    eids = [x["evidence_id"] for x in (rev, prof, gm, roe, ocf_ratio, debt, pe, ocf) if x and x.get("evidence_id")]

    if rv is not None and pv is not None and rv < 0 and pv < rv:
        out.append(
            _insight(
                kind="fundamental",
                source="fundamental",
                headline="利润降幅已超过收入降幅",
                agent_insight="收入与利润同步走弱，但利润对收入变化更敏感，可能存在经营杠杆、费用率或产品结构放大效应。",
                why=[
                    f"营收同比 {(rev or {}).get('value')}（{(rev or {}).get('period')}）",
                    f"归母净利同比 {(prof or {}).get('value')}（{(prof or {}).get('period')}）",
                ],
                meaning="当前更值得研究利润弹性，而不是简单把问题定义为「增长承压」。",
                research_question="利润降幅是否来自费用率抬升、产品结构变化还是一次性因素？",
                impact_channels=["利润率", "收入/销量"],
                link_strength="direct",
                company_link="反映公司当期经营结果与盈利质量",
                key_data=[
                    {"label": "营收同比", "value": (rev or {}).get("value", ""), "period": (rev or {}).get("period", "")},
                    {"label": "归母净利同比", "value": (prof or {}).get("value", ""), "period": (prof or {}).get("period", "")},
                ],
                evidence_ids=[x for x in [(rev or {}).get("evidence_id"), (prof or {}).get("evidence_id")] if x],
                score=88 + abs(pv - rv),
            )
        )

    if rv is not None and pv is not None and rv > 3 and 0 <= pv < 3:
        out.append(
            _insight(
                kind="fundamental",
                source="fundamental",
                headline="营收扩张较快，但利润释放明显偏慢",
                agent_insight="规模仍在增长，但利润增速显著落后于收入，需区分是投入期、价格竞争还是费用前置。",
                why=[
                    f"营收同比 {(rev or {}).get('value')}",
                    f"归母净利同比 {(prof or {}).get('value')}",
                ],
                meaning="核心矛盾不是「有没有增长」，而是增长是否转化为利润。",
                research_question="利润滞后是毛利率、费用率还是交付/确认节奏造成？",
                impact_channels=["收入/销量", "利润率"],
                link_strength="direct",
                company_link="主营扩张与盈利兑现之间的落差",
                key_data=[
                    {"label": "营收同比", "value": (rev or {}).get("value", ""), "period": (rev or {}).get("period", "")},
                    {"label": "归母净利同比", "value": (prof or {}).get("value", ""), "period": (prof or {}).get("period", "")},
                ],
                evidence_ids=[x for x in [(rev or {}).get("evidence_id"), (prof or {}).get("evidence_id")] if x],
                score=85 + rv - pv,
            )
        )

    if rv is not None and pv is not None and rv < 0 and pv > 0:
        out.append(
            _insight(
                kind="fundamental",
                source="fundamental",
                headline="收入承压但利润仍正增长",
                agent_insight="增长质量发生变化：利润可能来自产品结构、费用控制或低基数，而非收入扩张。",
                why=[f"营收同比 {(rev or {}).get('value')}", f"归母净利同比 {(prof or {}).get('value')}"],
                meaning="研究重点应转向利润来源，而非继续围绕收入规模。",
                research_question="利润增长来自哪些业务线或一次性因素？能否持续？",
                impact_channels=["利润率", "收入/销量"],
                link_strength="direct",
                company_link="盈利质量与收入规模的背离",
                key_data=[
                    {"label": "营收同比", "value": (rev or {}).get("value", ""), "period": (rev or {}).get("period", "")},
                    {"label": "归母净利同比", "value": (prof or {}).get("value", ""), "period": (prof or {}).get("period", "")},
                ],
                evidence_ids=[x for x in [(rev or {}).get("evidence_id"), (prof or {}).get("evidence_id")] if x],
                score=82,
            )
        )

    ocf_val = (ocf or {}).get("value") or ""
    ocf_neg = ocf_val.startswith("-")
    ratio_v = _parse_pct((ocf_ratio or {}).get("value"))
    if ratio_v is not None and ratio_v < 80:
        out.append(
            _insight(
                kind="fundamental",
                source="fundamental",
                headline="利润与经营现金流出现背离",
                agent_insight="账面利润并未同等转化为现金回收，需关注应收、存货或预收变化。",
                why=[
                    f"经营现金流/净利 {(ocf_ratio or {}).get('value')}（{(ocf_ratio or {}).get('period')}）",
                ],
                meaning="若利润增长不能伴随现金流改善，增长质量需要打折验证。",
                research_question="背离主要来自营运资本占用还是确认节奏？",
                impact_channels=["成本", "收入/销量"],
                link_strength="direct",
                company_link="利润质量与现金回收",
                key_data=[{"label": "经营现金流/净利", "value": (ocf_ratio or {}).get("value", ""), "period": (ocf_ratio or {}).get("period", "")}],
                evidence_ids=[(ocf_ratio or {}).get("evidence_id", "")] if ocf_ratio else [],
                score=78 + (80 - ratio_v) * 0.2,
            )
        )
    elif ocf_neg and pv is not None and pv > 0:
        out.append(
            _insight(
                kind="fundamental",
                source="fundamental",
                headline="利润为正但经营现金流为负",
                agent_insight="当期盈利尚未体现为现金流入，可能存在营运资本拖累。",
                why=[f"经营现金流 {ocf_val}", f"归母净利同比 {(prof or {}).get('value')}"],
                meaning="需验证利润是否真正转化为可动用现金。",
                research_question="负现金流是否来自备货、应收还是资本性支出混淆？",
                impact_channels=["成本"],
                link_strength="direct",
                company_link="现金流与利润的时间差",
                key_data=[
                    {"label": "经营现金流", "value": ocf_val, "period": (ocf or {}).get("period", "")},
                    {"label": "归母净利同比", "value": (prof or {}).get("value", ""), "period": (prof or {}).get("period", "")},
                ],
                evidence_ids=[x for x in [(ocf or {}).get("evidence_id"), (prof or {}).get("evidence_id")] if x],
                score=76,
            )
        )

    debt_v = _parse_pct((debt or {}).get("value"))
    roe_v = _parse_pct((roe or {}).get("value"))
    if debt_v is not None and debt_v > 60 and roe_v is not None and roe_v > 15:
        out.append(
            _insight(
                kind="fundamental",
                source="fundamental",
                headline="高 ROE 与较高杠杆并存",
                agent_insight="ROE 水平不低，但资产负债率偏高，需拆解杠杆对回报率的贡献。",
                why=[f"ROE {(roe or {}).get('value')}", f"资产负债率 {(debt or {}).get('value')}"],
                meaning="高 ROE 未必完全来自经营效率，财务安全垫同样值得跟踪。",
                research_question="ROE 改善中杠杆、周转与利润率各贡献多少？",
                impact_channels=["估值/风险溢价"],
                link_strength="direct",
                company_link="资本结构与股东回报",
                key_data=[
                    {"label": "ROE", "value": (roe or {}).get("value", ""), "period": (roe or {}).get("period", "")},
                    {"label": "资产负债率", "value": (debt or {}).get("value", ""), "period": (debt or {}).get("period", "")},
                ],
                evidence_ids=[x for x in [(roe or {}).get("evidence_id"), (debt or {}).get("evidence_id")] if x],
                score=70 + min(debt_v - 60, 20),
            )
        )

    gm_v = _parse_pct((gm or {}).get("value"))
    if gm_v is not None and gm_v > 70 and rv is not None and rv < 0:
        out.append(
            _insight(
                kind="fundamental",
                source="fundamental",
                headline="高毛利与收入走弱同时出现",
                agent_insight="盈利质量指标仍强，但规模增长转弱，需判断是需求问题还是短期基数/节奏问题。",
                why=[f"毛利率 {(gm or {}).get('value')}", f"营收同比 {(rev or {}).get('value')}"],
                meaning="不应只用「盈利能力强」概括；更要问高毛利能否在收入走弱时维持。",
                research_question="收入走弱是否已开始侵蚀毛利率或销量结构？",
                impact_channels=["收入/销量", "利润率"],
                link_strength="direct",
                company_link="定价力与需求规模的张力",
                key_data=[
                    {"label": "毛利率", "value": (gm or {}).get("value", ""), "period": (gm or {}).get("period", "")},
                    {"label": "营收同比", "value": (rev or {}).get("value", ""), "period": (rev or {}).get("period", "")},
                ],
                evidence_ids=[x for x in [(gm or {}).get("evidence_id"), (rev or {}).get("evidence_id")] if x],
                score=74,
            )
        )

    pe_v = _parse_pct((pe or {}).get("value"))
    if pe is not None and rv is not None and pv is not None:
        try:
            pe_n = float(str((pe or {}).get("value", "")).replace("倍", "").strip())
        except ValueError:
            pe_n = None
        if pe_n and pe_n > 25 and (pv < 5 or rv < 5):
            out.append(
                _insight(
                    kind="fundamental",
                    source="fundamental",
                    headline="估值不低，但基本面增速已明显放缓",
                    agent_insight="当前价格隐含的增长预期，与最新财务增速之间存在张力。",
                    why=[f"PE(TTM) {(pe or {}).get('value')}", f"营收同比 {(rev or {}).get('value')}", f"归母净利同比 {(prof or {}).get('value')}"],
                    meaning="核心问题不是「贵不贵」，而是未来增长能否兑现当前估值叙事。",
                    research_question="市场定价隐含了怎样的增速假设？公司能否接近该假设？",
                    impact_channels=["估值/风险溢价"],
                    link_strength="direct",
                    company_link="基本面与定价预期",
                    key_data=[
                        {"label": "PE(TTM)", "value": (pe or {}).get("value", ""), "period": (pe or {}).get("period", "")},
                        {"label": "营收同比", "value": (rev or {}).get("value", ""), "period": (rev or {}).get("period", "")},
                    ],
                    evidence_ids=[x for x in [(pe or {}).get("evidence_id"), (rev or {}).get("evidence_id")] if x],
                    score=68,
                )
            )

    if not out and (rev or prof):
        phrase = "增长与盈利关系需进一步拆解"
        if _yoy_dir(rev) == "neg" and _yoy_dir(prof) == "neg":
            phrase = "收入与利润同步走弱，但主导矛盾尚不明确"
        out.append(
            _insight(
                kind="fundamental",
                source="fundamental",
                headline=phrase,
                agent_insight="现有 KPI 尚未形成单一压倒性矛盾，建议从增长、盈利、现金流三条线交叉验证。",
                why=[f"{(rev or prof).get('label')} {(rev or prof).get('value')}"],
                meaning="避免套用模板结论，先锁定最值得验证的关系。",
                research_question="哪一条指标关系在最近一期变化最异常？",
                impact_channels=["收入/销量", "利润率"],
                link_strength="direct",
                company_link="公司基本面总览",
                key_data=[{"label": (rev or prof).get("label", ""), "value": (rev or prof).get("value", ""), "period": (rev or prof).get("period", "")}],
                evidence_ids=[(rev or prof).get("evidence_id", "")] if (rev or prof) else [],
                score=40,
            )
        )
    return out


def _main_business_hint(evidence: list[dict[str, Any]]) -> str:
    segs = [e for e in evidence if e.get("subtype") == "main_business_segment"]
    if not segs:
        return ""
    claim = (segs[0].get("claim") or "").strip()
    m = re.search(r"[:：]\s*(.+)$", claim)
    return (m.group(1) if m else claim)[:80]


def _industry_hint(snapshot: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    company = snapshot.get("company") or {}
    if company.get("industry"):
        return str(company["industry"]).replace("制造业-", "")
    ind = _latest_by_subtype(evidence, "industry")
    if not ind:
        return ""
    claim = ind.get("claim") or ""
    m = re.search(r"所属行业为\s*(.+)$", claim)
    return (m.group(1) if m else claim).replace("制造业-", "")


def _news_title(e: dict[str, Any]) -> str:
    claim = e.get("claim") or ""
    m = re.search(r"\[(?:market|macro)\]\s*(.+)$", claim)
    if m:
        return m.group(1).strip()
    return claim[:120]


def _classify_external(e: dict[str, Any], *, industry: str, business: str) -> dict[str, Any] | None:
    title = _news_title(e)
    text = f"{title} {e.get('claim') or ''}"
    eid = e.get("evidence_id") or ""
    biz = business or industry or "公司主业"

    if any(k in text for k in ("蛋价", "鸡蛋", "中秋备货")):
        return None
    if any(k in text for k in ("医疗保障", "生育津贴", "医保")):
        return None

    if any(k in text for k in ("存储", "长存", "长江存储", "闪存")):
        return _insight(
            kind="external",
            source="external",
            headline=title,
            agent_insight="存储/国产替代景气变化属于半导体供给端叙事，而非整车厂自身经营变量。",
            why=[f"事件：{title[:60]}"],
            meaning="可放入智能汽车供应链背景，但当前没有证据表明存储是公司关键成本或利润变量。",
            research_question="公司智能化产品对存储采购/value 量的实际暴露度是多少？",
            impact_channels=["供应链", "主题预期"],
            link_strength="adjacent",
            company_link=f"{biz}处于应用端，与存储制造环节存在产业链邻接",
            key_data=[],
            evidence_ids=[eid],
            score=62,
        )

    if any(k in text for k in ("人民币", "汇率", "中间价", "升值", "贬值")):
        return _insight(
            kind="external",
            source="external",
            headline=title,
            agent_insight="汇率环境变化影响出口竞争力、汇兑损益与外资风险偏好，属于宏观背景变量。",
            why=[f"事件：{title[:60]}"],
            meaning="是否传导至公司取决于海外收入占比与定价结构，当前证据不足以直接量化。",
            research_question="公司海外收入占比与汇兑敏感度是多少？",
            impact_channels=["成本", "估值/风险溢价"],
            link_strength="background",
            company_link="宏观汇率背景，需结合公司海外暴露验证",
            key_data=[],
            evidence_ids=[eid],
            score=55,
        )

    if any(k in text for k in ("智能芯片", "人工智能", "智驾", "工信部", "类脑", "世界模型")):
        return _insight(
            kind="external",
            source="external",
            headline=title,
            agent_insight="AI/智能汽车政策与产业主题升温，更可能先影响主题预期与估值叙事，而非当期 EPS。",
            why=[f"事件：{title[:60]}"],
            meaning="公司是应用端参与者，政策信号值得跟踪，但不能直接等同于技术突破或订单兑现。",
            research_question="公司在智驾、座舱等环节的实际技术参与度与价值量是多少？",
            impact_channels=["主题预期", "估值/风险溢价"],
            link_strength="adjacent",
            company_link=f"{biz}属于智能汽车/AI 应用端，非芯片攻关主体",
            key_data=[],
            evidence_ids=[eid],
            score=68,
        )

    if any(k in text for k in ("价格战", "降价", "新能源", "补贴", "以旧换新")):
        return _insight(
            kind="external",
            source="external",
            headline=title,
            agent_insight="行业价格与需求政策变化，可能通过产品售价与销量影响相关企业。",
            why=[f"事件：{title[:60]}"],
            meaning="若公司主营在该赛道，需验证价格变化是否已进入毛利率。",
            research_question="最新价格/促销变化是否已反映在毛利率或销量数据？",
            impact_channels=["收入/销量", "利润率", "竞争格局"],
            link_strength="direct",
            company_link=f"与 {biz} 的产品定价与竞争环境相关",
            key_data=[],
            evidence_ids=[eid],
            score=72,
        )

    if e.get("subtype") == "announcement":
        return _insight(
            kind="external",
            source="external",
            headline=title,
            agent_insight="公司披露事项，可能指向经营节奏、治理或资本运作，需回到正文与财务验证。",
            why=[f"公告：{title[:60]}"],
            meaning="公告标题本身不足以构成结论，但常是研究线索入口。",
            research_question="该公告是否改变产销、盈利或资本结构预期？",
            impact_channels=["收入/销量", "估值/风险溢价"],
            link_strength="direct",
            company_link="公司自身披露",
            key_data=[],
            evidence_ids=[eid],
            score=75,
        )

    if e.get("subtype") in {"macro_news", "market_news"}:
        return _insight(
            kind="external",
            source="external",
            headline=title,
            agent_insight="宏观/市场资讯，提供行业与风险偏好背景，暂未看到与公司主业的直接传导证据。",
            why=[f"事件：{title[:60]}"],
            meaning="保留为背景信号，避免强行建立因果关系。",
            research_question="该变化是否与公司收入、成本或估值渠道存在可验证联系？",
            impact_channels=["无明显关联"],
            link_strength="background",
            company_link="行业/宏观背景",
            key_data=[],
            evidence_ids=[eid],
            score=45,
        )
    return None


def _external_candidates(snapshot: dict[str, Any], evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    industry = _industry_hint(snapshot, evidence)
    business = _main_business_hint(evidence)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    news_types = {"market_news", "macro_news", "announcement"}
    items = [e for e in evidence if e.get("subtype") in news_types]
    items.sort(key=lambda e: str((e.get("time") or {}).get("published_at") or e.get("claim") or ""), reverse=True)
    for e in items:
        title = _news_title(e)
        if not title or title in seen:
            continue
        ins = _classify_external(e, industry=industry, business=business)
        if ins:
            seen.add(title)
            out.append(ins)
        if len(out) >= 8:
            break
    return out


def _build_connections(
    fundamentals: list[dict[str, Any]],
    externals: list[dict[str, Any]],
    *,
    business: str,
) -> list[dict[str, Any]]:
    conns: list[dict[str, Any]] = []
    top_f = fundamentals[:2]
    top_e = [x for x in externals if x.get("link_strength") in {"direct", "adjacent"}][:3]
    for ext in top_e:
        for fund in top_f:
            conns.append(
                {
                    "external_headline": ext.get("headline"),
                    "external_channel": "、".join(ext.get("impact_channels") or []) or "待验证",
                    "fundamental_headline": fund.get("headline"),
                    "exposure": ext.get("company_link") or business or "暴露度待验证",
                    "research_question": ext.get("research_question") or fund.get("research_question"),
                    "link_strength_label": ext.get("link_strength_label"),
                    "evidence_ids": list(dict.fromkeys((ext.get("evidence_ids") or []) + (fund.get("evidence_ids") or [])))[:4],
                }
            )
    if not conns and externals and fundamentals:
        ext = externals[0]
        conns.append(
            {
                "external_headline": ext.get("headline"),
                "external_channel": "、".join(ext.get("impact_channels") or ["无明显关联"]),
                "fundamental_headline": fundamentals[0].get("headline"),
                "exposure": "当前仅见弱关联或背景信号，不宜过度解释",
                "research_question": ext.get("research_question"),
                "link_strength_label": ext.get("link_strength_label"),
                "evidence_ids": ext.get("evidence_ids") or [],
            }
        )
    return conns[:4]


def _fundamental_picture(kpis: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rev, prof, gm, ocf_r = (
        kpis.get("revenue_yoy"),
        kpis.get("net_profit_yoy"),
        kpis.get("gross_margin"),
        kpis.get("ocf_to_net_profit"),
    )
    relations: list[str] = []
    if rev and prof:
        relations.append(f"增长：营收 {rev.get('value')} vs 净利 {prof.get('value')}")
    if gm:
        relations.append(f"盈利：毛利率 {gm.get('value')}")
    if ocf_r:
        relations.append(f"现金流：经营现金流/净利 {ocf_r.get('value')}")
    return {
        "summary": " · ".join(relations) if relations else "关键财务关系待更多期数据确认",
        "relations": relations,
        "kpis": [
            kpis[k]
            for k in ("revenue_yoy", "net_profit_yoy", "gross_margin", "roe", "ocf_to_net_profit", "pe")
            if k in kpis
        ],
    }


def _rank_insights(items: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    def _sort_key(x: dict[str, Any]) -> tuple:
        strength_boost = {
            "direct": 20,
            "adjacent": 12,
            "background": -8,
            "noise": -20,
            "none": -15,
        }.get(str(x.get("link_strength") or "direct"), 0)
        return (float(x.get("score") or 0) + strength_boost, float(x.get("score") or 0))

    ranked = sorted(items, key=_sort_key, reverse=True)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    background_used = 0
    for ins in ranked:
        key = ins.get("headline") or ""
        if key in seen:
            continue
        if ins.get("link_strength") == "background":
            if background_used >= 1:
                continue
            background_used += 1
        seen.add(key)
        out.append(ins)
        if len(out) >= limit:
            break
    return out


def build_insights(snapshot: dict[str, Any], *, kpis: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build ranked research signals from frozen artifacts only."""
    evidence = list(snapshot.get("evidence") or [])
    if kpis is None:
        kpis = _build_kpis(evidence)

    fundamentals = _fundamental_candidates(kpis, evidence)
    externals = _external_candidates(snapshot, evidence)
    business = _main_business_hint(evidence)

    ranked_all = _rank_insights(fundamentals + externals, limit=5)
    top_fund = _rank_insights(fundamentals, limit=3)
    top_ext = _rank_insights(externals, limit=3)

    headline = ranked_all[0] if ranked_all else _insight(
        kind="fundamental",
        source="fundamental",
        headline="暂无可排序洞察，请进入 Evidence Explorer",
        agent_insight="",
        why=[],
        meaning="",
        research_question="哪些指标关系在最近一期最异常？",
        score=0,
    )

    return {
        "headline_insight": {
            "change": headline.get("headline"),
            "why": headline.get("why") or [],
            "meaning": headline.get("meaning") or "",
            "next_research": headline.get("research_question") or "",
            "agent_insight": headline.get("agent_insight") or "",
            "evidence_ids": headline.get("evidence_ids") or [],
        },
        "research_signals": ranked_all,
        "fundamental_insights": top_fund,
        "external_signals": top_ext,
        "connections": _build_connections(top_fund, top_ext, business=business),
        "fundamental_picture": _fundamental_picture(kpis),
    }
