"""Current market / valuation snapshot (raw layer)."""

from __future__ import annotations

from typing import Any

import akshare as ak
import pandas as pd

from ..network import patch_requests_no_proxy, with_retry
from ..utils import meta, normalize_symbol, to_float, to_iso_date


SOURCE_VALUE = "akshare.stock_value_em"
SOURCE_SPOT = "akshare.stock_zh_a_spot_em"
SOURCE_SINA_DAILY = "akshare.stock_zh_a_daily"


def _from_value_em(symbol: str) -> dict[str, Any]:
    df = with_retry(lambda: ak.stock_value_em(symbol=symbol))
    if df is None or df.empty:
        raise RuntimeError("stock_value_em returned empty data")
    latest = df.iloc[-1]
    data_date = to_iso_date(latest.get("数据日期"))
    return {
        "stock_code": symbol,
        "latest_price": to_float(latest.get("当日收盘价")),
        "pe_ttm": to_float(latest.get("PE(TTM)")),
        "pe_static": to_float(latest.get("PE(静)")),
        "pb": to_float(latest.get("市净率")),
        "ps_ttm": to_float(latest.get("市销率")),
        "total_market_cap": to_float(latest.get("总市值")),
        "float_market_cap": to_float(latest.get("流通市值")),
        "turnover_rate": None,  # not provided by this endpoint
        "data_date": data_date,
        "_meta": meta(source=SOURCE_VALUE, data_date=data_date),
    }


def _turnover_from_spot_em(symbol: str) -> tuple[float | None, str | None]:
    df = with_retry(lambda: ak.stock_zh_a_spot_em(), retries=2)
    if df is None or df.empty:
        return None, None
    row = df.loc[df["代码"].astype(str) == symbol]
    if row.empty:
        return None, None
    latest = row.iloc[0]
    return to_float(latest.get("换手率")), to_iso_date(pd.Timestamp.now().date())


def _turnover_from_sina_daily(symbol: str) -> tuple[float | None, str | None]:
    """Sina daily exposes ``turnover`` (ratio). Convert to percent to match EM spot."""
    from ..utils import sina_symbol

    end = pd.Timestamp.now().strftime("%Y%m%d")
    start = (pd.Timestamp.now() - pd.Timedelta(days=20)).strftime("%Y%m%d")
    df = with_retry(
        lambda: ak.stock_zh_a_daily(
            symbol=sina_symbol(symbol),
            start_date=start,
            end_date=end,
            adjust="",
        )
    )
    if df is None or df.empty:
        return None, None
    latest = df.iloc[-1]
    turnover = to_float(latest.get("turnover"))
    # Sina turnover is a ratio (e.g. 0.0024); EM spot uses percent (e.g. 0.24)
    if turnover is not None and turnover < 1:
        turnover = turnover * 100
    return turnover, to_iso_date(latest.get("date"))


def get_market_snapshot(symbol: str) -> dict[str, Any]:
    """Current price + valuation multiples.

    Primary valuation: ``ak.stock_value_em`` (stable; includes PE/PB/PS/caps).
    Turnover: ``ak.stock_zh_a_spot_em`` first, then ``ak.stock_zh_a_daily``.
    """
    patch_requests_no_proxy()
    code = normalize_symbol(symbol)
    todos: list[dict[str, Any]] = []

    try:
        snapshot = _from_value_em(code)
    except Exception as exc:  # noqa: BLE001
        return {
            "stock_code": code,
            "error": str(exc),
            "todos": [
                {
                    "field": "market_snapshot",
                    "reason": f"stock_value_em failed: {exc}",
                    "alternative": "Tushare daily_basic / Eastmoney spot when push2 reachable",
                }
            ],
            "_meta": meta(source=SOURCE_VALUE),
        }

    # PE field requested as PE — expose pe_ttm as pe
    snapshot["pe"] = snapshot.get("pe_ttm")
    snapshot["ps"] = snapshot.get("ps_ttm")

    turnover = None
    turnover_source = None
    spot_error: str | None = None
    try:
        turnover, _ = _turnover_from_spot_em(code)
        if turnover is not None:
            turnover_source = SOURCE_SPOT
    except Exception as exc:  # noqa: BLE001
        spot_error = str(exc)

    if turnover is None:
        try:
            turnover, _ = _turnover_from_sina_daily(code)
            if turnover is not None:
                turnover_source = SOURCE_SINA_DAILY
                if spot_error:
                    snapshot["_meta"]["turnover_fallback_note"] = (
                        f"spot_em failed ({spot_error}); used sina daily"
                    )
        except Exception as exc:  # noqa: BLE001
            todos.append(
                {
                    "field": "turnover_rate",
                    "reason": (
                        f"spot_em failed ({spot_error}); "
                        f"stock_zh_a_daily also failed: {exc}"
                    ),
                    "alternative": "Tushare daily_basic.turnover_rate",
                }
            )

    if turnover is not None:
        snapshot["turnover_rate"] = turnover
        snapshot["_meta"]["turnover_source"] = turnover_source
    else:
        todos.append(
            {
                "field": "turnover_rate",
                "reason": spot_error or "No turnover available from spot or sina daily",
                "alternative": "Tushare daily_basic.turnover_rate",
            }
        )

    if todos:
        snapshot["todos"] = todos
    return snapshot


def test_market_snapshot(symbol: str = "600519") -> dict[str, Any]:
    data = get_market_snapshot(symbol)
    required = ["latest_price", "pe", "pb", "ps", "total_market_cap", "float_market_cap"]
    missing = [k for k in required if data.get(k) is None]
    return {
        "ok": len(missing) == 0,
        "missing": missing,
        "sample": {k: data.get(k) for k in required + ["turnover_rate", "data_date"]},
        "todos": data.get("todos"),
        "source": data.get("_meta", {}).get("source"),
    }
