"""Demo stock pre-scan: heat pool + evidence completeness (no LLM).

Usage:
  set PYTHONPATH=src
  python scripts/demo_stock_prescan.py

Writes examples/demo_candidate_prescan.json and prints Top 10.
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import akshare as ak

from data_service.network import patch_requests_no_proxy, with_retry
from data_service.raw.financials import get_income_statement
from data_service.utils import normalize_symbol
from poc_market_sources.eastmoney_poc import (
    fetch_announcements,
    fetch_holder_reduce,
    fetch_stock_news,
    fetch_stock_news_sina,
    filter_recent,
)
from poc_market_sources.ths_poc import run_ths_poc

CONTROL_SYMBOL = "600519"
OUT_PATH = ROOT / "examples" / "demo_candidate_prescan.json"
POOL_TARGET = 30
MIN_PRICE = 2.0

# Fallback liquid / high-coverage names if live heat APIs fail.
SEED_FALLBACK = [
    ("600519", "贵州茅台"),
    ("000858", "五粮液"),
    ("601318", "中国平安"),
    ("600036", "招商银行"),
    ("000001", "平安银行"),
    ("601012", "隆基绿能"),
    ("300750", "宁德时代"),
    ("002594", "比亚迪"),
    ("600276", "恒瑞医药"),
    ("000333", "美的集团"),
    ("601888", "中国中免"),
    ("600900", "长江电力"),
    ("002415", "海康威视"),
    ("300059", "东方财富"),
    ("601899", "紫金矿业"),
    ("600030", "中信证券"),
    ("000568", "泸州老窖"),
    ("603259", "药明康德"),
    ("688981", "中芯国际"),
    ("002230", "科大讯飞"),
    ("601127", "赛力斯"),
    ("002475", "立讯精密"),
    ("300274", "阳光电源"),
    ("601138", "工业富联"),
    ("000725", "京东方A"),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(x: Any) -> float | None:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _normalize_market_code(raw: Any) -> str:
    s = str(raw or "").strip().upper()
    s = s.replace("SH", "").replace("SZ", "").replace("BJ", "")
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(6) if digits else ""


def _row_from_parts(
    *,
    code: str,
    name: str,
    price: float | None,
    pct: float | None,
    amount: float | None,
    turnover: float | None,
    reason: str,
    control: str,
) -> dict[str, Any]:
    return {
        "symbol": code,
        "name": name,
        "price": price,
        "pct_chg": pct,
        "amount": amount,
        "turnover": turnover,
        "heat_reasons": [reason],
        "is_control": code == control,
    }


def build_heat_pool_from_hot_rank(hot_df, *, control: str = CONTROL_SYMBOL) -> list[dict[str, Any]]:
    """Eastmoney stock_hot_rank_em — discussion/heat oriented."""
    df = hot_df.copy()
    # Robust column discovery (akshare column names vary by locale/version).
    cols = {str(c): c for c in df.columns}
    code_col = next((cols[c] for c in cols if "代码" in c or c.lower() == "code"), list(df.columns)[1])
    name_col = next((cols[c] for c in cols if "名称" in c or "name" in c.lower()), list(df.columns)[2])
    price_col = next((cols[c] for c in cols if "最新价" in c or c.lower() == "price"), None)
    pct_col = next((cols[c] for c in cols if c == "涨跌幅" or "涨跌幅" in c), None)
    rank_col = next((cols[c] for c in cols if "排名" in c or "rank" in c.lower()), list(df.columns)[0])

    picked: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        code = _normalize_market_code(row.get(code_col))
        if not code or len(code) != 6:
            continue
        name = str(row.get(name_col) or code)
        if "ST" in name.upper():
            continue
        price = _safe_float(row.get(price_col)) if price_col is not None else None
        if price is not None and price < MIN_PRICE:
            continue
        pct = _safe_float(row.get(pct_col)) if pct_col is not None else None
        rank = _safe_float(row.get(rank_col)) or (len(picked) + 1)
        # Lower rank number = hotter.
        heat = round(max(0.0, 1.0 - (float(rank) - 1) / max(len(df), 1)), 4)
        picked[code] = {
            "symbol": code,
            "name": name,
            "price": price,
            "pct_chg": pct,
            "amount": None,
            "turnover": None,
            "heat_reasons": ["hot_rank_em"],
            "is_control": code == control,
            "heat_score": heat,
            "_rank_raw": rank,
        }

    if control not in picked:
        picked[control] = _row_from_parts(
            code=control,
            name="贵州茅台",
            price=None,
            pct=None,
            amount=None,
            turnover=None,
            reason="control_baseline",
            control=control,
        )
        picked[control]["heat_score"] = 0.15
        picked[control]["_rank_raw"] = 999

    ordered = sorted(picked.values(), key=lambda x: x.get("heat_score") or 0.0, reverse=True)
    keep = ordered[:POOL_TARGET]
    if all(x["symbol"] != control for x in keep):
        keep.append(picked[control])
    n = max(len(keep), 1)
    for i, row in enumerate(keep):
        row["heat_rank"] = round((n - i) / n, 4)
        row.pop("_rank_raw", None)
    return keep


def build_heat_pool_from_spot(spot_df, *, control: str = CONTROL_SYMBOL) -> list[dict[str, Any]]:
    df = spot_df.copy()
    df["代码"] = df["代码"].astype(str).map(_normalize_market_code)
    df["名称"] = df["名称"].astype(str)
    df["_price"] = df["最新价"].map(_safe_float)
    df["_pct"] = df["涨跌幅"].map(_safe_float)
    df["_amount"] = df["成交额"].map(_safe_float)
    df["_turnover"] = df["换手率"].map(_safe_float)

    mask = (
        ~df["名称"].str.contains("ST", case=False, na=False)
        & df["_price"].notna()
        & (df["_price"] >= MIN_PRICE)
        & df["_amount"].notna()
    )
    base = df.loc[mask].copy()

    picked: dict[str, dict[str, Any]] = {}

    def _add(rows, reason: str) -> None:
        for _, row in rows.iterrows():
            code = str(row["代码"])
            if code in picked:
                picked[code]["heat_reasons"].append(reason)
                continue
            picked[code] = _row_from_parts(
                code=code,
                name=str(row["名称"]),
                price=row["_price"],
                pct=row["_pct"],
                amount=row["_amount"],
                turnover=row["_turnover"],
                reason=reason,
                control=control,
            )

    _add(base.sort_values("_amount", ascending=False).head(15), "top_amount")
    _add(base.sort_values("_turnover", ascending=False).head(10), "top_turnover")
    base["_abs_pct"] = base["_pct"].abs()
    _add(base.sort_values("_abs_pct", ascending=False).head(10), "top_abs_pct")

    ctrl_rows = df.loc[df["代码"] == control]
    if not ctrl_rows.empty:
        _add(ctrl_rows.head(1), "control_baseline")
    elif control not in picked:
        picked[control] = _row_from_parts(
            code=control,
            name="贵州茅台",
            price=None,
            pct=None,
            amount=None,
            turnover=None,
            reason="control_baseline",
            control=control,
        )

    amounts = [p["amount"] or 0.0 for p in picked.values()]
    max_amt = max(amounts) if amounts else 1.0
    for p in picked.values():
        amt_n = (p["amount"] or 0.0) / max_amt if max_amt else 0.0
        to_n = min((p["turnover"] or 0.0) / 20.0, 1.0)
        pct_n = min(abs(p["pct_chg"] or 0.0) / 10.0, 1.0)
        p["heat_score"] = round(0.55 * amt_n + 0.25 * to_n + 0.20 * pct_n, 4)

    ordered = sorted(picked.values(), key=lambda x: x["heat_score"], reverse=True)
    keep: list[dict[str, Any]] = []
    for row in ordered:
        if len(keep) >= POOL_TARGET and row["symbol"] != control:
            continue
        keep.append(row)
    if all(x["symbol"] != control for x in keep) and control in picked:
        keep.append(picked[control])
    n = max(len(keep), 1)
    for i, row in enumerate(keep):
        row["heat_rank"] = round((n - i) / n, 4)
    return keep


def build_heat_pool_fallback(*, control: str = CONTROL_SYMBOL) -> list[dict[str, Any]]:
    picked = []
    for i, (code, name) in enumerate(SEED_FALLBACK):
        row = _row_from_parts(
            code=code,
            name=name,
            price=None,
            pct=None,
            amount=None,
            turnover=None,
            reason="seed_fallback",
            control=control,
        )
        row["heat_score"] = round(1.0 - i / max(len(SEED_FALLBACK), 1), 4)
        picked.append(row)
    if all(x["symbol"] != control for x in picked):
        row = _row_from_parts(
            code=control,
            name="贵州茅台",
            price=None,
            pct=None,
            amount=None,
            turnover=None,
            reason="control_baseline",
            control=control,
        )
        row["heat_score"] = 0.2
        picked.append(row)
    n = max(len(picked), 1)
    for i, row in enumerate(picked):
        row["heat_rank"] = round((n - i) / n, 4)
    return picked[:POOL_TARGET]


def load_heat_pool() -> tuple[list[dict[str, Any]], str]:
    """Prefer discussion heat rank; fall back to spot / seed list."""
    try:
        hot = with_retry(lambda: ak.stock_hot_rank_em(), retries=3)
        if hot is not None and not hot.empty:
            return build_heat_pool_from_hot_rank(hot), "akshare.stock_hot_rank_em"
    except Exception as exc:  # noqa: BLE001
        print(f"hot_rank_em failed: {exc}")

    try:
        spot = with_retry(lambda: ak.stock_zh_a_spot_em(), retries=2)
        if spot is not None and not spot.empty:
            return build_heat_pool_from_spot(spot), "akshare.stock_zh_a_spot_em"
    except Exception as exc:  # noqa: BLE001
        print(f"spot_em failed: {exc}")

    print("Using seed fallback heat pool")
    return build_heat_pool_fallback(), "seed_fallback"

def probe_news(code: str, name: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    source_used = "eastmoney.search-api"
    err: str | None = None
    try:
        data = fetch_stock_news(code, page_size=50)
        items = list(data.get("items") or [])
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    if not items:
        try:
            data = fetch_stock_news_sina(code, page_size=30)
            items = list(data.get("items") or [])
            source_used = "sina.fallback"
        except Exception as exc:  # noqa: BLE001
            err = f"{err + '; ' if err else ''}{exc}"
    recent_30, _ = filter_recent(items, 30)
    recent_90, _ = filter_recent(items, 90)
    name_hit = 0
    for it in recent_30 or items[:20]:
        title = str(it.get("title") or "")
        if name and name[:2] in title:
            name_hit += 1
    return {
        "source_used": source_used,
        "total_returned": len(items),
        "news_30": len(recent_30),
        "news_90": len(recent_90),
        "name_hit_in_recent": name_hit,
        "sample_titles": [str(i.get("title") or "")[:80] for i in (recent_30 or items)[:5]],
        "error": err,
    }


def probe_announcements(code: str) -> dict[str, Any]:
    err: str | None = None
    items: list[dict[str, Any]] = []
    try:
        data = fetch_announcements(code)
        items = list(data.get("items") or [])
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    ann_30, _ = filter_recent(items, 30)
    ann_90, _ = filter_recent(items, 90)
    return {
        "ann_30": len(ann_30),
        "ann_90": len(ann_90),
        "total_returned": len(items),
        "sample_titles": [str(i.get("title") or "")[:80] for i in (ann_30 or items)[:3]],
        "error": err,
    }


def probe_holder(code: str) -> dict[str, Any]:
    err: str | None = None
    count = 0
    try:
        data = fetch_holder_reduce(code)
        count = int(data.get("count") or len(data.get("items") or []) or 0)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    return {"holder_events": count, "error": err}


def probe_financials(code: str) -> dict[str, Any]:
    err: str | None = None
    try:
        income = get_income_statement(code, max_periods=2)
        items = list(income.get("items") or [])
        err = income.get("error")
    except Exception as exc:  # noqa: BLE001
        items = []
        err = str(exc)
    latest = items[0] if items else {}
    has = bool(latest.get("operating_revenue") is not None and latest.get("net_profit_parent") is not None)
    return {
        "has_financials": has,
        "latest_report_date": latest.get("report_date"),
        "revenue": latest.get("operating_revenue"),
        "net_profit_parent": latest.get("net_profit_parent"),
        "error": err,
    }


def probe_eps(code: str) -> dict[str, Any]:
    err: str | None = None
    consensus: list[dict[str, Any]] = []
    try:
        report = run_ths_poc(code)
        consensus = list(report.get("consensus_normalized") or [])
        if not consensus:
            notes = report.get("quality_notes") or []
            err = "; ".join(notes) if notes else "no_consensus"
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    eps_rows = [c for c in consensus if str(c.get("metric") or "").upper() in {"EPS", "每股收益"} or "EPS" in str(c.get("metric") or "").upper()]
    if not eps_rows and consensus:
        eps_rows = consensus
    return {
        "has_eps_consensus": len(consensus) > 0,
        "consensus_count": len(consensus),
        "sample": eps_rows[:2] or consensus[:2],
        "error": err,
    }


def score_row(
    *,
    has_financials: bool,
    has_eps: bool,
    news_30: int,
    ann_30: int,
    holder_events: int,
    heat_rank: float,
) -> float:
    return round(
        1.5 * (1.0 if has_financials else 0.0)
        + 1.2 * (1.0 if has_eps else 0.0)
        + 1.0 * math.log1p(max(news_30, 0))
        + 1.0 * math.log1p(max(ann_30, 0))
        + 0.8 * math.log1p(max(holder_events, 0))
        + 0.4 * float(heat_rank or 0.0),
        4,
    )


def gaps_for(row: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    if not row.get("has_financials"):
        gaps.append("缺少可用利润表营收/归母净利")
    if not row.get("has_eps_consensus"):
        gaps.append("缺少EPS一致预期")
    if (row.get("news_30") or 0) == 0:
        gaps.append("近30天个股新闻为空")
    elif (row.get("name_hit_in_recent") or 0) == 0 and (row.get("news_30") or 0) > 0:
        gaps.append("近30天新闻标题几乎不含公司名（可能偏宏观/行业噪音）")
    if (row.get("ann_30") or 0) == 0:
        gaps.append("近30天公告为空")
    if (row.get("holder_events") or 0) == 0:
        gaps.append("无增减持事件记录")
    return gaps


def probe_symbol(base: dict[str, Any]) -> dict[str, Any]:
    code = normalize_symbol(base["symbol"])
    name = str(base.get("name") or "")
    news = probe_news(code, name)
    time.sleep(0.25)
    ann = probe_announcements(code)
    time.sleep(0.2)
    holder = probe_holder(code)
    time.sleep(0.2)
    fin = probe_financials(code)
    time.sleep(0.2)
    eps = probe_eps(code)

    out = {
        **base,
        "symbol": code,
        "news_30": news["news_30"],
        "news_90": news["news_90"],
        "news_source": news["source_used"],
        "name_hit_in_recent": news["name_hit_in_recent"],
        "news_sample_titles": news["sample_titles"],
        "ann_30": ann["ann_30"],
        "ann_90": ann["ann_90"],
        "ann_sample_titles": ann["sample_titles"],
        "holder_events": holder["holder_events"],
        "has_financials": fin["has_financials"],
        "latest_report_date": fin["latest_report_date"],
        "has_eps_consensus": eps["has_eps_consensus"],
        "eps_sample": eps["sample"],
        "probe_errors": {
            k: v
            for k, v in {
                "news": news.get("error"),
                "announcements": ann.get("error"),
                "holder": holder.get("error"),
                "financials": fin.get("error"),
                "eps": eps.get("error"),
            }.items()
            if v
        },
    }
    out["score"] = score_row(
        has_financials=bool(out["has_financials"]),
        has_eps=bool(out["has_eps_consensus"]),
        news_30=int(out["news_30"] or 0),
        ann_30=int(out["ann_30"] or 0),
        holder_events=int(out["holder_events"] or 0),
        heat_rank=float(out.get("heat_rank") or 0.0),
    )
    out["gaps"] = gaps_for(out)
    return out


def main() -> int:
    patch_requests_no_proxy()
    print("Loading heat pool...")
    pool, heat_source = load_heat_pool()
    print(f"Heat source: {heat_source}")
    print(f"Heat pool size: {len(pool)}")
    for i, p in enumerate(pool[:8], 1):
        print(f"  heat#{i} {p['symbol']} {p['name']} heat={p['heat_score']}")

    results: list[dict[str, Any]] = []
    for i, base in enumerate(pool, 1):
        print(f"[{i}/{len(pool)}] probing {base['symbol']} {base['name']} ...")
        try:
            row = probe_symbol(base)
        except Exception as exc:  # noqa: BLE001
            row = {
                **base,
                "score": 0.0,
                "gaps": [f"probe_failed: {exc}"],
                "probe_errors": {"fatal": str(exc)},
                "news_30": 0,
                "ann_30": 0,
                "holder_events": 0,
                "has_financials": False,
                "has_eps_consensus": False,
            }
        results.append(row)
        print(
            f"    score={row.get('score')} news30={row.get('news_30')} "
            f"ann30={row.get('ann_30')} fin={row.get('has_financials')} eps={row.get('has_eps_consensus')}"
        )
        time.sleep(0.35)

    ranked = sorted(results, key=lambda r: (r.get("score") or 0.0, r.get("heat_score") or 0.0), reverse=True)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i

    top10 = ranked[:10]
    control = next((r for r in ranked if r.get("symbol") == CONTROL_SYMBOL), None)

    report = {
        "generated_at": _now_iso(),
        "mode": "demo_prescan_no_llm",
        "heat_source": heat_source,
        "control_symbol": CONTROL_SYMBOL,
        "pool_size": len(pool),
        "scoring": (
            "1.5*has_financials + 1.2*has_eps + 1.0*log1p(news_30) + "
            "1.0*log1p(ann_30) + 0.8*log1p(holder) + 0.4*heat_rank"
        ),
        "top10": top10,
        "control": control,
        "all_candidates": ranked,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== TOP 10 Demo candidates ===")
    print(f"{'rk':>2} {'code':6} {'name':8} {'score':>6} {'news30':>6} {'ann30':>5} {'fin':>3} {'eps':>3} {'heat':>5} gaps")
    for r in top10:
        print(
            f"{r['rank']:2d} {r['symbol']:6} {str(r.get('name') or '')[:8]:8} "
            f"{r.get('score'):6.3f} {r.get('news_30') or 0:6d} {r.get('ann_30') or 0:5d} "
            f"{'Y' if r.get('has_financials') else 'N':>3} {'Y' if r.get('has_eps_consensus') else 'N':>3} "
            f"{r.get('heat_score') or 0:5.2f} {';'.join((r.get('gaps') or [])[:2])}"
        )
    if control:
        print(
            f"\nControl {CONTROL_SYMBOL} rank={control.get('rank')} "
            f"score={control.get('score')} news30={control.get('news_30')} "
            f"ann30={control.get('ann_30')} gaps={control.get('gaps')}"
        )
    print(f"\nWrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
