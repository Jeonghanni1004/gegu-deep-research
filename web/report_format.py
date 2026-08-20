"""Presentation-only insight integration.

Transforms frozen Agent artifacts into a compressed research memo.
Does not call LLMs. Does not invent facts. Does not change judgment fields.
"""

from __future__ import annotations

import re
from typing import Any

from insight_layer import build_insights

AXIS_LABELS = {
    "growth_vs_profitability": "增长 vs 盈利",
    "valuation_vs_growth": "估值 vs 增长",
    "volume_vs_margin": "销量 vs 利润率",
    "utilization_vs_asp": "利用率 vs ASP",
    "fundamental_vs_market": "基本面 vs 市场",
    "cycle_vs_capex": "周期 vs 资本开支",
    "unknown": "待明确",
}

RESOLUTION_LABELS = {
    "unresolved": "解释未决",
    "bull_supported": "偏多解释占优",
    "bear_supported": "偏空解释占优",
    "partially_resolved": "部分收敛",
    "unknown": "未知",
}

STRENGTH_LABELS = {
    "unresolved": "未决",
    "tentative": "审慎",
    "moderate": "中等",
    "strong": "较强",
    "unknown": "未知",
}

PRESSURE_LABELS = {
    "mild": "温和",
    "elevated": "偏高",
    "severe": "严峻",
    None: "不适用",
}

SUPPORT_LABELS = {
    "weak": "偏弱",
    "moderate": "中等",
    "strong": "较强",
    None: "不适用",
}

METRIC_LABELS = {
    "roe": "ROE",
    "gross_margin": "毛利率",
    "revenue_yoy": "营收同比",
    "net_profit_yoy": "归母净利同比",
    "debt_to_asset_ratio": "资产负债率",
    "pe": "PE(TTM)",
    "pb": "PB",
    "close_price": "最新价",
    "net_profit_parent": "归母净利",
    "operating_revenue": "营业收入",
    "ocf_to_net_profit": "经营现金流/净利",
    "cash_and_equivalents": "货币资金",
    "operating_cash_flow": "经营现金流",
    "ma5": "MA5",
    "ma20": "MA20",
    "ma60": "MA60",
    "ma250": "MA250",
    "announcement": "公司公告",
    "eps_consensus": "EPS一致预期",
    "shareholder_change": "增减持",
}

SOURCE_LABELS = {
    "python.derived": "财务派生",
    "akshare.stock_value_em": "东财估值",
    "akshare.stock_profit_sheet_by_report_em": "利润表",
    "akshare.stock_balance_sheet_by_report_em": "资产负债表",
    "akshare.stock_cash_flow_sheet_by_report_em": "现金流量表",
    "eastmoney": "东方财富",
    "tonghuashun": "同花顺",
    "cls": "财联社",
}

PROFILE_LABELS = {
    "stock_name": "名称",
    "industry": "行业",
    "listing_date": "上市日期",
    "total_market_cap": "总市值",
    "total_shares": "总股本",
    "float_shares": "流通股本",
}

CHALLENGE_TYPE_LABELS = {
    "evidence_conflict": "证据冲突",
    "evidence_insufficient": "证据不足",
    "interpretation_conflict": "解释冲突",
    "time_sensitivity": "时效敏感",
    "assumption": "假设质疑",
    "scope": "范围质疑",
}

RESPONSE_LABELS = {
    "accept": "接受",
    "partially_accept": "部分接受",
    "reject": "驳回",
}

DIRECTION_LABELS = {
    "more_constructive": "判断可更积极",
    "more_cautious": "判断需更谨慎",
    "unresolved_to_resolved": "未决可转为裁定",
}

_META_EQ = re.compile(
    r"(?:assessment_strength|support_strength|evidence_pressure|strength|resolution|"
    r"analyst_mode|inference_status)\s*=\s*[A-Za-z0-9_/\-]+",
    re.I,
)
_ID_TOKEN = re.compile(r"\b(?:TENSION_|FINDING_|CH_|RB_|BULL_|BEAR_)[A-Z0-9_]+\b")
_BRACKET_IDS = re.compile(r"\[[^\]]*(?:CH_|RB_|BULL_|BEAR_)[^\]]*\]")
_PREFIXES = re.compile(
    r"^(?:"
    r"as_of=\d{4}-\d{2}-\d{2}[：:]\s*|"
    r"Core thesis（校准）[：:]\s*|"
    r"Base（非机械）[：:]\s*|"
    r"Bull 边界[：:]\s*|"
    r"Bear 边界[：:]\s*|"
    r"驱动（[^）]+）[：:]\s*|"
    r"Debate unresolved survival[：:]\s*|"
    r"Primary tension \S+\s*Debate unresolved[：:]\s*|"
    r"Debate 未裁定 \S+[：:]\s*|"
    r"Debate resolution=\S+[：:]\s*|"
    r"继承 Research gap[：:]\s*|"
    r"Debate 主 resolution=\S+[（(][^）)]*[）)][。.]?\s*"
    r")"
)
_JARGON_PHRASES = [
    (r"accept/partially_accept", "部分接受"),
    (r"partially_accept", "部分接受"),
    (r"evidence_insufficient", "证据不足"),
    (r"interpretation_conflict", "解释冲突"),
    (r"Challenge/Rebuttal", "质询与回应"),
    (r"support_strength=None", ""),
    (r"resolution=unresolved", "解释未决"),
    (r"evidence_pressure=elevated", "证据压力偏高"),
    (r"\bRebuttal\b", "回应"),
    (r"\bChallenge\b", "质询"),
    (r"\bEvidence\b", "证据"),
    (r"\bBull\b", "多头"),
    (r"\bBear\b", "空头"),
    (r"\bBase\b", "基准情形"),
    (r"Final Analyst", "最终判断"),
    (r"Research Context", "现有研究材料"),
    (r"Primary tension\s+", ""),
    (r"Debate unresolved survival[：:]\s*", ""),
    (r"未对本 tension 立论", "未对本命题立论"),
    (r"未对本命题 tension 立论", "未对本命题立论"),
]


def human_label(mapping: dict[Any, str], key: Any, fallback: str | None = None) -> str:
    if key in mapping:
        return mapping[key]
    return fallback if fallback is not None else str(key or "—")


def clean_prose(text: str | None, *, max_chars: int = 420) -> str:
    if not text:
        return ""
    t = str(text).strip()
    t = _BRACKET_IDS.sub("", t)
    t = _META_EQ.sub("", t)
    t = _ID_TOKEN.sub("", t)
    t = _PREFIXES.sub("", t)
    for pat, repl in _JARGON_PHRASES:
        t = re.sub(pat, repl, t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"因此不能在 多头/空头 解释间做机械平均，只能保留未决。?", "多空解释尚无法被有效裁定，只能保留未决。", t)
    t = re.sub(r"不能在 多头/空头 解释间做机械平均，只能保留未决。?", "多空解释尚无法被有效裁定，只能保留未决。", t)
    t = re.sub(r"不得把 多头/空头 条数平均成中性。?", "不能按多空条目数量机械折中。", t)
    t = re.sub(r"FA 不得补全为已确认事实。?", "报告不得把缺口补写成已确认事实。", t)
    t = re.sub(
        r"存在.{0,12}证据不足.{0,8}或未关闭的.{0,8}解释冲突.{0,20}部分接受.{0,8}或缺失。?",
        "质询尚未关闭，回应也未形成压倒性裁定。",
        t,
    )
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"[；;]{2,}", "；", t)
    t = re.sub(r"[，,]{2,}", "，", t)
    t = re.sub(r"（\s*）", "", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = t.strip(" ；;，,。.")
    parts = re.split(r"(?<=[。！？])", t)
    kept: list[str] = []
    carry = ""
    for p in parts:
        p = (carry + p).strip(" ；;，,")
        carry = ""
        if not p:
            continue
        chinese = len(re.findall(r"[\u4e00-\u9fff]", p))
        has_number = bool(re.search(r"\d", p))
        if chinese < 6 and not has_number:
            carry = p
            continue
        if chinese < 6 and has_number:
            carry = p + "；"
            continue
        if not p.endswith(("。", "！", "？", "；")):
            p += "。"
        kept.append(p)
    if carry and len(re.findall(r"[\u4e00-\u9fff]", carry)) >= 4:
        kept.append(carry if carry.endswith(("。", "！", "？", "；")) else carry + "。")
    out = "".join(kept) if kept else (t + ("。" if t and not t.endswith(("。", "！", "？")) else ""))
    out = re.sub(r"\s{2,}", " ", out).strip()
    if len(out) > max_chars:
        cut = out[: max_chars - 1]
        for sep in ("。", "；", "，"):
            idx = cut.rfind(sep)
            if idx > max_chars // 2:
                cut = cut[: idx + 1]
                break
        out = cut.rstrip("，；、") + ("…" if not cut.endswith(("。", "！", "？")) else "")
    return out


def _evidence_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["evidence_id"]: e for e in snapshot.get("evidence") or []}


def _source_label(provider: str | None) -> str:
    p = provider or ""
    if p in SOURCE_LABELS:
        return SOURCE_LABELS[p]
    if p.startswith("python.derived"):
        return "财务派生"
    if p.startswith("akshare"):
        return "行情/财务"
    return p.split(".")[0] if p else "—"


def _evidence_card_fields(e: dict[str, Any]) -> dict[str, Any]:
    subtype = e.get("subtype") or ""
    provider = (e.get("source") or {}).get("provider") or ""
    display = _metric_value_text(e)
    return {
        "metric_label": METRIC_LABELS.get(subtype, subtype or "证据"),
        "display_value": display,
        "source_label": _source_label(provider),
        "period": _period_of(e),
    }


def _evidence_briefs(ids: list[str], index: dict[str, dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for eid in ids or []:
        e = index.get(eid)
        if not e:
            continue
        val = e.get("value") or {}
        extra = _evidence_card_fields(e)
        out.append(
            {
                "evidence_id": eid,
                "claim": e.get("claim") or "",
                "subtype": e.get("subtype") or "",
                "type": e.get("evidence_type") or "",
                "source": (e.get("source") or {}).get("provider") or "",
                "date": extra["period"] or (e.get("time") or {}).get("data_date") or "",
                "value_preview": val.get("value"),
                **extra,
            }
        )
        if len(out) >= limit:
            break
    return out


def _finding_map(research: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for f in (research.get("fundamental_findings") or []) + (research.get("market_findings") or []):
        fid = f.get("finding_id")
        if fid:
            out[fid] = f
    return out


def _split_fact_interp(claim: str | None, interp: str | None) -> tuple[str, str]:
    text = claim or ""
    for sep in ("这表明", "对照结果显示", "因此", "所以"):
        if sep in text:
            a, b = text.split(sep, 1)
            return clean_prose(a, max_chars=280), clean_prose(sep + b, max_chars=220)
    return clean_prose(text, max_chars=280), clean_prose(interp, max_chars=220)


def _strength_band(assessment: str | None) -> tuple[str, str]:
    raw = assessment or "unknown"
    band = {"strong": "strong", "moderate": "moderate", "tentative": "weak", "unresolved": "unresolved"}.get(raw, "unresolved")
    label = {"strong": "较强", "moderate": "中等", "weak": "偏弱", "unresolved": "未决"}.get(band, "未决")
    return band, label


def _winner_for(resolution: str | None, bull_pos: str, bear_pos: str) -> tuple[str, str]:
    res = resolution or "unresolved"
    no_bull = (not bull_pos) or ("未对本" in bull_pos)
    no_bear = (not bear_pos) or ("未对本" in bear_pos)
    if res == "bull_supported":
        return "多头", "辩论裁定偏多头解释；该结论来自已有 resolution，而不是引用条数。"
    if res == "bear_supported":
        return "空头", "辩论裁定偏空头解释；该结论来自已有 resolution，而不是引用条数。"
    if res == "partially_resolved":
        return "部分收敛", "部分争议已经收敛，但仍不足以锁定单边解释。"
    if no_bull and not no_bear:
        return "未决", "空头有立论、多头未对本命题立论，但主裁定仍为未决，不能记作空头已获胜。"
    if no_bear and not no_bull:
        return "未决", "多头有立论、空头未对本命题立论，但主裁定仍为未决，不能记作多头已获胜。"
    return "未决", "双方都有可引用事实，但质询尚未关闭，不能把证据条数折算成胜负。"


def _claims_on_tension(debate: dict[str, Any] | None, tension_id: str, side: str) -> list[dict[str, Any]]:
    if not debate:
        return []
    pack = (debate.get(side) or {}).get("claims") or []
    return [c for c in pack if tension_id in (c.get("canonical_finding_ids") or [])]


def _dedupe_text(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        t = (x or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _period_of(e: dict[str, Any]) -> str:
    t = e.get("time") or {}
    v = e.get("value") or {}
    return str(t.get("report_date") or v.get("period") or t.get("data_date") or "")


def _latest_by_subtype(evidence: list[dict[str, Any]], subtype: str) -> dict[str, Any] | None:
    items = [e for e in evidence if e.get("subtype") == subtype]
    if not items:
        return None
    return max(items, key=lambda e: _period_of(e) or "")


def _metric_value_text(e: dict[str, Any]) -> str:
    claim = e.get("claim") or ""
    m = re.search(r"同比下降\s*([-\d.]+%)", claim)
    if m:
        return f"-{m.group(1).lstrip('-')}"
    m = re.search(r"同比(?:上升|增长)\s*([-\d.]+%)", claim)
    if m:
        return f"+{m.group(1).lstrip('+')}"
    m = re.search(r"为\s*([-\d.]+%?)(?:\s|$|元|倍)", claim)
    if m:
        return m.group(1)
    val = (e.get("value") or {}).get("value")
    unit = (e.get("value") or {}).get("unit")
    if isinstance(val, (int, float)):
        if unit == "ratio" and abs(val) <= 2:
            return f"{val * 100:.2f}%"
        if abs(val) >= 100:
            return f"{val:.2f}"
        return f"{val:.2f}"
    return ""


def _kpi_row(e: dict[str, Any] | None, label: str) -> dict[str, Any] | None:
    if not e:
        return None
    display = _metric_value_text(e)
    if not display:
        return None
    return {
        "label": label,
        "value": display,
        "period": _period_of(e),
        "evidence_id": e.get("evidence_id") or "",
        "claim": e.get("claim") or "",
        "subtype": e.get("subtype") or "",
    }


def _thesis_from_question(q: str | None) -> str:
    raw = clean_prose(q, max_chars=80)
    t = raw.rstrip("？?")
    if not t:
        return ""
    if "是否冲突" in t:
        t = t.replace("是否冲突", "需分尺度解读")
    t = t.replace("是否", "")
    t = re.sub(r"需要怎样的(.{0,24})才能成立", r"成立更依赖\1", t)
    t = re.sub(r"如何共同(.{0,12})", r"共同\1", t)
    t = re.sub(r"处于什么状态", "状态", t)
    t = re.sub(r"如何共同约束", "如何约束", t)
    t = re.sub(r"，+", "，", t).strip("， 。")
    return t


def _industry_short(profile: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> str:
    for p in profile:
        if p.get("label") == "行业" and p.get("value"):
            return str(p["value"]).replace("制造业-", "")
    ind = _latest_by_subtype(evidence, "industry")
    if not ind:
        return ""
    claim = ind.get("claim") or ""
    m = re.search(r"所属行业为\s*(.+)$", claim)
    raw = (m.group(1) if m else claim).strip()
    return raw.replace("制造业-", "")


def _compose_core_view(
    *,
    name: str,
    industry: str,
    kpis: dict[str, dict[str, Any]],
    cover_title: str,
) -> str:
    """投价报告式核心观点：数字织入段落，不堆砌「日期+指标」清单。"""
    bits: list[str] = []
    head = name or "公司"
    if industry:
        bits.append(f"{head}现有证据显示，所属行业为{industry}。")
    else:
        bits.append(f"{head}现有证据显示：")

    roe, gm = kpis.get("roe"), kpis.get("gross_margin")
    fund_period = (roe or gm or {}).get("period") or ""
    if roe and gm:
        bits.append(
            f"{fund_period} ROE、毛利率分别为 {roe['value']}/{gm['value']}，"
            "盈利能力仍处较高水平。"
        )
    elif roe:
        bits.append(f"{fund_period} ROE 为 {roe['value']}，盈利能力仍处较高水平。")
    elif gm:
        bits.append(f"{fund_period} 毛利率为 {gm['value']}，盈利能力仍处较高水平。")

    ry, ny = kpis.get("revenue_yoy"), kpis.get("net_profit_yoy")
    growth_note = _growth_phrase(ry, ny)
    if ry and ny:
        bits.append(
            f"同一报告期营业收入、归母净利润同比分别为 {ry['value']}/{ny['value']}，"
            f"{growth_note}。"
        )
    elif ry or ny:
        row = ry or ny
        label = "营业收入" if ry else "归母净利润"
        bits.append(f"同一报告期{label}同比为 {row['value']}，{growth_note}。")

    debt = kpis.get("debt_to_asset_ratio")
    if debt:
        bits.append(f"财务结构上，资产负债率为 {debt['value']}。")

    pe, pb = kpis.get("pe"), kpis.get("pb")
    asof = (pe or pb or {}).get("period") or ""
    if pe and pb:
        bits.append(f"截至 {asof}，PE(TTM)、PB 分别为 {pe['value']}/{pb['value']}。")
    elif pe:
        bits.append(f"截至 {asof}，PE(TTM) 为 {pe['value']}。")

    bits.append(
        "因此当前研究主线应对照盈利能力、增长动能与现价是否已反映不确定性；"
        "单期同比尚不足以区分周期性波动与结构性变化。"
    )
    if cover_title and cover_title not in "".join(bits):
        bits.append(f"概括而言，{cover_title}。")

    out = "".join(bits)
    out = re.sub(r"。+", "。", out)
    out = re.sub(r"显示：。", "显示：", out)
    return out


def _yoy_direction(row: dict[str, Any] | None) -> str:
    if not row:
        return "unknown"
    raw = str(row.get("value") or "")
    if raw.startswith("-") or "下降" in raw:
        return "neg"
    if raw.startswith("+"):
        return "pos"
    try:
        return "pos" if float(raw.rstrip("%")) >= 0 else "neg"
    except ValueError:
        return "unknown"


def _growth_phrase(ry: dict[str, Any] | None, ny: dict[str, Any] | None) -> str:
    rd, nd = _yoy_direction(ry), _yoy_direction(ny)
    if rd == "neg" and nd == "neg":
        return "增长端已经承压"
    if rd == "pos" and nd == "neg":
        return "营收仍在扩张，但利润端承压"
    if rd == "pos" and nd == "pos":
        # Near-zero profit growth still deserves a softer note when revenue expands.
        try:
            n = float(str((ny or {}).get("value") or "0").lstrip("+").rstrip("%"))
            if 0 <= n < 3:
                return "营收扩张较快，利润增速偏弱"
        except ValueError:
            pass
        return "营收与利润同比均为正，增长仍在扩张"
    if rd == "neg" and nd == "pos":
        return "利润仍增，但营收承压"
    return "增长态势需结合更多期数据确认"


def _cover_from_kpis(kpis: dict[str, dict[str, Any]], fallback: str) -> str:
    """When grounded research reuses a Maotai-like tension wording, retitle from KPIs."""
    rd = _yoy_direction(kpis.get("revenue_yoy"))
    nd = _yoy_direction(kpis.get("net_profit_yoy"))
    if "承压" in fallback and rd == "pos" and nd in {"pos", "unknown"}:
        try:
            n = float(str((kpis.get("net_profit_yoy") or {}).get("value") or "0").lstrip("+").rstrip("%"))
            if 0 <= n < 3:
                return "营收仍在扩张，利润增速偏弱"
        except ValueError:
            pass
        return "盈利与营收扩张并存，可持续性待核实"
    if "承压" in fallback and rd == "pos" and nd == "neg":
        return "营收扩张与利润承压并存"
    return fallback

def _compose_section_body(kicker: str, fact: str, derived: str, extra: str = "") -> str:
    parts = _dedupe_text([fact, extra, derived])
    body = "".join(p if p.endswith(("。", "！", "？")) else p + "。" for p in parts if p)
    body = clean_prose(body, max_chars=420)
    if kicker == "估值观察" and body and "预测" not in body and "合理市值" not in body:
        body = body.rstrip("。") + "。本报告不对合理市值或买卖区间作结论。"
    return body


def build_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Insight integration for the demo report. Does not change Agent judgment."""
    fa = snapshot.get("final_analyst") or {}
    j = snapshot.get("judgment") or {}
    company = snapshot.get("company") or {}
    research = snapshot.get("research") or {}
    debate = snapshot.get("debate")
    why = fa.get("why_this_judgment") or fa.get("assessment_basis") or {}
    idx = _evidence_index(snapshot)
    fmap = _finding_map(research)
    calibrated = why.get("calibrated_frame") or ""
    band, band_label = _strength_band(
        j.get("assessment_strength") or (fa.get("executive_assessment") or {}).get("assessment_strength")
    )

    findings_raw = (research.get("fundamental_findings") or []) + (research.get("market_findings") or [])
    findings: list[dict[str, Any]] = []
    for f in findings_raw:
        claim = clean_prose(f.get("claim"), max_chars=360)
        if not claim:
            continue
        findings.append(
            {
                "finding_id": f.get("finding_id"),
                "title": clean_prose(f.get("research_question") or f.get("finding_id") or "研究命题", max_chars=80),
                "claim": claim,
                "interpretation": clean_prose(f.get("interpretation"), max_chars=220),
                "numbers": list(f.get("numbers_preserved") or [])[:8],
                "evidence_ids": list(f.get("evidence_ids") or [])[:8],
            }
        )

    tensions_in = list(fa.get("tensions") or [])[:3]
    primary = tensions_in[0] if tensions_in else None
    primary_finding = fmap.get((primary or {}).get("tension_id") or "") if primary else None
    if not primary_finding and findings_raw:
        primary_finding = findings_raw[0]

    fact_part, derived_part = _split_fact_interp(
        (primary_finding or {}).get("claim"),
        (primary_finding or {}).get("interpretation"),
    )

    evidence_rows = list(snapshot.get("evidence") or [])
    kpi_specs = [
        ("roe", "ROE"),
        ("gross_margin", "毛利率"),
        ("revenue_yoy", "营收同比"),
        ("net_profit_yoy", "归母净利同比"),
        ("debt_to_asset_ratio", "资产负债率"),
        ("pe", "PE(TTM)"),
        ("pb", "PB"),
        ("close_price", "最新价"),
    ]
    kpi_table: list[dict[str, Any]] = []
    kpis: dict[str, dict[str, Any]] = {}
    for subtype, label in kpi_specs:
        row = _kpi_row(_latest_by_subtype(evidence_rows, subtype), label)
        if row:
            kpi_table.append(row)
            kpis[subtype] = row

    cover_title = _thesis_from_question((primary or {}).get("research_question") or (primary_finding or {}).get("research_question"))
    if not cover_title:
        cover_title = re.sub(r"^(这表明|对照结果显示|因此|所以)", "", derived_part or "").strip(" ，,。")
        cover_title = cover_title.split("。")[0] if cover_title else "现有证据支持有限的条件判断"
    if cover_title.startswith("事实清楚") or cover_title.startswith("基准判断"):
        cover_title = _thesis_from_question((primary or {}).get("research_question")) or "盈利与增长并存，解释框架未决"
    cover_title = _cover_from_kpis(kpis, cover_title)
    one_liner = cover_title if cover_title.endswith(("。", "！", "？")) else cover_title + "。"

    val_finding = next((f for f in findings_raw if "VALUATION" in (f.get("finding_id") or "")), None)
    balance_finding = next(
        (f for f in findings_raw if "BALANCE" in (f.get("finding_id") or "")),
        None,
    )
    cash_finding = next((f for f in findings_raw if "CASH" in (f.get("finding_id") or "")), None)
    mkt_finding = next((f for f in findings_raw if "SHORT_VS_LONG" in (f.get("finding_id") or "")), None)
    if not mkt_finding:
        mkt_finding = next((f for f in findings_raw if "PRICE_MA" in (f.get("finding_id") or "")), None)
    val_fact, val_derived = (
        _split_fact_interp((val_finding or {}).get("claim"), (val_finding or {}).get("interpretation"))
        if val_finding
        else ("", "")
    )
    bal_fact, bal_derived = (
        _split_fact_interp((balance_finding or {}).get("claim"), (balance_finding or {}).get("interpretation"))
        if balance_finding
        else ("", "")
    )
    cash_fact, _ = (
        _split_fact_interp((cash_finding or {}).get("claim"), (cash_finding or {}).get("interpretation"))
        if cash_finding
        else ("", "")
    )
    mkt_fact, mkt_derived = (
        _split_fact_interp((mkt_finding or {}).get("claim"), (mkt_finding or {}).get("interpretation"))
        if mkt_finding
        else ("", "")
    )

    sections: list[dict[str, Any]] = [
        {
            "kicker": "财务分析",
            "thesis": cover_title,
            "body": _compose_section_body("财务分析", fact_part, derived_part, "；".join(x for x in (bal_fact, cash_fact) if x)),
        },
        {
            "kicker": "估值观察",
            "thesis": _thesis_from_question((val_finding or {}).get("research_question")) or "估值成立更依赖增长恢复",
            "body": _compose_section_body("估值观察", val_fact, val_derived),
        },
    ]
    if mkt_fact or mkt_derived:
        sections.append(
            {
                "kicker": "市场结构",
                "thesis": _thesis_from_question((mkt_finding or {}).get("research_question")) or "短中期与长期均线需分尺度解读",
                "body": _compose_section_body("市场结构", mkt_fact, mkt_derived),
            }
        )

    support_ids: list[str] = []
    if primary:
        support_ids.extend(list(primary.get("decisive_evidence_ids") or []))
    if primary_finding:
        support_ids.extend(list(primary_finding.get("evidence_ids") or []))
    exec_ids = list((fa.get("executive_assessment") or {}).get("evidence_ids") or [])
    top_ids: list[str] = []
    for eid in support_ids + exec_ids:
        if eid not in top_ids:
            top_ids.append(eid)
    supporting_evidence = _evidence_briefs(top_ids, idx, limit=3)

    max_uncertainty = clean_prose(
        (primary_finding or {}).get("interpretation") or (primary or {}).get("resolution_reason"),
        max_chars=180,
    )
    if not max_uncertainty:
        for u in fa.get("uncertainty") or []:
            t = clean_prose(u.get("text"), max_chars=160)
            if t and "事实清楚" not in t:
                max_uncertainty = t
                break

    confirmed = _dedupe_text([fact_part, bal_fact, val_fact])
    unconfirmed = _dedupe_text(
        [
            derived_part if any(k in derived_part for k in ("不足以", "不能", "尚未", "未裁定", "未决", "主要矛盾")) else "",
            clean_prose((primary_finding or {}).get("interpretation"), max_chars=180),
        ]
    )
    unconfirmed = [x for x in unconfirmed if "事实清楚、解释未决" not in x]
    if not unconfirmed and primary:
        unconfirmed = [clean_prose(primary.get("resolution_reason"), max_chars=180)]

    current_supports = derived_part or fact_part or one_liner
    if band == "unresolved":
        strength_reason = "判断强度为未决，是因为核心争议的解释尚未被质询关闭，而不是因为缺少可确认事实。"
        if max_uncertainty:
            strength_reason = f"{strength_reason} {max_uncertainty}"
    elif band == "weak":
        strength_reason = "已有事实方向，但支持强度偏弱，只能给出审慎的条件判断。"
    elif band == "moderate":
        strength_reason = "证据对当前解释有中等支持，仍需保留对立解释的有效性。"
    else:
        strength_reason = "当前解释获得较强证据支持，但仍是条件判断而非交易建议。"

    key_tensions: list[dict[str, Any]] = []
    for t in tensions_in:
        fid = t.get("tension_id") or ""
        rf = fmap.get(fid) or {}
        fact, derived = _split_fact_interp(rf.get("claim"), rf.get("interpretation"))
        bull_pos = clean_prose(t.get("bull_position"), max_chars=160)
        bear_pos = clean_prose(t.get("bear_position"), max_chars=160)
        winner, winner_reason = _winner_for(t.get("resolution"), t.get("bull_position") or "", t.get("bear_position") or "")
        bull_eids: list[str] = []
        bear_eids: list[str] = []
        for c in _claims_on_tension(debate, fid, "bull"):
            bull_eids.extend(list(c.get("evidence_ids") or []))
        for c in _claims_on_tension(debate, fid, "bear"):
            bear_eids.extend(list(c.get("evidence_ids") or []))
        still_why = clean_prose(rf.get("interpretation") or t.get("resolution_reason"), max_chars=200)
        question = clean_prose(t.get("research_question") or rf.get("research_question"), max_chars=120)
        key_tensions.append(
            {
                "tension_id": fid,
                "question": question,
                "thesis": _thesis_from_question(question),
                "fact": fact,
                "derived": derived,
                "bull": bull_pos or "未对本命题立论",
                "bear": bear_pos or "未对本命题立论",
                "bull_evidence": _evidence_briefs(bull_eids, idx, limit=3),
                "bear_evidence": _evidence_briefs(bear_eids, idx, limit=3),
                "winner": winner,
                "winner_reason": winner_reason,
                "still_why": still_why,
                "resolution": t.get("resolution"),
                "resolution_label": human_label(RESOLUTION_LABELS, t.get("resolution")),
                "strength_label": human_label(STRENGTH_LABELS, t.get("assessment_strength")),
                "numbers": list((t.get("current_assessment") or {}).get("numbers_used") or rf.get("numbers_preserved") or [])[:8],
            }
        )

    profile = []
    for p in company.get("profile") or []:
        profile.append(
            {
                "label": PROFILE_LABELS.get(p.get("subtype"), p.get("subtype") or ""),
                "value": p.get("value") if p.get("value") is not None else clean_prose(p.get("claim"), max_chars=80),
                "evidence_id": p.get("evidence_id"),
            }
        )
    industry = _industry_short(profile, evidence_rows)
    core_view = _compose_core_view(
        name=str(snapshot.get("name") or snapshot.get("symbol") or ""),
        industry=industry,
        kpis=kpis,
        cover_title=cover_title,
    )
    narrative_parts = _dedupe_text([core_view] + [s["body"] for s in sections if s.get("body")])

    changers = []
    for v in (fa.get("what_would_change_my_view") or [])[:5]:
        direction = v.get("direction")
        changers.append(
            {
                "trigger": clean_prose(v.get("trigger_evidence_description"), max_chars=180),
                "effect": clean_prose(v.get("related_gap_or_boundary") or v.get("would_affect"), max_chars=140),
                "direction": direction,
                "direction_label": human_label(DIRECTION_LABELS, direction, fallback=str(direction or "")),
                "why": clean_prose(v.get("related_gap_or_boundary"), max_chars=140),
            }
        )

    risks: list[dict[str, Any]] = []
    for t in key_tensions:
        txt = t.get("still_why") or ""
        if txt and all(txt != r["text"] for r in risks):
            risks.append({"text": txt, "kind": "tension"})
        if len(risks) >= 2:
            break
    for g in fa.get("research_gaps") or []:
        text = clean_prose(g.get("text"), max_chars=140)
        if text and all(text != r["text"] for r in risks):
            risks.append({"text": text, "kind": "gap", "evidence_ids": list(g.get("evidence_ids") or [])[:2]})
        if len(risks) >= 3:
            break

    if risks:
        risk_body = "；".join(r["text"].rstrip("。") for r in risks if r.get("text"))
        if risk_body and not risk_body.endswith("。"):
            risk_body += "。"
        sections.append({"kicker": "风险因素", "thesis": "", "body": risk_body, "items": [r["text"] for r in risks]})

    key_evidence = []
    for brief in _evidence_briefs(top_ids, idx, limit=6):
        e = idx.get(brief["evidence_id"]) or {}
        if e.get("subtype") in {"stock_name", "industry", "listing_date"}:
            continue
        key_evidence.append({**brief, "type": e.get("evidence_type"), "supports": e.get("supports") or []})

    primary_tension = key_tensions[0] if key_tensions else {}
    bull_case = clean_prose(
        (primary_tension.get("bull") if primary_tension else "")
        or ((debate or {}).get("bull") or {}).get("thesis")
        or "",
        max_chars=180,
    )
    bear_case = clean_prose(
        (primary_tension.get("bear") if primary_tension else "")
        or ((debate or {}).get("bear") or {}).get("thesis")
        or "",
        max_chars=180,
    )
    key_unknown = (
        clean_prose(primary_tension.get("still_why"), max_chars=160)
        if primary_tension
        else ""
    ) or max_uncertainty or (unconfirmed[0] if unconfirmed else "")
    if key_unknown.startswith("事实清楚"):
        key_unknown = clean_prose((primary or {}).get("research_question"), max_chars=120) or key_unknown

    insight_pack = build_insights(snapshot, kpis=kpis)
    headline_insight = insight_pack.get("headline_insight") or {}
    insight_change = headline_insight.get("change") or cover_title

    research_brief = {
        "core_judgment": insight_change,
        "insight_change": insight_change,
        "insight_why": headline_insight.get("why") or [],
        "insight_meaning": headline_insight.get("meaning") or "",
        "insight_next_research": headline_insight.get("next_research") or "",
        "agent_insight": headline_insight.get("agent_insight") or "",
        "core_tension": clean_prose((primary or {}).get("research_question"), max_chars=80),
        "axis_label": human_label(AXIS_LABELS, j.get("primary_axis")),
        "bull_case": bull_case or "多头未对本命题立论",
        "bear_case": bear_case or "空头未对本命题立论",
        "key_unknown": key_unknown,
        "what_changes_view": [
            {
                "trigger": c["trigger"],
                "direction_label": c["direction_label"],
            }
            for c in changers[:4]
        ],
        "assessment_label": band_label,
        "debate_label": human_label(RESOLUTION_LABELS, j.get("debate_state")),
        "supporting_line": current_supports,
    }

    debate_view = None
    if debate:
        debate_view = {
            "bull_thesis": clean_prose(debate.get("bull", {}).get("thesis"), max_chars=220),
            "bear_thesis": clean_prose(debate.get("bear", {}).get("thesis"), max_chars=220),
            "comparisons": [
                {
                    "question": t["question"],
                    "bull": t["bull"],
                    "bear": t["bear"],
                    "bull_evidence": t["bull_evidence"],
                    "bear_evidence": t["bear_evidence"],
                    "winner": t["winner"],
                    "reason": t["winner_reason"],
                    "still_why": t["still_why"],
                }
                for t in key_tensions
            ],
            "bull_claims": [
                {
                    "title": clean_prose(c.get("claim"), max_chars=120),
                    "reasoning": clean_prose(c.get("reasoning"), max_chars=220),
                    "evidence_briefs": _evidence_briefs(list(c.get("evidence_ids") or []), idx, limit=3),
                }
                for c in debate.get("bull", {}).get("claims") or []
            ],
            "bear_claims": [
                {
                    "title": clean_prose(c.get("claim"), max_chars=120),
                    "reasoning": clean_prose(c.get("reasoning"), max_chars=220),
                    "evidence_briefs": _evidence_briefs(list(c.get("evidence_ids") or []), idx, limit=3),
                }
                for c in debate.get("bear", {}).get("claims") or []
            ],
            "chains": [
                {
                    "target": clean_prose(ch.get("target_claim"), max_chars=160),
                    "target_side": "多头" if ch.get("target_stance") == "bull" else "空头" if ch.get("target_stance") == "bear" else "",
                    "challenge": clean_prose(ch.get("argument"), max_chars=220),
                    "challenge_type": human_label(CHALLENGE_TYPE_LABELS, ch.get("challenge_type")),
                    "challenger": "多头" if ch.get("challenger") == "bull" else "空头",
                    "rebuttals": [
                        {
                            "author": "多头" if r.get("author") == "bull" else "空头",
                            "response": human_label(RESPONSE_LABELS, r.get("response_type")),
                            "argument": clean_prose(r.get("argument"), max_chars=220),
                        }
                        for r in ch.get("rebuttals") or []
                    ],
                }
                for ch in debate.get("chains") or []
            ],
            "summary": {
                "shared": [clean_prose(x, max_chars=160) for x in (debate.get("summary") or {}).get("shared_facts") or []],
                "disagreements": [
                    clean_prose(x, max_chars=160) for x in (debate.get("summary") or {}).get("core_disagreements") or []
                ],
                "unresolved": [
                    clean_prose(x, max_chars=160) for x in (debate.get("summary") or {}).get("unresolved_issues") or []
                ],
            },
        }

    numbers = list((fa.get("executive_assessment") or {}).get("numbers_used") or [])
    if not numbers and primary_finding:
        numbers = list(primary_finding.get("numbers_preserved") or [])[:8]

    return {
        "title": f"{snapshot.get('name') or snapshot.get('symbol')}深度研究报告",
        "subtitle": "条件判断备忘录 · 非交易建议",
        "symbol": snapshot.get("symbol"),
        "name": snapshot.get("name"),
        "as_of": snapshot.get("as_of"),
        "disclaimer": "本报告只整合已有 Evidence / Research / Debate，不构成买入或卖出建议；不对合理市值或评级作结论。",
        "verdict": {
            "headline": cover_title,
            "core_tension": clean_prose((primary or {}).get("research_question"), max_chars=80),
            "calibration_note": calibrated,
            "assessment_label": band_label,
            "assessment_band": band,
            "axis_label": human_label(AXIS_LABELS, j.get("primary_axis")),
            "debate_label": human_label(RESOLUTION_LABELS, j.get("debate_state")),
            "support_label": human_label(SUPPORT_LABELS, j.get("support_strength")),
            "pressure_label": human_label(PRESSURE_LABELS, j.get("pressure_level")),
            "gate_label": ((snapshot.get("gate") or {}).get("decision") or (snapshot.get("gate") or {}).get("status") or "—"),
        },
        "executive": {
            "cover_title": cover_title,
            "one_liner": one_liner,
            "core_view": core_view,
            "core_tension": clean_prose((primary or {}).get("research_question"), max_chars=80),
            "narrative": narrative_parts,
            "sections": sections,
            "kpi_table": kpi_table,
            "supporting_evidence": supporting_evidence,
            "strength_band": band,
            "strength_label": band_label,
            "max_uncertainty": max_uncertainty,
            "research_brief": research_brief,
        },
        "cover_title": cover_title,
        "core_view": core_view,
        "research_brief": research_brief,
        "sections": sections,
        "kpi_table": kpi_table,
        "executive_summary": narrative_parts,
        "anchor_numbers": numbers[:8],
        "company_profile": profile,
        "findings": findings[:8],
        "key_tensions": key_tensions,
        "debates": key_tensions,
        "judgment": {
            "current_supports": current_supports,
            "confirmed": confirmed,
            "unconfirmed": unconfirmed,
            "strength_band": band,
            "strength_label": band_label,
            "strength_reason": strength_reason,
            "calibration_note": calibrated,
        },
        "risks": risks,
        "view_changers": changers,
        "key_evidence": key_evidence,
        "debate_view": debate_view,
        "insights": insight_pack,
        "research_signals": insight_pack.get("research_signals") or [],
        "external_signals": insight_pack.get("external_signals") or [],
        "fundamental_picture": insight_pack.get("fundamental_picture") or {},
        "connections": insight_pack.get("connections") or [],
        "why": {
            "supported_facts": [clean_prose(x, max_chars=180) for x in why.get("supported_facts") or []],
            "interpretation": clean_prose(why.get("interpretation_advantage"), max_chars=160),
            "base_reason": clean_prose(why.get("reason_base_case_selected"), max_chars=260),
            "calibrated_frame": calibrated,
            "constraints": list(fa.get("constraints") or []),
        },
    }
