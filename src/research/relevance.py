"""Event relevance + research_role for Research context.

Strict industry matching: no over-broad tokens like generic '制造业'.
Uses only Evidence Pack fields. Does not delete Evidence.
"""

from __future__ import annotations

import re
from typing import Literal

from evidence.pack import EvidencePack
from evidence.schema import Evidence, EvidenceType

from research.time_context import classify_role

RelevanceBucket = Literal[
    "stock_specific",
    "industry_related",
    "macro_market",
    "irrelevant",
]

ResearchRole = Literal[
    "fundamental_core",
    "market_core",
    "industry_context",
    "macro_background",
    "event_context",
    "excluded",
]

_IRRELEVANT_TECH_HINTS = (
    "cdn",
    "gpu",
    "英伟达",
    "英伟達",
    "chatgpt",
    "openai",
    "算力租赁",
    "液冷",
    "光模块",
    "cpu云",
)

# Tokens too generic to justify industry_related
_GENERIC_BLOCKLIST = {
    "制造",
    "制造业",
    "公司",
    "股份",
    "有限",
    "集团",
    "中国",
    "行业",
    "业务",
    "产品",
    "收入",
    "利润",
    "规模",
    "市场",
    "经济",
    "发展",
    "饮料",  # too broad alone; liquor uses 白酒/酱香 explicitly
    "产业",
    "板块",
}


def pack_stock_name(pack: EvidencePack) -> str | None:
    for e in pack.evidence:
        if e.subtype == "stock_name":
            val = (e.value or {}).get("value") or (e.value or {}).get("name")
            if val:
                return str(val).strip()
            m = re.search(r"名称为\s*(.+)$", e.claim or "")
            if m:
                return m.group(1).strip()
    return None


def pack_industry_strong_tokens(pack: EvidencePack) -> list[str]:
    """Strong industry anchors only — no bare generic tokens like 制造业/市场/产业."""
    tokens: list[str] = []
    industry_text = ""
    for e in pack.evidence:
        if e.subtype == "industry":
            industry_text = str((e.value or {}).get("value") or e.claim or "")
            break

    # Profile expansions (require industry_text hit first — do not stack unrelated keywords)
    profiles: list[tuple[tuple[str, ...], list[str]]] = [
        (
            ("酒", "白酒", "饮料和精制茶"),
            ["白酒", "酱香", "浓香", "酒类", "茅台", "五粮液", "泸州老窖", "高端白酒"],
        ),
        (
            ("食品", "乳制品", "饮料制造", "调味品", "休闲食品"),
            ["食品饮料", "乳制品", "乳业", "乳制品行业", "酸奶", "奶粉", "休闲食品", "调味品"],
        ),
        (
            ("家用电器", "家电", "白色家电", "厨电"),
            ["家电", "家用电器", "白色家电", "厨电", "空调", "冰箱"],
        ),
        (
            ("汽车零部件", "汽车制造", "整车", "新能源汽车"),
            ["汽车零部件", "整车", "新能源汽车", "汽车产业链", "汽车销量"],
        ),
        (
            ("专用设备", "通用设备", "工程机械", "机械设备"),
            ["工程机械", "专用设备", "通用设备", "机械设备", "机床"],
        ),
        (
            ("软件", "互联网", "信息技术", "计算机", "云计算"),
            ["软件", "互联网", "云计算", "SaaS", "产业互联网", "在线服务"],
        ),
        (
            ("半导体", "集成电路", "芯片", "电子制造"),
            ["半导体", "集成电路", "芯片", "晶圆", "封测"],
        ),
        (
            ("通信设备", "通信", "5G"),
            ["通信设备", "5G", "基站", "光通信"],
        ),
    ]
    for keys, extra in profiles:
        if any(k in industry_text for k in keys):
            tokens.extend(extra)

    # Path segments ≥4 chars, not blocklisted (cross-industry fallback)
    for part in re.split(r"[-/、，,\s]+", industry_text):
        part = part.strip()
        if len(part) >= 4 and part not in _GENERIC_BLOCKLIST and part not in tokens:
            tokens.append(part)

    # Main-business segments: keep only parts that overlap strong tokens / profile anchors
    strong_hints = set(tokens)
    for e in pack.evidence:
        if e.subtype != "main_business_segment":
            continue
        text = str((e.value or {}).get("segment") or (e.value or {}).get("value") or e.claim or "")
        for part in re.split(r"[-/、，,\s]+", text):
            part = part.strip()
            if len(part) < 2 or part in _GENERIC_BLOCKLIST:
                continue
            if part in strong_hints or any(t in part or part in t for t in strong_hints):
                if part not in tokens:
                    tokens.append(part)

    seen = set()
    out = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def classify_relevance(evidence: Evidence, pack: EvidencePack) -> RelevanceBucket:
    role = classify_role(evidence)
    if role in {"financial_statement", "market_spot", "market_derived", "expectation", "company_profile"}:
        return "stock_specific"
    if role == "company_event":
        return "stock_specific"
    if role == "macro_news":
        return "macro_market"

    claim_raw = evidence.claim or ""
    claim = claim_raw.lower()
    code = (pack.stock_code or "").strip()
    name = pack_stock_name(pack) or ""

    # Stock-specific: name or code must appear in claim text
    if code and code in claim_raw:
        return "stock_specific"
    if name and (name in claim_raw or name.lower() in claim):
        return "stock_specific"
    # Aliases for 茅台 when pack name contains it
    if "茅台" in name and "茅台" in claim_raw:
        return "stock_specific"

    if any(h in claim for h in _IRRELEVANT_TECH_HINTS):
        return "irrelevant"

    # Industry: strong tokens only
    for tok in pack_industry_strong_tokens(pack):
        if tok and tok in claim_raw:
            return "industry_related"

    if role == "industry_news":
        # subtype alone is not enough without strong token hit
        return "macro_market"

    macro_hints = (
        "北向",
        "沪深",
        "央行",
        "宏观",
        "社融",
        "cpi",
        "pmi",
        "美联储",
        "国债",
        "大盘",
        "两市",
        "外汇局",
        "经常账户",
        "顺差",
        "中小规模跨国",
    )
    if any(h.lower() in claim or h in claim_raw for h in macro_hints):
        return "macro_market"

    # Cross-sector flash without our strong tokens → irrelevant (not industry_related via 产业/市场)
    foreign_sector_hints = (
        "白酒",
        "调味品",
        "家电",
        "半导体",
        "芯片",
        "晶圆",
        "云计算",
        "SaaS",
        "新能源汽车",
        "汽车零部件",
        "工程机械",
    )
    our_tokens = set(pack_industry_strong_tokens(pack))
    if any(h in claim_raw for h in foreign_sector_hints) and not any(t in claim_raw for t in our_tokens):
        return "irrelevant"

    # Other listed-company flashes without our name → irrelevant to this research
    if evidence.evidence_type == EvidenceType.EVENT and role == "news_flash":
        other_co = re.search(
            r"(?:\*?ST)?[\u4e00-\u9fff]{2,}(?:股份|科技|集团|银行|证券|电子|汽车|通信)?",
            claim_raw,
        )
        # Explicit peer-company / ST flashes that are not our stock
        if re.search(r"\*?\*?ST[\u4e00-\u9fff]{2,}", claim_raw) and (not name or name not in claim_raw):
            return "irrelevant"
        if other_co and (not name or name not in claim_raw):
            # If claim looks like another company's corporate flash, exclude
            if any(k in claim_raw for k in ("定点", "预亏", "亏损", "中标", "签订", "收购", "收购合同", "中标公告")):
                return "irrelevant"
            if re.search(r"[\u4e00-\u9fff]{2,}(?:股份|科技|集团)", claim_raw):
                return "irrelevant"
        if evidence.subtype == "market_news":
            return "macro_market"
        return "irrelevant"

    return "macro_market"


def assign_research_role(
    evidence: Evidence,
    pack: EvidencePack,
    *,
    agent: str = "fundamental",
    relevance: RelevanceBucket | None = None,
) -> ResearchRole:
    rel = relevance or classify_relevance(evidence, pack)
    role = classify_role(evidence)
    if rel == "irrelevant":
        return "excluded"
    if rel == "macro_market":
        return "macro_background"
    if rel == "industry_related":
        return "industry_context"
    if role == "company_event":
        return "event_context"
    if agent == "fundamental":
        if role in {"financial_statement", "company_profile", "expectation"}:
            return "fundamental_core"
        if role in {"market_spot", "market_derived"}:
            return "market_core"  # valuation anchors usable by fundamental
        return "fundamental_core"
    # market agent
    if role in {"market_spot", "market_derived", "expectation"}:
        return "market_core"
    if role == "news_flash" and rel == "stock_specific":
        return "market_core"
    if role == "news_flash" and rel == "industry_related":
        return "industry_context"
    return "market_core"
