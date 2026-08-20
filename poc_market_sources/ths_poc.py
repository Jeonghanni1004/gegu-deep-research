"""Tonghuashun (同花顺) consensus estimate PoC."""

from __future__ import annotations

import re
from io import StringIO
from typing import Any

import pandas as pd

from .common import attempt, get, now_iso


STOCK_CODE = "600519"


def fetch_worth_page(code: str = STOCK_CODE) -> dict[str, Any]:
    """TradingAgents `_ths_eps_forecast` — parse worth.html tables."""
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    resp = get(
        url,
        headers={
            "Referer": "https://basic.10jqka.com.cn/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    meta = {
        "request": {"method": "GET", "url": url},
        "http_status": resp.status_code,
        "content_type": resp.headers.get("Content-Type"),
        "bytes": len(resp.content),
        "final_url": str(resp.url),
    }
    resp.raise_for_status()
    # THS often returns GBK
    resp.encoding = resp.apparent_encoding or "gbk"
    html = resp.text
    blocked = any(x in html for x in ("访问受限", "验证码", "deny", "Forbidden"))
    tables = []
    try:
        dfs = pd.read_html(StringIO(html))
    except ValueError:
        dfs = []
    for i, df in enumerate(dfs):
        flat = df.copy()
        flat.columns = [
            "_".join([str(x) for x in c if str(x) != "nan"]).strip("_")
            if isinstance(c, tuple)
            else str(c)
            for c in flat.columns
        ]
        preview_records = []
        for row in flat.head(8).astype(str).to_dict(orient="records"):
            preview_records.append({str(k): v for k, v in row.items()})
        tables.append(
            {
                "index": i,
                "columns": [str(c) for c in flat.columns.tolist()],
                "shape": list(flat.shape),
                "preview": preview_records,
            }
        )

    eps_table = None
    for df in dfs:
        cols = [str(c) for c in df.columns]
        flat = " ".join(cols)
        if "每股收益" in flat or ("均值" in flat and "预测" in flat):
            eps_table = df
            break
    if eps_table is None and dfs:
        # heuristic: first table with year-like values
        for df in dfs:
            text = df.astype(str).to_csv(index=False)
            if re.search(r"20\d{2}", text) and ("收益" in text or "EPS" in text.upper() or "均值" in text):
                eps_table = df
                break

    consensus = []
    updated_at = None
    # Try extract update time from page
    m = re.search(r"(更新时间|数据日期|截至)[:：\s]*([0-9]{4}[-/年][0-9]{1,2}[-/月][0-9]{1,2})", html)
    if m:
        updated_at = m.group(2).replace("年", "-").replace("月", "-").replace("/", "-")

    if eps_table is not None:
        # Normalize multiindex columns if any
        df = eps_table.copy()
        df.columns = [
            "_".join([str(x) for x in c if str(x) != "nan"]).strip("_")
            if isinstance(c, tuple)
            else str(c)
            for c in df.columns
        ]
        records = df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")
        for row in records:
            year = None
            value = None
            inst = None
            vmin = None
            vmax = None
            # flexible field hunt
            for k, v in row.items():
                ks = str(k)
                vs = "" if v is None else str(v)
                if year is None and re.fullmatch(r"20\d{2}", vs.strip()):
                    year = vs.strip()
                if "年度" in ks or ks in {"年份", "年"} or ks.endswith("年份"):
                    year = str(v).strip() if v is not None else year
                if "均值" in ks or "一致" in ks:
                    try:
                        value = float(str(v).replace(",", ""))
                    except (TypeError, ValueError):
                        value = v
                if "最小" in ks:
                    try:
                        vmin = float(str(v).replace(",", ""))
                    except (TypeError, ValueError):
                        vmin = v
                if "最大" in ks:
                    try:
                        vmax = float(str(v).replace(",", ""))
                    except (TypeError, ValueError):
                        vmax = v
                if "机构" in ks:
                    try:
                        inst = int(float(str(v)))
                    except (TypeError, ValueError):
                        inst = v
            if year or value is not None:
                consensus.append(
                    {
                        "type": "consensus_estimate",
                        "stock_code": code,
                        "metric": "EPS",
                        "forecast_year": year,
                        "value": value,
                        "min_value": vmin,
                        "max_value": vmax,
                        "institution_count": inst,
                        "updated_at": updated_at,
                        "source": "同花顺",
                        "raw_row": {
                            str(k): (
                                None
                                if v is None or (isinstance(v, float) and pd.isna(v))
                                else (str(v) if not isinstance(v, (int, float, str, bool)) else v)
                            )
                            for k, v in row.items()
                        },
                    }
                )

    # Rating / target price sniff
    rating_hits = re.findall(r"(买入|增持|中性|减持|卖出|目标价[:：]?\s*[0-9.]+)", html)
    has_history_chart = "预测走势" in html or "历史走势" in html or "一致预期走势" in html

    return {
        "meta": meta,
        "blocked_guess": blocked,
        "table_count": len(tables),
        "tables": tables[:6],
        "consensus": consensus,
        "updated_at_guess": updated_at,
        "rating_or_target_text_hits": rating_hits[:20],
        "has_history_timeseries_hint_in_html": has_history_chart,
        "html_title": (re.search(r"<title>(.*?)</title>", html, re.I | re.S) or [None, ""])[1].strip(),
    }


def fetch_ths_ajax_worth(code: str = STOCK_CODE) -> dict[str, Any]:
    """Probe possible JSON endpoints under basic.10jqka (may 403/empty)."""
    candidates = [
        f"https://basic.10jqka.com.cn/api/stock/finance/{code}_worth.json",
        f"https://basic.10jqka.com.cn/new/{code}/worth.js",
        f"https://d.10jqka.com.cn/v2/realhead/hs_{code}/last.js",
    ]
    results = []
    for url in candidates:
        try:
            resp = get(url, headers={"Referer": f"https://basic.10jqka.com.cn/new/{code}/worth.html"})
            results.append(
                {
                    "url": url,
                    "http_status": resp.status_code,
                    "content_type": resp.headers.get("Content-Type"),
                    "bytes": len(resp.content),
                    "preview": resp.text[:240],
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"url": url, "error": str(exc)})
    return {"candidates": results}


def run_ths_poc(code: str = STOCK_CODE) -> dict[str, Any]:
    report: dict[str, Any] = {
        "stock_code": code,
        "retrieved_at": now_iso(),
        "source": "tonghuashun",
        "reference": "TradingAgents-astock _ths_eps_forecast / basic.10jqka.com.cn worth.html",
        "attempts": {},
        "quality_notes": [],
    }

    worth = attempt("worth_html", lambda: fetch_worth_page(code))
    ajax = attempt("ajax_probes", lambda: fetch_ths_ajax_worth(code))
    report["attempts"]["worth_html"] = {k: worth[k] for k in ("ok", "elapsed_sec", "error")}
    report["attempts"]["ajax_probes"] = {k: ajax[k] for k in ("ok", "elapsed_sec", "error")}
    report["worth_html"] = worth.get("data") if worth["ok"] else {"ok": False, "error": worth["error"]}
    report["ajax_probes"] = ajax.get("data") if ajax["ok"] else {"ok": False, "error": ajax["error"]}

    consensus = []
    if worth["ok"]:
        consensus = (worth["data"] or {}).get("consensus") or []
    report["consensus_normalized"] = consensus
    report["summary"] = {
        "got_current_consensus": len(consensus) > 0,
        "metrics_found": sorted({c.get("metric") for c in consensus}),
        "forecast_years": [c.get("forecast_year") for c in consensus],
        "has_institution_count": any(c.get("institution_count") not in (None, "") for c in consensus),
        "has_updated_at": any(c.get("updated_at") for c in consensus),
        "has_rating_or_target_text": bool((worth.get("data") or {}).get("rating_or_target_text_hits")),
        "has_historical_timeseries_api": False,
        "historical_timeseries_note": (
            "本 PoC 仅拿到 worth.html 当前截面表格；未发现可用的一致预期历史时间序列 JSON。"
            "HTML 中可能有图表脚本提示，但不等于可稳定抽取的历史序列。"
        ),
    }
    if not consensus:
        report["quality_notes"].append("未解析到 EPS 一致预期表，可能被反爬或页面结构变化。")
    else:
        report["quality_notes"].append("已拿到当前一致预期截面；历史变化时间序列未能通过公开接口稳定获取。")
    return report
