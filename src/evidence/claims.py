"""Deterministic claim templates. No LLM."""

from __future__ import annotations

from typing import Any


def _fmt_num(value: Any, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(num) >= 1e8:
        return f"{num / 1e8:.2f} 亿元"
    if abs(num) >= 1e4:
        return f"{num / 1e4:.2f} 万元"
    return f"{num:.{digits}f}"


def _fmt_pct(value: Any, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return str(value)


def claim_fact_metric(metric_label: str, value: Any, *, period: str | None = None, unit_hint: str = "") -> str:
    period_part = f"{period} " if period else ""
    if unit_hint == "ratio":
        return f"{period_part}{metric_label}为 {_fmt_pct(value)}".strip()
    if unit_hint == "price":
        return f"{period_part}{metric_label}为 {float(value):.2f} 元".strip() if value is not None else f"{metric_label}缺失"
    if unit_hint == "count":
        return f"{period_part}{metric_label}为 {value}".strip()
    return f"{period_part}{metric_label}为 {_fmt_num(value)}".strip()


def claim_derived_yoy(label: str, value: Any, *, period: str | None = None) -> str:
    period_part = f"{period} " if period else ""
    if value is None:
        return f"{period_part}{label}同比数据缺失".strip()
    direction = "增长" if float(value) >= 0 else "下降"
    return f"{period_part}{label}同比{direction} {_fmt_pct(abs(float(value)))}".strip()


def claim_derived_ratio(label: str, value: Any, *, period: str | None = None) -> str:
    period_part = f"{period} " if period else ""
    return f"{period_part}{label}为 {_fmt_pct(value)}".strip()


def claim_technical(label: str, value: Any, *, data_date: str | None = None) -> str:
    date_part = f"{data_date} " if data_date else ""
    if value is None:
        return f"{date_part}{label}缺失".strip()
    if "position" in label.lower() or label.endswith("区间位置"):
        return f"{date_part}{label}为 {_fmt_pct(value)}".strip()
    return f"{date_part}{label}为 {float(value):.4f}".strip()


def claim_announcement(title: str, published_at: str | None = None) -> str:
    when = f"{published_at[:10]} " if published_at else ""
    return f"{when}公司公告：{title}".strip()


def claim_shareholder(holder: str, direction: str, change_num: Any, notice_date: str | None) -> str:
    when = f"{str(notice_date)[:10]} " if notice_date else ""
    qty = _fmt_num(change_num * 1e4) if isinstance(change_num, (int, float)) else str(change_num)
    # CHANGE_NUM in EM sample appears to be in 万股 already (127.4234)
    if isinstance(change_num, (int, float)):
        qty = f"{float(change_num):.4f} 万股"
    return f"{when}股东{holder}{direction}{qty}".strip()


def claim_news(title: str, published_at: str | None, category: str) -> str:
    when = f"{published_at} " if published_at else ""
    return f"{when}[{category}] {title}".strip()


def claim_eps_consensus(year: Any, value: Any, institution_count: Any, updated_at: str | None = None) -> str:
    when = f"（更新于 {updated_at}）" if updated_at else ""
    inst = f"，共 {institution_count} 家机构" if institution_count is not None else ""
    return f"{year} 年 EPS 一致预期为 {float(value):.2f} 元{inst}{when}"
