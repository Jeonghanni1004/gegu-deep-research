"""Three financial statements (raw layer)."""

from __future__ import annotations

from typing import Any

import akshare as ak
import pandas as pd

from ..network import patch_requests_no_proxy, with_retry
from ..utils import em_symbol, meta, normalize_symbol, to_float, to_iso_date


SOURCE_PROFIT = "akshare.stock_profit_sheet_by_report_em"
SOURCE_BALANCE = "akshare.stock_balance_sheet_by_report_em"
SOURCE_CASH = "akshare.stock_cash_flow_sheet_by_report_em"


def _limit_recent(df: pd.DataFrame, max_rows: int = 20) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    if "REPORT_DATE" in out.columns:
        out["_rd"] = pd.to_datetime(out["REPORT_DATE"], errors="coerce")
        out = out.sort_values("_rd", ascending=False).drop(columns=["_rd"])
    return out.head(max_rows).reset_index(drop=True)


def _row_meta(source: str, report_date: str | None) -> dict[str, Any]:
    return meta(source=source, report_date=report_date)


def get_income_statement(symbol: str, max_periods: int = 20) -> dict[str, Any]:
    patch_requests_no_proxy()
    code = normalize_symbol(symbol)
    try:
        df = with_retry(lambda: ak.stock_profit_sheet_by_report_em(symbol=em_symbol(code)))
        df = _limit_recent(df, max_periods)
    except Exception as exc:  # noqa: BLE001
        return {
            "stock_code": code,
            "items": [],
            "error": str(exc),
            "todos": [
                {
                    "field": "income_statement",
                    "reason": f"stock_profit_sheet_by_report_em failed: {exc}",
                    "alternative": "ak.stock_financial_report_sina / CNINFO / Tushare income",
                }
            ],
            "_meta": meta(source=SOURCE_PROFIT),
        }

    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        report_date = to_iso_date(row.get("REPORT_DATE"))
        revenue = to_float(row.get("OPERATE_INCOME"))
        if revenue is None:
            revenue = to_float(row.get("TOTAL_OPERATE_INCOME"))
        cost = to_float(row.get("OPERATE_COST"))
        gross_profit = None
        if revenue is not None and cost is not None:
            gross_profit = revenue - cost
        items.append(
            {
                "report_date": report_date,
                "operating_revenue": revenue,
                "operating_cost": cost,
                "operating_profit": to_float(row.get("OPERATE_PROFIT")),
                "net_profit_parent": to_float(row.get("PARENT_NETPROFIT")),
                "gross_profit": gross_profit,
                "eps_basic": to_float(row.get("BASIC_EPS")),
                "rd_expense": to_float(row.get("RESEARCH_EXPENSE")),
                "selling_expense": to_float(row.get("SALE_EXPENSE")),
                "admin_expense": to_float(row.get("MANAGE_EXPENSE")),
                "finance_expense": to_float(row.get("FINANCE_EXPENSE")),
                "_meta": _row_meta(SOURCE_PROFIT, report_date),
            }
        )

    return {
        "stock_code": code,
        "items": items,
        "_meta": meta(source=SOURCE_PROFIT, report_date=items[0]["report_date"] if items else None),
    }


def get_balance_sheet(symbol: str, max_periods: int = 20) -> dict[str, Any]:
    patch_requests_no_proxy()
    code = normalize_symbol(symbol)
    try:
        df = with_retry(lambda: ak.stock_balance_sheet_by_report_em(symbol=em_symbol(code)))
        df = _limit_recent(df, max_periods)
    except Exception as exc:  # noqa: BLE001
        return {
            "stock_code": code,
            "items": [],
            "error": str(exc),
            "todos": [
                {
                    "field": "balance_sheet",
                    "reason": f"stock_balance_sheet_by_report_em failed: {exc}",
                    "alternative": "ak.stock_financial_debt_ths / CNINFO / Tushare balancesheet",
                }
            ],
            "_meta": meta(source=SOURCE_BALANCE),
        }

    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        report_date = to_iso_date(row.get("REPORT_DATE"))
        total_assets = to_float(row.get("TOTAL_ASSETS"))
        total_liab = to_float(row.get("TOTAL_LIABILITIES"))
        equity = to_float(row.get("TOTAL_PARENT_EQUITY"))
        if equity is None:
            equity = to_float(row.get("TOTAL_EQUITY"))
        items.append(
            {
                "report_date": report_date,
                "total_assets": total_assets,
                "total_liabilities": total_liab,
                "total_equity": equity,
                "cash_and_equivalents": to_float(row.get("MONETARYFUNDS")),
                "accounts_receivable": to_float(row.get("ACCOUNTS_RECE")),
                "inventory": to_float(row.get("INVENTORY")),
                "goodwill": to_float(row.get("GOODWILL")),
                "short_term_borrowings": to_float(row.get("SHORT_LOAN")),
                "long_term_borrowings": to_float(row.get("LONG_LOAN")),
                "_meta": _row_meta(SOURCE_BALANCE, report_date),
            }
        )

    return {
        "stock_code": code,
        "items": items,
        "_meta": meta(source=SOURCE_BALANCE, report_date=items[0]["report_date"] if items else None),
    }


def get_cash_flow(symbol: str, max_periods: int = 20) -> dict[str, Any]:
    patch_requests_no_proxy()
    code = normalize_symbol(symbol)
    try:
        df = with_retry(lambda: ak.stock_cash_flow_sheet_by_report_em(symbol=em_symbol(code)))
        df = _limit_recent(df, max_periods)
    except Exception as exc:  # noqa: BLE001
        return {
            "stock_code": code,
            "items": [],
            "error": str(exc),
            "todos": [
                {
                    "field": "cash_flow",
                    "reason": f"stock_cash_flow_sheet_by_report_em failed: {exc}",
                    "alternative": "ak.stock_financial_cash_ths / CNINFO / Tushare cashflow",
                }
            ],
            "_meta": meta(source=SOURCE_CASH),
        }

    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        report_date = to_iso_date(row.get("REPORT_DATE"))
        items.append(
            {
                "report_date": report_date,
                "operating_cash_flow": to_float(row.get("NETCASH_OPERATE")),
                "investing_cash_flow": to_float(row.get("NETCASH_INVEST")),
                "financing_cash_flow": to_float(row.get("NETCASH_FINANCE")),
                "_meta": _row_meta(SOURCE_CASH, report_date),
            }
        )

    return {
        "stock_code": code,
        "items": items,
        "_meta": meta(source=SOURCE_CASH, report_date=items[0]["report_date"] if items else None),
    }


def get_financials(symbol: str, max_periods: int = 20) -> dict[str, Any]:
    code = normalize_symbol(symbol)
    income = get_income_statement(code, max_periods=max_periods)
    balance = get_balance_sheet(code, max_periods=max_periods)
    cash = get_cash_flow(code, max_periods=max_periods)
    todos: list[dict[str, Any]] = []
    for part in (income, balance, cash):
        todos.extend(part.get("todos") or [])
    return {
        "stock_code": code,
        "income_statement": income,
        "balance_sheet": balance,
        "cash_flow": cash,
        "todos": todos,
    }


def test_financials(symbol: str = "600519") -> dict[str, Any]:
    data = get_financials(symbol, max_periods=8)
    return {
        "ok": bool(data["income_statement"]["items"])
        and bool(data["balance_sheet"]["items"])
        and bool(data["cash_flow"]["items"]),
        "income_count": len(data["income_statement"].get("items") or []),
        "balance_count": len(data["balance_sheet"].get("items") or []),
        "cash_count": len(data["cash_flow"].get("items") or []),
        "income_sample": (data["income_statement"].get("items") or [None])[0],
        "balance_sample": (data["balance_sheet"].get("items") or [None])[0],
        "cash_sample": (data["cash_flow"].get("items") or [None])[0],
        "todos": data.get("todos"),
    }
