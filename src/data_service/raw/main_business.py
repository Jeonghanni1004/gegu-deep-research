"""Main business composition (raw layer)."""

from __future__ import annotations

from typing import Any

import akshare as ak
import pandas as pd

from ..network import patch_requests_no_proxy, with_retry
from ..utils import em_symbol, meta, normalize_symbol, to_float, to_iso_date


SOURCE = "akshare.stock_zygc_em"

COLUMN_MAP = {
    "股票代码": "stock_code",
    "报告日期": "report_date",
    "分类类型": "category_type",
    "主营构成": "business_segment",
    "主营收入": "revenue",
    "收入比例": "revenue_ratio",
    "主营成本": "operating_cost",
    "成本比例": "cost_ratio",
    "主营利润": "gross_profit",
    "利润比例": "profit_ratio",
    "毛利率": "gross_margin",
}


def get_main_business(symbol: str) -> dict[str, Any]:
    """Fetch main business composition via ``ak.stock_zygc_em``."""
    patch_requests_no_proxy()
    code = normalize_symbol(symbol)
    try:
        df = with_retry(lambda: ak.stock_zygc_em(symbol=em_symbol(code)))
    except Exception as exc:  # noqa: BLE001
        return {
            "stock_code": code,
            "items": [],
            "error": str(exc),
            "todos": [
                {
                    "field": "main_business",
                    "reason": f"stock_zygc_em failed: {exc}",
                    "alternative": "Eastmoney F10 BusinessAnalysis PageAjax / CNINFO annual report notes",
                }
            ],
            "_meta": meta(source=SOURCE),
        }

    if df is None or df.empty:
        return {
            "stock_code": code,
            "items": [],
            "todos": [
                {
                    "field": "main_business",
                    "reason": "stock_zygc_em returned empty frame",
                    "alternative": "CNINFO / Wind / Choice segment revenue tables",
                }
            ],
            "_meta": meta(source=SOURCE),
        }

    renamed = df.rename(columns=COLUMN_MAP).copy()
    items: list[dict[str, Any]] = []
    for _, row in renamed.iterrows():
        report_date = to_iso_date(row.get("report_date"))
        items.append(
            {
                "stock_code": code,
                "report_date": report_date,
                "category_type": None if pd.isna(row.get("category_type")) else str(row.get("category_type")),
                "business_segment": None if pd.isna(row.get("business_segment")) else str(row.get("business_segment")),
                "revenue": to_float(row.get("revenue")),
                "revenue_ratio": to_float(row.get("revenue_ratio")),
                "operating_cost": to_float(row.get("operating_cost")),
                "cost_ratio": to_float(row.get("cost_ratio")),
                "gross_profit": to_float(row.get("gross_profit")),
                "profit_ratio": to_float(row.get("profit_ratio")),
                "gross_margin": to_float(row.get("gross_margin")),
                "_meta": meta(source=SOURCE, report_date=report_date),
            }
        )

    latest_report = max((i["report_date"] for i in items if i.get("report_date")), default=None)
    return {
        "stock_code": code,
        "latest_report_date": latest_report,
        "items": items,
        "_meta": meta(source=SOURCE, report_date=latest_report),
    }


def test_main_business(symbol: str = "600519") -> dict[str, Any]:
    data = get_main_business(symbol)
    ok = bool(data.get("items"))
    sample = data["items"][:3] if data.get("items") else []
    return {
        "ok": ok,
        "count": len(data.get("items") or []),
        "latest_report_date": data.get("latest_report_date"),
        "sample": sample,
        "error": data.get("error"),
    }
