"""Company basic profile (raw layer)."""

from __future__ import annotations

from typing import Any

import akshare as ak
import pandas as pd
import requests

from ..network import patch_requests_no_proxy, with_retry
from ..utils import (
    em_symbol,
    exchange_name,
    meta,
    normalize_symbol,
    to_float,
    to_iso_date,
)


SOURCE_EM_INDIVIDUAL = "akshare.stock_individual_info_em"
SOURCE_EM_VALUE = "akshare.stock_value_em"
SOURCE_EM_F10_SURVEY = "eastmoney.PC_HSF10.CompanySurvey"


def _item_map_from_em_info(df: pd.DataFrame) -> dict[str, Any]:
    return {str(row["item"]): row["value"] for _, row in df.iterrows()}


def _fetch_em_individual(symbol: str) -> dict[str, Any]:
    df = with_retry(lambda: ak.stock_individual_info_em(symbol=symbol))
    items = _item_map_from_em_info(df)
    listing_raw = items.get("上市时间")
    # Eastmoney returns YYYYMMDD int for listing date
    listing_date = to_iso_date(listing_raw)
    return {
        "stock_code": normalize_symbol(str(items.get("股票代码", symbol))),
        "stock_name": str(items.get("股票简称") or ""),
        "exchange": exchange_name(symbol),
        "listing_date": listing_date,
        "industry": str(items.get("行业") or "") or None,
        "total_shares": to_float(items.get("总股本")),
        "float_shares": to_float(items.get("流通股")),
        "total_market_cap": to_float(items.get("总市值")),
        "_meta": meta(source=SOURCE_EM_INDIVIDUAL, data_date=None),
    }


def _fetch_em_f10_survey(symbol: str) -> dict[str, Any]:
    """Fallback via Eastmoney F10 CompanySurvey (same host family as stock_zygc_em).

    Not an AKShare wrapper function; used only when ``stock_individual_info_em``
    (push2.eastmoney.com) is unreachable.
    """
    code = em_symbol(symbol)
    url = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax"
    session = requests.Session()
    session.trust_env = False
    resp = session.get(url, params={"code": code}, proxies={"http": None, "https": None}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    jbzl = (data.get("jbzl") or [None])[0] or {}
    fxxg = (data.get("fxxg") or [None])[0] or {}
    return {
        "stock_code": normalize_symbol(symbol),
        "stock_name": jbzl.get("SECURITY_NAME_ABBR") or jbzl.get("STR_NAMEA"),
        "exchange": exchange_name(symbol),
        "listing_date": to_iso_date(fxxg.get("LISTING_DATE")),
        "industry": jbzl.get("INDUSTRYCSRC1"),
        "company_name": jbzl.get("ORG_NAME"),
        "business_scope": jbzl.get("BUSINESS_SCOPE"),
        "_meta": meta(source=SOURCE_EM_F10_SURVEY, data_date=None),
    }


def _fetch_shares_from_value_em(symbol: str) -> dict[str, Any]:
    df = with_retry(lambda: ak.stock_value_em(symbol=normalize_symbol(symbol)))
    if df is None or df.empty:
        raise RuntimeError("stock_value_em returned empty data")
    latest = df.iloc[-1]
    data_date = to_iso_date(latest.get("数据日期"))
    return {
        "total_shares": to_float(latest.get("总股本")),
        "float_shares": to_float(latest.get("流通股本")),
        "total_market_cap": to_float(latest.get("总市值")),
        "float_market_cap": to_float(latest.get("流通市值")),
        "data_date": data_date,
        "_meta": meta(source=SOURCE_EM_VALUE, data_date=data_date),
    }


def get_company_info(symbol: str) -> dict[str, Any]:
    """Fetch company basic info.

    Primary: ``ak.stock_individual_info_em``
    Fallback: Eastmoney F10 CompanySurvey + ``ak.stock_value_em`` for shares/cap.
    """
    patch_requests_no_proxy()
    code = normalize_symbol(symbol)
    errors: list[str] = []
    profile: dict[str, Any] | None = None

    try:
        profile = _fetch_em_individual(code)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{SOURCE_EM_INDIVIDUAL}: {exc}")
        try:
            profile = _fetch_em_f10_survey(code)
        except Exception as exc2:  # noqa: BLE001
            errors.append(f"{SOURCE_EM_F10_SURVEY}: {exc2}")
            raise RuntimeError(
                "Failed to fetch company basic info. "
                f"Tried AKShare stock_individual_info_em then EM F10 survey. errors={errors}"
            ) from exc2

    # Enrich shares / market cap if missing
    if profile.get("total_shares") is None or profile.get("total_market_cap") is None:
        try:
            shares = _fetch_shares_from_value_em(code)
            for key in ("total_shares", "float_shares", "total_market_cap"):
                if profile.get(key) is None:
                    profile[key] = shares.get(key)
            profile.setdefault("float_market_cap", shares.get("float_market_cap"))
            profile["_meta"]["enrichment_source"] = SOURCE_EM_VALUE
            if shares.get("data_date"):
                profile["_meta"]["data_date"] = shares["data_date"]
        except Exception as exc:  # noqa: BLE001
            profile.setdefault("todos", []).append(
                {
                    "field": "total_shares/total_market_cap",
                    "reason": f"stock_value_em enrichment failed: {exc}",
                    "alternative": "Tushare daily_basic / Eastmoney quote push2 when reachable",
                }
            )

    profile["stock_code"] = code
    if errors:
        profile.setdefault("_meta", {})["fallback_notes"] = errors
    return profile


def test_company_info(symbol: str = "600519") -> dict[str, Any]:
    data = get_company_info(symbol)
    required = ["stock_code", "stock_name", "exchange", "listing_date", "industry"]
    missing = [k for k in required if not data.get(k)]
    return {
        "ok": len(missing) == 0,
        "missing": missing,
        "sample": {k: data.get(k) for k in required + ["total_shares", "float_shares", "total_market_cap"]},
        "source": data.get("_meta", {}).get("source"),
    }
