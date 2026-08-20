"""Shared helpers: symbol normalization, metadata, safe conversions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_symbol(symbol: str) -> str:
    """Normalize user input like ``600519`` / ``sh600519`` / ``600519.SH``."""
    s = symbol.strip().upper().replace(" ", "")
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    if "." in s:
        s = s.split(".", 1)[0]
    if not s.isdigit() or len(s) != 6:
        raise ValueError(f"Invalid A-share symbol: {symbol!r}")
    return s


def market_prefix(symbol: str) -> str:
    """Return ``SH`` / ``SZ`` / ``BJ`` for a 6-digit code."""
    code = normalize_symbol(symbol)
    if code.startswith("6"):
        return "SH"
    if code.startswith(("0", "3")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    raise ValueError(f"Cannot infer exchange for symbol: {symbol!r}")


def exchange_name(symbol: str) -> str:
    mapping = {
        "SH": "Shanghai Stock Exchange",
        "SZ": "Shenzhen Stock Exchange",
        "BJ": "Beijing Stock Exchange",
    }
    return mapping[market_prefix(symbol)]


def em_symbol(symbol: str) -> str:
    """Eastmoney style: ``SH600519``."""
    code = normalize_symbol(symbol)
    return f"{market_prefix(code)}{code}"


def sina_symbol(symbol: str) -> str:
    """Sina style: ``sh600519``."""
    code = normalize_symbol(symbol)
    return f"{market_prefix(code).lower()}{code}"


def to_float(value: Any) -> float | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (float, int, np.floating, np.integer)):
        if pd.isna(value):
            return None
        return float(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        text = str(value).strip().replace(",", "")
        if text in {"", "-", "--", "None", "nan", "NaN"}:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def to_iso_date(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, np.integer)) and value > 10_000_000_000:
        # ms timestamp
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).date().isoformat()
    text = str(value).strip()
    if not text or text in {"-", "--", "None", "nan"}:
        return None
    # ``20010827`` or ``2001-08-27 00:00:00``
    if text.isdigit() and len(text) == 8:
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return pd.to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        return None


def meta(
    *,
    source: str,
    data_date: str | None = None,
    report_date: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": source,
        "retrieved_at": now_utc_iso(),
    }
    if data_date is not None:
        payload["data_date"] = data_date
    if report_date is not None:
        payload["report_date"] = report_date
    if extra:
        payload.update(extra)
    return payload


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def yoy_growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous)
