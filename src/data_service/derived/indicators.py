"""Derived indicators computed in Python (no LLM)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..utils import meta, safe_div, to_float, yoy_growth


SOURCE = "python.derived"


def _bars_to_df(history_items: list[dict[str, Any]]) -> pd.DataFrame:
    if not history_items:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
    df = pd.DataFrame(history_items)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    for col in ("open", "high", "low", "close", "volume", "amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float | None]:
    if close.empty or len(close) < slow + signal:
        return {"macd_dif": None, "macd_dea": None, "macd_hist": None}
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = (dif - dea) * 2
    return {
        "macd_dif": to_float(dif.iloc[-1]),
        "macd_dea": to_float(dea.iloc[-1]),
        "macd_hist": to_float(hist.iloc[-1]),
    }


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return to_float(rsi.iloc[-1])


def _find_by_report_date(items: list[dict[str, Any]], report_date: str | None) -> dict[str, Any] | None:
    if not report_date:
        return None
    for item in items:
        if item.get("report_date") == report_date:
            return item
    return None


def _prior_year_same_period(items: list[dict[str, Any]], report_date: str) -> dict[str, Any] | None:
    """Find item with same month-day one year earlier (e.g. 2024-12-31 -> 2023-12-31)."""
    try:
        current = pd.Timestamp(report_date)
    except (TypeError, ValueError):
        return None
    target = (current - pd.DateOffset(years=1)).date().isoformat()
    return _find_by_report_date(items, target)


def compute_fundamental_indicators(
    income_items: list[dict[str, Any]],
    balance_items: list[dict[str, Any]],
    cash_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute fundamental ratios from the latest aligned report period."""
    if not income_items:
        return {
            "items": [],
            "latest": None,
            "todos": [{"field": "fundamentals", "reason": "empty income statement", "alternative": None}],
            "_meta": meta(source=SOURCE),
        }

    # Prefer annual reports (12-31) when available, else latest period
    annual = [i for i in income_items if (i.get("report_date") or "").endswith("-12-31")]
    base_income = annual[0] if annual else income_items[0]
    report_date = base_income.get("report_date")
    balance = _find_by_report_date(balance_items, report_date) or (balance_items[0] if balance_items else {})
    cash = _find_by_report_date(cash_items, report_date) or (cash_items[0] if cash_items else {})
    prior_income = _prior_year_same_period(income_items, report_date) if report_date else None

    revenue = base_income.get("operating_revenue")
    cost = base_income.get("operating_cost")
    net_profit = base_income.get("net_profit_parent")
    prior_revenue = prior_income.get("operating_revenue") if prior_income else None
    prior_net = prior_income.get("net_profit_parent") if prior_income else None
    equity = balance.get("total_equity")
    assets = balance.get("total_assets")
    liabilities = balance.get("total_liabilities")
    ocf = cash.get("operating_cash_flow")

    gross_profit = None
    if revenue is not None and cost is not None:
        gross_profit = revenue - cost

    latest = {
        "report_date": report_date,
        "revenue_yoy": yoy_growth(revenue, prior_revenue),
        "net_profit_yoy": yoy_growth(net_profit, prior_net),
        "gross_margin": safe_div(gross_profit, revenue),
        "net_margin": safe_div(net_profit, revenue),
        "roe": safe_div(net_profit, equity),
        "debt_to_asset_ratio": safe_div(liabilities, assets),
        "ocf_to_net_profit": safe_div(ocf, net_profit),
        "_meta": meta(source=SOURCE, report_date=report_date),
        "_inputs": {
            "revenue": revenue,
            "prior_revenue": prior_revenue,
            "net_profit_parent": net_profit,
            "prior_net_profit_parent": prior_net,
            "total_equity": equity,
            "total_assets": assets,
            "total_liabilities": liabilities,
            "operating_cash_flow": ocf,
            "note": "ROE uses ending equity (not average equity).",
        },
    }

    return {
        "latest": latest,
        "items": [latest],
        "_meta": meta(source=SOURCE, report_date=report_date),
    }


def compute_technical_indicators(history_items: list[dict[str, Any]]) -> dict[str, Any]:
    df = _bars_to_df(history_items)
    if df.empty:
        return {
            "latest": None,
            "series_tail": [],
            "todos": [{"field": "technicals", "reason": "empty market history", "alternative": None}],
            "_meta": meta(source=SOURCE),
        }

    close = df["close"]
    for window in (5, 20, 60, 250):
        df[f"ma{window}"] = close.rolling(window).mean()

    macd = _macd(close)
    rsi = _rsi(close)

    lookback = df.tail(252) if len(df) >= 252 else df
    high_52w = to_float(lookback["high"].max())
    low_52w = to_float(lookback["low"].min())
    last_close = to_float(close.iloc[-1])
    position = None
    if last_close is not None and high_52w is not None and low_52w is not None and high_52w != low_52w:
        position = (last_close - low_52w) / (high_52w - low_52w)

    last_date = df["date"].iloc[-1].date().isoformat()
    latest = {
        "data_date": last_date,
        "close": last_close,
        "ma5": to_float(df["ma5"].iloc[-1]),
        "ma20": to_float(df["ma20"].iloc[-1]),
        "ma60": to_float(df["ma60"].iloc[-1]),
        "ma250": to_float(df["ma250"].iloc[-1]),
        "macd_dif": macd["macd_dif"],
        "macd_dea": macd["macd_dea"],
        "macd_hist": macd["macd_hist"],
        "rsi_14": rsi,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "price_position_in_52w_range": position,
        "_meta": meta(source=SOURCE, data_date=last_date),
    }

    # Keep a short series for debugging / charts later
    tail = df.tail(5)
    series_tail = []
    for _, row in tail.iterrows():
        series_tail.append(
            {
                "date": row["date"].date().isoformat(),
                "close": to_float(row["close"]),
                "ma5": to_float(row["ma5"]),
                "ma20": to_float(row["ma20"]),
                "ma60": to_float(row["ma60"]),
                "ma250": to_float(row["ma250"]),
            }
        )

    return {
        "latest": latest,
        "series_tail": series_tail,
        "_meta": meta(source=SOURCE, data_date=last_date),
    }


def compute_all_indicators(
    *,
    financials: dict[str, Any],
    market_history: dict[str, Any],
) -> dict[str, Any]:
    fundamentals = compute_fundamental_indicators(
        financials.get("income_statement", {}).get("items") or [],
        financials.get("balance_sheet", {}).get("items") or [],
        financials.get("cash_flow", {}).get("items") or [],
    )
    technicals = compute_technical_indicators(market_history.get("items") or [])
    return {
        "fundamentals": fundamentals,
        "technicals": technicals,
        "_meta": meta(source=SOURCE),
    }


def test_indicators(symbol: str = "600519") -> dict[str, Any]:
    from ..raw.financials import get_financials
    from ..raw.market_history import get_market_history

    financials = get_financials(symbol, max_periods=12)
    history = get_market_history(symbol, years=3)
    derived = compute_all_indicators(financials=financials, market_history=history)
    fund = (derived.get("fundamentals") or {}).get("latest") or {}
    tech = (derived.get("technicals") or {}).get("latest") or {}
    required_fund = ["revenue_yoy", "net_profit_yoy", "gross_margin", "net_margin", "roe", "debt_to_asset_ratio"]
    required_tech = ["ma5", "ma20", "ma60", "rsi_14", "high_52w", "low_52w", "price_position_in_52w_range"]
    missing = [k for k in required_fund if fund.get(k) is None] + [k for k in required_tech if tech.get(k) is None]
    return {
        "ok": len(missing) == 0,
        "missing": missing,
        "fundamentals": fund,
        "technicals": tech,
    }
