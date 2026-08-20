"""Historical OHLCV (raw layer)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import akshare as ak
import pandas as pd

from ..network import patch_requests_no_proxy, with_retry
from ..utils import meta, normalize_symbol, sina_symbol, to_float, to_iso_date


SOURCE_EM_HIST = "akshare.stock_zh_a_hist"
SOURCE_SINA_DAILY = "akshare.stock_zh_a_daily"


def _default_start(years: int = 3) -> str:
    start = datetime.now().date() - timedelta(days=365 * years + 30)
    return start.strftime("%Y%m%d")


def _default_end() -> str:
    return datetime.now().date().strftime("%Y%m%d")


def _normalize_em_hist(df: pd.DataFrame, code: str, source: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        data_date = to_iso_date(row.get("日期"))
        items.append(
            {
                "date": data_date,
                "open": to_float(row.get("开盘")),
                "high": to_float(row.get("最高")),
                "low": to_float(row.get("最低")),
                "close": to_float(row.get("收盘")),
                "volume": to_float(row.get("成交量")),
                "amount": to_float(row.get("成交额")),
                "_meta": meta(source=source, data_date=data_date),
            }
        )
    return items


def _normalize_sina_daily(df: pd.DataFrame, code: str, source: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        data_date = to_iso_date(row.get("date"))
        items.append(
            {
                "date": data_date,
                "open": to_float(row.get("open")),
                "high": to_float(row.get("high")),
                "low": to_float(row.get("low")),
                "close": to_float(row.get("close")),
                "volume": to_float(row.get("volume")),
                "amount": to_float(row.get("amount")),
                "_meta": meta(source=source, data_date=data_date),
            }
        )
    return items


def get_market_history(
    symbol: str,
    *,
    years: int = 3,
    adjust: str = "qfq",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Fetch at least ~3 years of daily bars.

    Primary: ``ak.stock_zh_a_hist`` (Eastmoney)
    Fallback: ``ak.stock_zh_a_daily`` (Sina) when push2his is unreachable.
    """
    patch_requests_no_proxy()
    code = normalize_symbol(symbol)
    start = start_date or _default_start(years)
    end = end_date or _default_end()
    errors: list[str] = []

    # Eastmoney
    try:
        df = with_retry(
            lambda: ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start,
                end_date=end,
                adjust=adjust,
            ),
            retries=2,
        )
        if df is not None and not df.empty:
            items = _normalize_em_hist(df, code, SOURCE_EM_HIST)
            return {
                "stock_code": code,
                "adjust": adjust,
                "start_date": to_iso_date(start),
                "end_date": to_iso_date(end),
                "items": items,
                "_meta": meta(
                    source=SOURCE_EM_HIST,
                    data_date=items[-1]["date"] if items else None,
                    extra={"adjust": adjust},
                ),
            }
        errors.append(f"{SOURCE_EM_HIST}: empty frame")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{SOURCE_EM_HIST}: {exc}")

    # Sina fallback
    try:
        df = with_retry(
            lambda: ak.stock_zh_a_daily(
                symbol=sina_symbol(code),
                start_date=start,
                end_date=end,
                adjust=adjust,
            )
        )
        if df is not None and not df.empty:
            items = _normalize_sina_daily(df, code, SOURCE_SINA_DAILY)
            return {
                "stock_code": code,
                "adjust": adjust,
                "start_date": to_iso_date(start),
                "end_date": to_iso_date(end),
                "items": items,
                "_meta": meta(
                    source=SOURCE_SINA_DAILY,
                    data_date=items[-1]["date"] if items else None,
                    extra={"adjust": adjust, "fallback_notes": errors},
                ),
            }
        errors.append(f"{SOURCE_SINA_DAILY}: empty frame")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{SOURCE_SINA_DAILY}: {exc}")

    return {
        "stock_code": code,
        "adjust": adjust,
        "items": [],
        "error": "; ".join(errors),
        "todos": [
            {
                "field": "market_history",
                "reason": "; ".join(errors),
                "alternative": "Tushare pro.daily / Baostock query_history_k_data_plus",
            }
        ],
        "_meta": meta(source=SOURCE_EM_HIST),
    }


def test_market_history(symbol: str = "600519") -> dict[str, Any]:
    data = get_market_history(symbol, years=3)
    items = data.get("items") or []
    return {
        "ok": len(items) >= 200,
        "count": len(items),
        "source": data.get("_meta", {}).get("source"),
        "first": items[0] if items else None,
        "last": items[-1] if items else None,
        "error": data.get("error"),
    }
