"""Normalize verified raw sources into Evidence / EvidencePack. No LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .claims import (
    claim_announcement,
    claim_derived_ratio,
    claim_derived_yoy,
    claim_eps_consensus,
    claim_fact_metric,
    claim_news,
    claim_shareholder,
    claim_technical,
)
from .dedup import mark_duplicates, short_hash
from .freshness import compute_freshness
from .pack import EvidencePack
from .schema import (
    Evidence,
    EvidenceSource,
    EvidenceTime,
    EvidenceType,
    Reliability,
    utc_now_iso,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"

SINA_BLOCKLIST = {"新浪财经", "sina", "Sina"}


def _meta_get(obj: dict[str, Any], key: str, default=None):
    meta = obj.get("_meta") if isinstance(obj, dict) else None
    if isinstance(meta, dict) and key in meta:
        return meta.get(key)
    return obj.get(key, default) if isinstance(obj, dict) else default


def _make_id(provider: str, etype: str, stock: str | None, anchor: str, *parts: str) -> str:
    stock_part = stock or "macro"
    digest = short_hash(provider, etype, stock_part, anchor, *parts)
    safe_anchor = "".join(ch if ch.isalnum() else "" for ch in (anchor or ""))[:10] or "na"
    return f"{provider}_{etype}_{stock_part}_{safe_anchor}_{digest}"


class EvidenceNormalizer:
    """Convert raw AKShare / market-info payloads into Evidence objects."""

    def normalize_bundle(self, bundle: dict[str, Any]) -> list[Evidence]:
        stock = bundle.get("stock_code") or "unknown"
        retrieved_at = bundle.get("retrieved_at") or utc_now_iso()
        raw = (bundle.get("layers") or {}).get("raw") or {}
        derived = (bundle.get("layers") or {}).get("derived") or {}
        out: list[Evidence] = []
        out.extend(self._from_company_info(raw.get("company_info") or {}, stock, retrieved_at))
        out.extend(self._from_financials(raw.get("financials") or {}, stock, retrieved_at))
        out.extend(self._from_main_business(raw.get("main_business") or {}, stock, retrieved_at))
        out.extend(self._from_snapshot(raw.get("market_snapshot") or {}, stock, retrieved_at))
        out.extend(self._from_derived(derived, stock, retrieved_at))
        return out

    def normalize_market_information(self, market_info: dict[str, Any]) -> list[Evidence]:
        stock = market_info.get("stock_code")
        retrieved_at = market_info.get("retrieved_at") or utc_now_iso()
        out: list[Evidence] = []

        # Announcements
        for item in market_info.get("announcements") or []:
            out.append(self._event_from_announcement(item, stock, retrieved_at))

        # Consensus expectations
        for item in market_info.get("consensus") or []:
            out.append(self._expectation_from_consensus(item, stock, retrieved_at))

        # Events block (e.g. holder_change samples)
        for event in market_info.get("events") or []:
            if event.get("type") == "holder_change":
                for row in event.get("sample") or []:
                    out.append(self._event_from_holder_row(row, stock, retrieved_at))

        # News: skip Sina from core evidence layer
        for item in market_info.get("news") or []:
            source = str(item.get("source") or "")
            if any(x.lower() in source.lower() for x in SINA_BLOCKLIST):
                continue
            # Keep Eastmoney / CLS style items
            out.append(self._event_from_news(item, stock, retrieved_at))

        return [e for e in out if e is not None]

    def normalize_eastmoney(self, em: dict[str, Any]) -> list[Evidence]:
        stock = em.get("stock_code")
        retrieved_at = em.get("retrieved_at") or utc_now_iso()
        out: list[Evidence] = []
        ann = em.get("announcements") or {}
        for item in ann.get("sample") or []:
            out.append(self._event_from_announcement(item, stock, retrieved_at))
        holder = em.get("holder_change") or {}
        if holder.get("ok"):
            for row in holder.get("sample") or []:
                out.append(self._event_from_holder_row(row, stock, retrieved_at))
        return out

    def normalize_cls(self, cls: dict[str, Any]) -> list[Evidence]:
        retrieved_at = cls.get("retrieved_at") or utc_now_iso()
        stock = cls.get("stock_code")
        out: list[Evidence] = []
        summary = cls.get("summary") or {}
        # Prefer stock-related; also keep a capped set of macro/industry/market flashes
        samples = []
        samples.extend(summary.get("related_30_sample") or [])
        samples.extend(summary.get("related_90_sample") or [])
        market_samples = summary.get("market_30_sample") or []
        # keep macro/industry first, then general market (cap)
        prioritized = [x for x in market_samples if x.get("category") in {"macro", "industry"}]
        prioritized += [x for x in market_samples if x.get("category") not in {"macro", "industry"}]
        samples.extend(prioritized[:20])

        # Also take from v1_roll items if present (capped)
        v1_items = (cls.get("v1_roll") or {}).get("items") or []
        related = [x for x in v1_items if x.get("stock_related")]
        samples.extend(related)
        samples.extend([x for x in v1_items if x.get("category") in {"macro", "industry"}][:15])

        seen = set()
        for item in samples:
            key = (item.get("title"), item.get("published_at"), item.get("url"))
            if key in seen:
                continue
            seen.add(key)
            out.append(self._event_from_news(item, stock if item.get("stock_related") else None, retrieved_at, default_provider="cls"))
        return out

    def normalize_ths(self, ths: dict[str, Any]) -> list[Evidence]:
        stock = ths.get("stock_code")
        retrieved_at = ths.get("retrieved_at") or utc_now_iso()
        out = []
        for item in ths.get("consensus_normalized") or []:
            out.append(self._expectation_from_consensus(item, stock, retrieved_at))
        return out

    # ------------------------------------------------------------------
    # builders
    # ------------------------------------------------------------------

    def _from_company_info(self, info: dict[str, Any], stock: str, retrieved_at: str) -> list[Evidence]:
        provider = str(_meta_get(info, "source") or "akshare")
        out = []
        mapping = [
            ("stock_name", "股票名称", info.get("stock_name"), "text"),
            ("industry", "所属行业", info.get("industry"), "text"),
            ("listing_date", "上市日期", info.get("listing_date"), "text"),
            ("total_shares", "总股本", info.get("total_shares"), "count"),
            ("float_shares", "流通股本", info.get("float_shares"), "count"),
            ("total_market_cap", "总市值", info.get("total_market_cap"), "money"),
        ]
        data_date = _meta_get(info, "data_date")
        for subtype, label, value, hint in mapping:
            if value is None or value == "":
                continue
            claim = (
                f"{label}为 {value}"
                if hint == "text"
                else claim_fact_metric(label, value, unit_hint="count" if hint == "count" else "")
            )
            out.append(
                Evidence(
                    evidence_id=_make_id("akshare", "fact", stock, subtype, str(value)),
                    stock_code=stock,
                    evidence_type=EvidenceType.FACT,
                    subtype=subtype,
                    claim=claim,
                    value={"metric": subtype, "value": value, "unit": hint},
                    source=EvidenceSource(
                        provider=provider,
                        source_type="company_info",
                        url=None,
                        retrieved_at=retrieved_at,
                    ),
                    time=EvidenceTime(data_date=data_date, retrieved_at=retrieved_at),
                    freshness=compute_freshness(
                        evidence_type=EvidenceType.FACT,
                        subtype=subtype,
                        retrieved_at=retrieved_at,
                    ),
                    reliability=Reliability.HIGH,
                    metadata={"layer": "raw.company_info"},
                )
            )
        return out

    def _from_financials(self, financials: dict[str, Any], stock: str, retrieved_at: str) -> list[Evidence]:
        out: list[Evidence] = []
        income_items = (financials.get("income_statement") or {}).get("items") or []
        balance_items = (financials.get("balance_sheet") or {}).get("items") or []
        cash_items = (financials.get("cash_flow") or {}).get("items") or []

        def pick_periods(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            if not items:
                return []
            annual = [x for x in items if str(x.get("report_date") or "").endswith("-12-31")]
            latest = items[0]
            chosen = []
            if annual:
                chosen.append(annual[0])
                if len(annual) > 1:
                    chosen.append(annual[1])
            if latest not in chosen:
                chosen.append(latest)
            # unique by report_date
            seen = set()
            uniq = []
            for row in chosen:
                rd = row.get("report_date")
                if rd in seen:
                    continue
                seen.add(rd)
                uniq.append(row)
            return uniq

        income_map = [
            ("operating_revenue", "营业收入", ""),
            ("operating_cost", "营业成本", ""),
            ("operating_profit", "营业利润", ""),
            ("net_profit_parent", "归母净利润", ""),
            ("gross_profit", "毛利", ""),
            ("eps_basic", "基本每股收益", "price"),
        ]
        for row in pick_periods(income_items):
            report_date = row.get("report_date")
            src = str(_meta_get(row, "source") or "akshare.stock_profit_sheet_by_report_em")
            for subtype, label, hint in income_map:
                val = row.get(subtype)
                if val is None:
                    continue
                out.append(
                    Evidence(
                        evidence_id=_make_id("akshare", "fact", stock, str(report_date), subtype),
                        stock_code=stock,
                        evidence_type=EvidenceType.FACT,
                        subtype=subtype,
                        claim=claim_fact_metric(label, val, period=report_date, unit_hint=hint),
                        value={
                            "metric": subtype,
                            "value": val,
                            "unit": "CNY" if hint != "price" else "CNY/share",
                            "period": report_date,
                        },
                        source=EvidenceSource(provider=src, source_type="income_statement", retrieved_at=retrieved_at),
                        time=EvidenceTime(report_date=report_date, retrieved_at=retrieved_at),
                        freshness=compute_freshness(
                            evidence_type=EvidenceType.FACT,
                            subtype=subtype,
                            retrieved_at=retrieved_at,
                        ),
                        reliability=Reliability.HIGH,
                        metadata={"statement": "income_statement"},
                    )
                )

        balance_map = [
            ("total_assets", "总资产"),
            ("total_liabilities", "总负债"),
            ("total_equity", "净资产(归母权益)"),
            ("cash_and_equivalents", "货币资金"),
            ("accounts_receivable", "应收账款"),
            ("inventory", "存货"),
        ]
        for row in pick_periods(balance_items):
            report_date = row.get("report_date")
            src = str(_meta_get(row, "source") or "akshare.stock_balance_sheet_by_report_em")
            for subtype, label in balance_map:
                val = row.get(subtype)
                if val is None:
                    continue
                out.append(
                    Evidence(
                        evidence_id=_make_id("akshare", "fact", stock, str(report_date), subtype),
                        stock_code=stock,
                        evidence_type=EvidenceType.FACT,
                        subtype=subtype,
                        claim=claim_fact_metric(label, val, period=report_date),
                        value={"metric": subtype, "value": val, "unit": "CNY", "period": report_date},
                        source=EvidenceSource(provider=src, source_type="balance_sheet", retrieved_at=retrieved_at),
                        time=EvidenceTime(report_date=report_date, retrieved_at=retrieved_at),
                        freshness=compute_freshness(
                            evidence_type=EvidenceType.FACT,
                            subtype=subtype,
                            retrieved_at=retrieved_at,
                        ),
                        reliability=Reliability.HIGH,
                        metadata={"statement": "balance_sheet"},
                    )
                )

        cash_map = [
            ("operating_cash_flow", "经营活动现金流"),
            ("investing_cash_flow", "投资活动现金流"),
            ("financing_cash_flow", "融资活动现金流"),
        ]
        for row in pick_periods(cash_items):
            report_date = row.get("report_date")
            src = str(_meta_get(row, "source") or "akshare.stock_cash_flow_sheet_by_report_em")
            for subtype, label in cash_map:
                val = row.get(subtype)
                if val is None:
                    continue
                out.append(
                    Evidence(
                        evidence_id=_make_id("akshare", "fact", stock, str(report_date), subtype),
                        stock_code=stock,
                        evidence_type=EvidenceType.FACT,
                        subtype=subtype,
                        claim=claim_fact_metric(label, val, period=report_date),
                        value={"metric": subtype, "value": val, "unit": "CNY", "period": report_date},
                        source=EvidenceSource(provider=src, source_type="cash_flow", retrieved_at=retrieved_at),
                        time=EvidenceTime(report_date=report_date, retrieved_at=retrieved_at),
                        freshness=compute_freshness(
                            evidence_type=EvidenceType.FACT,
                            subtype=subtype,
                            retrieved_at=retrieved_at,
                        ),
                        reliability=Reliability.HIGH,
                        metadata={"statement": "cash_flow"},
                    )
                )
        return out

    def _from_main_business(self, mb: dict[str, Any], stock: str, retrieved_at: str) -> list[Evidence]:
        out = []
        latest = mb.get("latest_report_date")
        items = mb.get("items") or []
        # keep product-category rows for latest report, top by revenue_ratio
        rows = [x for x in items if x.get("report_date") == latest and x.get("category_type") == "按产品分类"]
        rows = sorted(rows, key=lambda x: (x.get("revenue_ratio") or 0), reverse=True)[:5]
        for row in rows:
            seg = row.get("business_segment")
            ratio = row.get("revenue_ratio")
            revenue = row.get("revenue")
            gm = row.get("gross_margin")
            claim = (
                f"{latest} 主营构成「{seg}」收入 {_fmt_or(revenue)}，占比 "
                f"{(ratio or 0)*100:.2f}%，毛利率 {(gm or 0)*100:.2f}%"
            )
            out.append(
                Evidence(
                    evidence_id=_make_id("akshare", "fact", stock, str(latest), "segment", str(seg)),
                    stock_code=stock,
                    evidence_type=EvidenceType.FACT,
                    subtype="main_business_segment",
                    claim=claim,
                    value={
                        "metric": "main_business_segment",
                        "business_segment": seg,
                        "revenue": revenue,
                        "revenue_ratio": ratio,
                        "gross_margin": gm,
                        "period": latest,
                    },
                    source=EvidenceSource(
                        provider=str(_meta_get(row, "source") or "akshare.stock_zygc_em"),
                        source_type="main_business",
                        retrieved_at=retrieved_at,
                    ),
                    time=EvidenceTime(report_date=latest, retrieved_at=retrieved_at),
                    freshness=compute_freshness(
                        evidence_type=EvidenceType.FACT,
                        subtype="main_business_segment",
                        retrieved_at=retrieved_at,
                    ),
                    reliability=Reliability.HIGH,
                    metadata={"category_type": row.get("category_type")},
                )
            )
        return out

    def _from_snapshot(self, snap: dict[str, Any], stock: str, retrieved_at: str) -> list[Evidence]:
        if not snap:
            return []
        data_date = snap.get("data_date")
        provider = str(_meta_get(snap, "source") or "akshare.stock_value_em")
        fields = [
            ("latest_price", "最新价格", "price"),
            ("pe", "市盈率PE(TTM)", ""),
            ("pb", "市净率PB", ""),
            ("ps", "市销率PS", ""),
            ("total_market_cap", "总市值", ""),
            ("float_market_cap", "流通市值", ""),
            ("turnover_rate", "换手率", "ratio_pct"),
        ]
        out = []
        for subtype, label, hint in fields:
            val = snap.get(subtype)
            if val is None:
                continue
            if hint == "ratio_pct":
                claim = f"{data_date + ' ' if data_date else ''}{label}为 {float(val):.4f}%"
            elif hint == "price":
                claim = claim_fact_metric(label, val, period=data_date, unit_hint="price")
            else:
                claim = claim_fact_metric(label, val, period=data_date)
            out.append(
                Evidence(
                    evidence_id=_make_id("akshare", "fact", stock, str(data_date or "snap"), subtype),
                    stock_code=stock,
                    evidence_type=EvidenceType.FACT,
                    subtype=subtype if subtype != "latest_price" else "close_price",
                    claim=claim,
                    value={
                        "metric": subtype,
                        "value": val,
                        "unit": "CNY" if hint == "price" else ("percent" if hint == "ratio_pct" else "ratio_or_cny"),
                        "period": data_date,
                    },
                    source=EvidenceSource(provider=provider, source_type="market_snapshot", retrieved_at=retrieved_at),
                    time=EvidenceTime(data_date=data_date, retrieved_at=retrieved_at),
                    freshness=compute_freshness(
                        evidence_type=EvidenceType.FACT,
                        subtype="close_price",
                        reference_time=data_date,
                        retrieved_at=retrieved_at,
                    )
                    if subtype in {"latest_price", "turnover_rate"}
                    else compute_freshness(
                        evidence_type=EvidenceType.FACT,
                        subtype=subtype,
                        retrieved_at=retrieved_at,
                    ),
                    reliability=Reliability.HIGH,
                    metadata={"layer": "raw.market_snapshot"},
                )
            )
        return out

    def _from_derived(self, derived: dict[str, Any], stock: str, retrieved_at: str) -> list[Evidence]:
        out: list[Evidence] = []
        fund = (derived.get("fundamentals") or {}).get("latest") or {}
        if fund:
            report_date = fund.get("report_date")
            provider = str(_meta_get(fund, "source") or "python.derived")
            yoy_fields = [
                ("revenue_yoy", "营业收入"),
                ("net_profit_yoy", "归母净利润"),
            ]
            for subtype, label in yoy_fields:
                val = fund.get(subtype)
                out.append(
                    Evidence(
                        evidence_id=_make_id("derived", "derived", stock, str(report_date), subtype),
                        stock_code=stock,
                        evidence_type=EvidenceType.DERIVED,
                        subtype=subtype,
                        claim=claim_derived_yoy(label, val, period=report_date),
                        value={"metric": subtype, "value": val, "unit": "ratio", "period": report_date},
                        source=EvidenceSource(provider=provider, source_type="derived_fundamentals", retrieved_at=retrieved_at),
                        time=EvidenceTime(report_date=report_date, retrieved_at=retrieved_at),
                        freshness=compute_freshness(
                            evidence_type=EvidenceType.DERIVED,
                            subtype=subtype,
                            retrieved_at=retrieved_at,
                        ),
                        reliability=Reliability.HIGH,
                        metadata={
                            "formula": {
                                "revenue_yoy": "(revenue_t - revenue_t-1) / abs(revenue_t-1)",
                                "net_profit_yoy": "(np_t - np_t-1) / abs(np_t-1)",
                            }.get(subtype),
                            "inputs": fund.get("_inputs"),
                        },
                    )
                )
            ratio_fields = [
                ("gross_margin", "毛利率"),
                ("net_margin", "净利率"),
                ("roe", "ROE"),
                ("debt_to_asset_ratio", "资产负债率"),
                ("ocf_to_net_profit", "经营现金流/净利润"),
            ]
            formulas = {
                "gross_margin": "(revenue - operating_cost) / revenue",
                "net_margin": "net_profit_parent / revenue",
                "roe": "net_profit_parent / ending_equity",
                "debt_to_asset_ratio": "total_liabilities / total_assets",
                "ocf_to_net_profit": "operating_cash_flow / net_profit_parent",
            }
            for subtype, label in ratio_fields:
                val = fund.get(subtype)
                if val is None:
                    continue
                out.append(
                    Evidence(
                        evidence_id=_make_id("derived", "derived", stock, str(report_date), subtype),
                        stock_code=stock,
                        evidence_type=EvidenceType.DERIVED,
                        subtype=subtype,
                        claim=claim_derived_ratio(label, val, period=report_date),
                        value={"metric": subtype, "value": val, "unit": "ratio", "period": report_date},
                        source=EvidenceSource(provider=provider, source_type="derived_fundamentals", retrieved_at=retrieved_at),
                        time=EvidenceTime(report_date=report_date, retrieved_at=retrieved_at),
                        freshness=compute_freshness(
                            evidence_type=EvidenceType.DERIVED,
                            subtype=subtype,
                            retrieved_at=retrieved_at,
                        ),
                        reliability=Reliability.HIGH,
                        metadata={"formula": formulas.get(subtype), "inputs": fund.get("_inputs")},
                    )
                )

        tech = (derived.get("technicals") or {}).get("latest") or {}
        if tech:
            data_date = tech.get("data_date")
            provider = str(_meta_get(tech, "source") or "python.derived")
            labels = {
                "ma5": "MA5",
                "ma20": "MA20",
                "ma60": "MA60",
                "ma250": "MA250",
                "macd_dif": "MACD DIF",
                "macd_dea": "MACD DEA",
                "macd_hist": "MACD HIST",
                "rsi_14": "RSI(14)",
                "high_52w": "52周最高价",
                "low_52w": "52周最低价",
                "price_position_in_52w_range": "当前价格在52周区间中的位置",
                "close": "收盘价",
            }
            for subtype, label in labels.items():
                val = tech.get(subtype)
                if val is None:
                    continue
                out.append(
                    Evidence(
                        evidence_id=_make_id("derived", "derived", stock, str(data_date), subtype),
                        stock_code=stock,
                        evidence_type=EvidenceType.DERIVED if subtype != "close" else EvidenceType.FACT,
                        subtype=subtype if subtype != "close" else "close_price",
                        claim=claim_technical(label, val, data_date=data_date),
                        value={"metric": subtype, "value": val, "unit": "price_or_ratio", "period": data_date},
                        source=EvidenceSource(provider=provider, source_type="derived_technicals", retrieved_at=retrieved_at),
                        time=EvidenceTime(data_date=data_date, retrieved_at=retrieved_at),
                        freshness=compute_freshness(
                            evidence_type=EvidenceType.DERIVED if subtype != "close" else EvidenceType.FACT,
                            subtype=subtype,
                            reference_time=data_date,
                            retrieved_at=retrieved_at,
                        ),
                        reliability=Reliability.HIGH,
                        metadata={
                            "formula": {
                                "ma5": "SMA(close,5)",
                                "ma20": "SMA(close,20)",
                                "ma60": "SMA(close,60)",
                                "ma250": "SMA(close,250)",
                                "macd_dif": "EMA12-EMA26",
                                "macd_dea": "EMA9(DIF)",
                                "macd_hist": "(DIF-DEA)*2",
                                "rsi_14": "RSI(14)",
                                "price_position_in_52w_range": "(close-low52)/(high52-low52)",
                            }.get(subtype)
                        },
                    )
                )
        return out

    def _event_from_announcement(self, item: dict[str, Any], stock: str | None, retrieved_at: str) -> Evidence:
        title = item.get("title") or ""
        published = item.get("published_at")
        url = item.get("url")
        return Evidence(
            evidence_id=_make_id("eastmoney", "event", stock, str(published or "")[:10], "ann", title[:40]),
            stock_code=stock,
            evidence_type=EvidenceType.EVENT,
            subtype="announcement",
            claim=claim_announcement(title, published),
            value={
                "title": title,
                "content": item.get("content") or "",
                "category": item.get("category") or "company",
                "column_names": item.get("column_names"),
            },
            source=EvidenceSource(
                provider="eastmoney",
                source_type="announcement",
                url=url,
                retrieved_at=retrieved_at,
                published_at=published,
            ),
            time=EvidenceTime(published_at=published, retrieved_at=retrieved_at),
            freshness=compute_freshness(
                evidence_type=EvidenceType.EVENT,
                reference_time=published,
                retrieved_at=retrieved_at,
            ),
            reliability=Reliability.HIGH,
            metadata={"event_category": "company"},
        )

    def _event_from_holder_row(self, row: dict[str, Any], stock: str | None, retrieved_at: str) -> Evidence:
        holder = row.get("HOLDER_NAME") or row.get("holder_name") or "股东"
        direction = row.get("DIRECTION") or row.get("direction") or "变动"
        change_num = row.get("CHANGE_NUM") if row.get("CHANGE_NUM") is not None else row.get("change_num")
        notice = row.get("NOTICE_DATE") or row.get("published_at")
        published = str(notice)[:19] if notice else None
        claim = claim_shareholder(str(holder), str(direction), change_num, published)
        return Evidence(
            evidence_id=_make_id(
                "eastmoney",
                "event",
                stock,
                str(published or "")[:10],
                "holder",
                str(holder)[:20],
                str(direction),
                str(change_num),
            ),
            stock_code=stock or row.get("SECURITY_CODE"),
            evidence_type=EvidenceType.EVENT,
            subtype="shareholder_change",
            claim=claim,
            value={
                "title": claim,
                "holder_name": holder,
                "direction": direction,
                "change_num": change_num,
                "change_rate": row.get("CHANGE_RATE"),
                "hold_ratio": row.get("HOLD_RATIO"),
                "trade_average_price": row.get("TRADE_AVERAGE_PRICE") or row.get("REAL_PRICE"),
                "start_date": row.get("START_DATE"),
                "end_date": row.get("END_DATE"),
                "category": "shareholder",
                "raw": {k: row.get(k) for k in ("MARKET", "AFTER_HOLDER_NUM", "AFTER_CHANGE_RATE")},
            },
            source=EvidenceSource(
                provider="eastmoney",
                source_type="shareholder_change",
                url=None,
                retrieved_at=retrieved_at,
                published_at=published,
            ),
            time=EvidenceTime(published_at=published, data_date=str(row.get("TRADE_DATE") or "")[:10] or None, retrieved_at=retrieved_at),
            freshness=compute_freshness(
                evidence_type=EvidenceType.EVENT,
                reference_time=published,
                retrieved_at=retrieved_at,
            ),
            reliability=Reliability.HIGH,
            metadata={"event_category": "shareholder"},
        )

    def _event_from_news(
        self,
        item: dict[str, Any],
        stock: str | None,
        retrieved_at: str,
        default_provider: str | None = None,
    ) -> Evidence:
        title = item.get("title") or ""
        published = item.get("published_at")
        source_name = str(item.get("source") or default_provider or "unknown")
        category = item.get("category") or "unknown"
        provider = "cls" if "财联社" in source_name or default_provider == "cls" else (
            "eastmoney" if "东方财富" in source_name or "eastmoney" in source_name.lower() else source_name
        )
        subtype_map = {
            "company": "company_news",
            "shareholder": "shareholder_change",
            "industry": "industry_news",
            "macro": "macro_news",
            "market": "market_news",
            "unknown": "market_news",
        }
        subtype = subtype_map.get(str(category), "market_news")
        reliability = Reliability.MEDIUM_HIGH if provider in {"cls", "eastmoney"} else Reliability.MEDIUM
        return Evidence(
            evidence_id=_make_id(provider, "event", stock, str(published or "")[:10], subtype, title[:40]),
            stock_code=stock or item.get("stock_code"),
            evidence_type=EvidenceType.EVENT,
            subtype=subtype,
            claim=claim_news(title, published, str(category)),
            value={
                "title": title,
                "content": item.get("content") or "",
                "category": category,
                "matched_keywords": item.get("matched_keywords"),
            },
            source=EvidenceSource(
                provider=provider,
                source_type="news_flash" if provider == "cls" else "news",
                url=item.get("url"),
                retrieved_at=retrieved_at,
                published_at=published,
            ),
            time=EvidenceTime(published_at=published, retrieved_at=retrieved_at),
            freshness=compute_freshness(
                evidence_type=EvidenceType.EVENT,
                reference_time=published,
                retrieved_at=retrieved_at,
            ),
            reliability=reliability,
            metadata={"event_category": category, "raw_source_label": source_name},
        )

    def _expectation_from_consensus(self, item: dict[str, Any], stock: str | None, retrieved_at: str) -> Evidence:
        year = item.get("forecast_year")
        value = item.get("value")
        inst = item.get("institution_count")
        updated = item.get("updated_at")
        metric = str(item.get("metric") or "EPS").upper()
        subtype = "eps_consensus" if metric == "EPS" else "net_profit_consensus"
        return Evidence(
            evidence_id=_make_id("ths", "expectation", stock, str(year), subtype, str(value)),
            stock_code=stock or item.get("stock_code"),
            evidence_type=EvidenceType.EXPECTATION,
            subtype=subtype,
            claim=claim_eps_consensus(year, value, inst, updated),
            value={
                "metric": metric,
                "forecast_year": year,
                "value": value,
                "min_value": item.get("min_value"),
                "max_value": item.get("max_value"),
                "institution_count": inst,
                "unit": "CNY/share" if metric == "EPS" else "CNY",
            },
            source=EvidenceSource(
                provider="tonghuashun",
                source_type="consensus_estimate",
                url=f"https://basic.10jqka.com.cn/new/{stock or item.get('stock_code')}/worth.html",
                retrieved_at=retrieved_at,
                updated_at=updated,
            ),
            time=EvidenceTime(data_date=updated, retrieved_at=retrieved_at),
            freshness=compute_freshness(
                evidence_type=EvidenceType.EXPECTATION,
                subtype=subtype,
                retrieved_at=retrieved_at,
            ),
            reliability=Reliability.MEDIUM_HIGH,
            metadata={"raw_row": item.get("raw_row")},
        )


def _fmt_or(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(num) >= 1e8:
        return f"{num/1e8:.2f} 亿元"
    return f"{num:.2f}"


def build_evidence_pack(
    *,
    symbol: str = "600519",
    bundle_path: str | Path | None = None,
    market_info_path: str | Path | None = None,
    eastmoney_path: str | Path | None = None,
    cls_path: str | Path | None = None,
    ths_path: str | Path | None = None,
) -> EvidencePack:
    """Build EvidencePack from verified example JSON files."""
    symbol = symbol.strip()
    bundle_path = Path(bundle_path or EXAMPLES / f"{symbol}_bundle.json")
    market_info_path = Path(market_info_path or EXAMPLES / f"{symbol}_market_information.json")
    eastmoney_path = Path(eastmoney_path or EXAMPLES / f"{symbol}_eastmoney_test.json")
    cls_path = Path(cls_path or EXAMPLES / f"{symbol}_cls_test.json")
    ths_path = Path(ths_path or EXAMPLES / f"{symbol}_ths_test.json")

    def _load(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    bundle = _load(bundle_path)
    if not bundle:
        raise FileNotFoundError(f"Missing bundle: {bundle_path}")
    market_info = _load(market_info_path) or {}
    eastmoney = _load(eastmoney_path)
    cls = _load(cls_path)
    ths = _load(ths_path)

    normalizer = EvidenceNormalizer()
    evidences: list[Evidence] = []
    evidences.extend(normalizer.normalize_bundle(bundle))
    evidences.extend(normalizer.normalize_market_information(market_info))
    if eastmoney:
        evidences.extend(normalizer.normalize_eastmoney(eastmoney))
    if cls:
        evidences.extend(normalizer.normalize_cls(cls))
    if ths:
        evidences.extend(normalizer.normalize_ths(ths))

    # Unique by evidence_id (same content from market_info + raw files)
    uniq: dict[str, Evidence] = {}
    for e in evidences:
        uniq[e.evidence_id] = e
    merged = list(uniq.values())
    merged = mark_duplicates(merged)

    pack = EvidencePack(
        stock_code=symbol,
        evidence=merged,
        metadata={
            "inputs": {
                "bundle": str(bundle_path),
                "market_information": str(market_info_path),
                "eastmoney": str(eastmoney_path) if eastmoney else None,
                "cls": str(cls_path) if cls else None,
                "ths": str(ths_path) if ths else None,
            },
            "notes": [
                "Sina news is excluded from core Evidence Layer.",
                "Evidence contains facts only; no bull/bear stance fields.",
            ],
        },
    )
    pack.validate()
    return pack


def save_evidence_pack(pack: EvidencePack, output_path: str | Path | None = None) -> Path:
    path = Path(output_path or EXAMPLES / f"{pack.stock_code}_evidence_pack.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pack.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
