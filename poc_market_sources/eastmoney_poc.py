"""Eastmoney PoC — news / announcements / events (TradingAgents-style)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

from .common import attempt, get, now_iso


STOCK_CODE = "600519"
STOCK_NAME = "贵州茅台"


def _parse_jsonp(text: str) -> dict:
    start = text.index("(") + 1
    end = text.rindex(")")
    return json.loads(text[start:end])


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_stock_news(code: str = STOCK_CODE, page_size: int = 50) -> dict[str, Any]:
    """Mirror TradingAgents `_fetch_news_eastmoney`."""
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner = {
        "uid": "",
        "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "",
                "postTag": "",
            }
        },
    }
    params = {
        "cb": "jQuery35108723733748578402_1693632913001",
        "param": json.dumps(inner, ensure_ascii=False, separators=(",", ":")),
        "_": "1693632913001",
    }
    headers = {
        "Referer": f"https://so.eastmoney.com/news/s?keyword={code}",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }
    resp = get(url, params=params, headers=headers, eastmoney=True)
    meta = {
        "request": {"method": "GET", "url": url, "params_keys": list(params.keys())},
        "http_status": resp.status_code,
        "content_type": resp.headers.get("Content-Type"),
        "bytes": len(resp.content),
    }
    resp.raise_for_status()
    payload = _parse_jsonp(resp.text)
    result_keys = list((payload.get("result") or {}).keys())
    articles_raw = (payload.get("result") or {}).get("cmsArticleWebOld") or []
    items = []
    for a in articles_raw:
        title = _strip_html(a.get("title", ""))
        content = _strip_html(a.get("content", ""))
        items.append(
            {
                "type": "stock_news",
                "stock_code": code,
                "title": title,
                "published_at": a.get("date") or a.get("createTime") or "",
                "source": a.get("mediaName") or "东方财富",
                "url": a.get("url") or "",
                "content": content,
                "is_announcement_guess": any(
                    k in title for k in ("公告", "半年报", "年报", "季报", "披露")
                ),
                "raw_keys": sorted(a.keys()),
            }
        )
    return {"meta": meta, "result_keys": result_keys, "count": len(items), "items": items}


def fetch_stock_news_sina(code: str = STOCK_CODE, page_size: int = 30) -> dict[str, Any]:
    """TradingAgents `_fetch_news_sina` fallback (not Eastmoney, but same project pattern)."""
    prefix = "sh" if code.startswith("6") else "sz"
    url = (
        "https://vip.stock.finance.sina.com.cn/corp/view/"
        f"vCB_AllNewsStock.php?symbol={prefix}{code}&Page=1"
    )
    resp = get(url, headers={"Referer": "https://finance.sina.com.cn/"})
    meta = {
        "request": {"method": "GET", "url": url},
        "http_status": resp.status_code,
        "bytes": len(resp.content),
        "note": "TradingAgents fallback when Eastmoney stock news is empty",
    }
    resp.raise_for_status()
    resp.encoding = "gb2312"
    html = resp.text
    rows = re.findall(
        r"(\d{4}-\d{2}-\d{2})\s*(?:&nbsp;)*(\d{2}:\d{2})\s*(?:&nbsp;)*"
        r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]*>([^<]+)</a>",
        html,
    )
    items = []
    for date_str, time_str, link, title in rows[:page_size]:
        items.append(
            {
                "type": "stock_news",
                "stock_code": code,
                "title": title.strip(),
                "published_at": f"{date_str} {time_str}:00",
                "source": "新浪财经",
                "url": link,
                "content": "",
                "is_announcement_guess": "公告" in title,
            }
        )
    return {"meta": meta, "count": len(items), "items": items}


def fetch_global_news_em(page_size: int = 30) -> dict[str, Any]:
    """Eastmoney 7x24 / column news — works even when search-api is wind-controlled."""
    url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
    params = {
        "client": "web",
        "biz": "web_news_col",
        "column": "350",
        "order": "1",
        "needInteractData": "0",
        "page_index": "1",
        "page_size": str(page_size),
        "req_trace": "poc600519",
        "fields": "code,showTime,title,mediaName,summary,url,uniqueUrl,Np_dst",
        "types": "1,20",
    }
    resp = get(url, params=params, headers={"Referer": "https://finance.eastmoney.com/"}, eastmoney=True)
    meta = {
        "request": {"method": "GET", "url": url, "params": params},
        "http_status": resp.status_code,
        "bytes": len(resp.content),
    }
    resp.raise_for_status()
    payload = resp.json()
    rows = ((payload.get("data") or {}).get("list")) or []
    items = []
    for row in rows:
        title = row.get("title") or ""
        summary = row.get("summary") or ""
        related = any(k in f"{title}{summary}" for k in (STOCK_CODE, STOCK_NAME, "茅台", "白酒"))
        items.append(
            {
                "type": "market_news",
                "stock_code": STOCK_CODE if related else None,
                "title": title,
                "published_at": row.get("showTime") or "",
                "source": row.get("mediaName") or "东方财富",
                "url": row.get("uniqueUrl") or row.get("url") or "",
                "content": summary,
                "stock_related": related,
                "category": "company" if related else "market",
            }
        )
    return {"meta": meta, "count": len(items), "items": items, "related_count": sum(1 for i in items if i["stock_related"])}


def fetch_announcements(code: str = STOCK_CODE, page_size: int = 30) -> dict[str, Any]:
    """Eastmoney notice list (not in TradingAgents core, but same EM family)."""
    url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    params = {
        "page_size": str(page_size),
        "page_index": "1",
        "ann_type": "A",
        "client_source": "web",
        "stock_list": code,
        "f_node": "0",
        "s_node": "0",
    }
    resp = get(
        url,
        params=params,
        headers={"Referer": f"https://data.eastmoney.com/notices/stock/{code}.html"},
        eastmoney=True,
    )
    meta = {
        "request": {"method": "GET", "url": url, "params": params},
        "http_status": resp.status_code,
        "bytes": len(resp.content),
    }
    resp.raise_for_status()
    data = resp.json()
    rows = (data.get("data") or {}).get("list") or []
    items = []
    for row in rows:
        art_code = row.get("art_code") or ""
        title = row.get("title") or ""
        notice_date = row.get("notice_date") or row.get("display_time") or ""
        columns = row.get("columns") or []
        col_names = [c.get("column_name") for c in columns if isinstance(c, dict)]
        url_detail = (
            f"https://data.eastmoney.com/notices/detail/{code}/{art_code}.html"
            if art_code
            else ""
        )
        items.append(
            {
                "type": "announcement",
                "stock_code": code,
                "title": title,
                "published_at": notice_date,
                "source": "东方财富公告",
                "url": url_detail,
                "content": "",
                "column_names": col_names,
                "art_code": art_code,
            }
        )
    return {"meta": meta, "count": len(items), "items": items, "raw_top_keys": list(data.keys())}


def _datacenter(report_name: str, filter_str: str, page_size: int = 50) -> dict[str, Any]:
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "filter": filter_str,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": "NOTICE_DATE" if "SHARE" in report_name or "HOLDER" in report_name else "TRADE_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    # unlock/shareholder reports use different date columns; let API ignore bad sort
    resp = get(url, params=params, headers={"Referer": "https://data.eastmoney.com/"}, eastmoney=True)
    meta = {
        "request": {"method": "GET", "url": url, "reportName": report_name, "filter": filter_str},
        "http_status": resp.status_code,
    }
    resp.raise_for_status()
    payload = resp.json()
    rows = ((payload.get("result") or {}).get("data")) or []
    return {"meta": meta, "count": len(rows), "items": rows[:20], "message": payload.get("message")}


def fetch_dragon_tiger(code: str = STOCK_CODE, days: int = 90) -> dict[str, Any]:
    end = datetime.now().date()
    start = end - timedelta(days=days)
    return _datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=(
            f"(TRADE_DATE>='{start.isoformat()}')"
            f"(TRADE_DATE<='{end.isoformat()}')"
            f'(SECURITY_CODE="{code}")'
        ),
    )


def fetch_lockup(code: str = STOCK_CODE) -> dict[str, Any]:
    # Free-float / restricted share unlock calendar
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": "RPT_LIFT_STAGE",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": "1",
        "pageSize": "20",
        "sortColumns": "FREE_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    resp = get(url, params=params, headers={"Referer": "https://data.eastmoney.com/"}, eastmoney=True)
    meta = {
        "request": {"method": "GET", "url": url, "reportName": "RPT_LIFT_STAGE"},
        "http_status": resp.status_code,
    }
    resp.raise_for_status()
    payload = resp.json()
    rows = ((payload.get("result") or {}).get("data")) or []
    return {"meta": meta, "count": len(rows), "items": rows[:20], "message": payload.get("message")}


def fetch_holder_reduce(code: str = STOCK_CODE) -> dict[str, Any]:
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": "RPT_SHARE_HOLDER_INCREASE",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": "1",
        "pageSize": "20",
        "sortColumns": "NOTICE_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    resp = get(url, params=params, headers={"Referer": "https://data.eastmoney.com/"}, eastmoney=True)
    meta = {
        "request": {"method": "GET", "url": url, "reportName": params["reportName"]},
        "http_status": resp.status_code,
    }
    resp.raise_for_status()
    payload = resp.json()
    rows = ((payload.get("result") or {}).get("data")) or []
    return {"meta": meta, "count": len(rows), "items": rows[:20], "message": payload.get("message")}


def fetch_fund_flow_hist(code: str = STOCK_CODE) -> dict[str, Any]:
    """Historical daily fund flow via push2his (often blocked on some networks)."""
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "lmt": "0",
        "klt": "101",
        "secid": secid,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
    }
    resp = get(url, params=params, headers={"Referer": "https://data.eastmoney.com/"}, eastmoney=True)
    meta = {
        "request": {"method": "GET", "url": url, "params": params},
        "http_status": resp.status_code,
        "bytes": len(resp.content),
    }
    resp.raise_for_status()
    payload = resp.json()
    klines = ((payload.get("data") or {}).get("klines")) or []
    parsed = []
    for line in klines[-30:]:
        parts = str(line).split(",")
        if len(parts) >= 6:
            parsed.append(
                {
                    "date": parts[0],
                    "main_net": parts[1],
                    "small_net": parts[2],
                    "mid_net": parts[3],
                    "large_net": parts[4],
                    "super_net": parts[5],
                }
            )
    return {"meta": meta, "count": len(parsed), "items": parsed, "raw_klines_total": len(klines)}


def filter_recent(items: list[dict], days: int, date_key: str = "published_at") -> tuple[list[dict], dict]:
    cutoff = datetime.now() - timedelta(days=days)
    kept = []
    unparsed = 0
    for item in items:
        raw = str(item.get(date_key) or "")[:19]
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
            try:
                dt = datetime.strptime(raw.replace("T", " ")[:19], fmt)
                break
            except ValueError:
                continue
        if dt is None:
            unparsed += 1
            continue
        if dt >= cutoff:
            kept.append(item)
    return kept, {"cutoff": cutoff.isoformat(timespec="seconds"), "unparsed": unparsed, "kept": len(kept)}


def run_eastmoney_poc(code: str = STOCK_CODE) -> dict[str, Any]:
    report: dict[str, Any] = {
        "stock_code": code,
        "stock_name": STOCK_NAME,
        "retrieved_at": now_iso(),
        "source": "eastmoney",
        "reference": "TradingAgents-astock tradingagents/dataflows/a_stock.py",
        "attempts": {},
        "quality_notes": [],
    }

    news_attempt = attempt("stock_news", lambda: fetch_stock_news(code, page_size=50))
    report["attempts"]["stock_news"] = {
        k: news_attempt[k] for k in ("ok", "elapsed_sec", "error")
    }
    news_data = news_attempt.get("data") or {}
    items = news_data.get("items") or []
    news_source_used = "eastmoney.search-api"
    if not items:
        sina_attempt = attempt("stock_news_sina_fallback", lambda: fetch_stock_news_sina(code))
        report["attempts"]["stock_news_sina_fallback"] = {
            k: sina_attempt[k] for k in ("ok", "elapsed_sec", "error")
        }
        if sina_attempt["ok"]:
            news_data = sina_attempt["data"] or {}
            items = news_data.get("items") or []
            news_source_used = "sina.vCB_AllNewsStock (TradingAgents fallback)"
            report["quality_notes"].append(
                "东财 search-api 仅返回 passportWeb（个股新闻 cmsArticleWebOld 为空），已按 TradingAgents 回退到新浪个股新闻。"
            )
    recent_30, filter_meta_30 = filter_recent(items, 30)
    recent_90, filter_meta_90 = filter_recent(items, 90)
    titles = [i["title"] for i in items]
    dup = len(titles) - len(set(titles))
    report["news"] = {
        "source_used": news_source_used,
        "total_returned": len(items),
        "recent_30_count": len(recent_30),
        "recent_90_count": len(recent_90),
        "filter_30": filter_meta_30,
        "filter_90": filter_meta_90,
        "duplicate_titles": dup,
        "has_content_ratio": (
            round(sum(1 for i in items if i.get("content")) / len(items), 3) if items else 0
        ),
        "avg_content_len": (
            int(sum(len(i.get("content") or "") for i in items) / len(items)) if items else 0
        ),
        "announcement_guess_count": sum(1 for i in items if i.get("is_announcement_guess")),
        "sample": items[:5],
        "recent_30_sample": recent_30[:10],
        "meta": news_data.get("meta"),
        "result_keys": news_data.get("result_keys"),
    }
    if len(recent_30) == 0 and len(recent_90) > 0:
        report["quality_notes"].append("最近30天新闻为空，但90天有数据；已扩大到90天窗口。")
    if len(items) == 0:
        report["quality_notes"].append(
            "个股新闻东财+新浪均空。东财 search-api 对部分住宅 IP 间歇只返回 passportWeb（#18）。"
        )

    global_attempt = attempt("global_news_em", lambda: fetch_global_news_em(30))
    report["attempts"]["global_news_em"] = {
        k: global_attempt[k] for k in ("ok", "elapsed_sec", "error")
    }
    report["global_news_em"] = (
        global_attempt.get("data")
        if global_attempt["ok"]
        else {"ok": False, "error": global_attempt["error"]}
    )

    for key, fn in [
        ("announcements", lambda: fetch_announcements(code)),
        ("dragon_tiger_90d", lambda: fetch_dragon_tiger(code, days=90)),
        ("lockup", lambda: fetch_lockup(code)),
        ("holder_change", lambda: fetch_holder_reduce(code)),
        ("fund_flow_hist", lambda: fetch_fund_flow_hist(code)),
    ]:
        att = attempt(key, fn)
        report["attempts"][key] = {k: att[k] for k in ("ok", "elapsed_sec", "error")}
        data = att.get("data")
        if not att["ok"]:
            report[key] = {"ok": False, "error": att["error"]}
            continue
        if key == "announcements":
            ann_items = data.get("items") or []
            ann_30, ann_meta = filter_recent(ann_items, 30)
            ann_90, ann_meta_90 = filter_recent(ann_items, 90)
            report[key] = {
                "ok": True,
                "total_returned": len(ann_items),
                "recent_30_count": len(ann_30),
                "recent_90_count": len(ann_90),
                "filter_30": ann_meta,
                "filter_90": ann_meta_90,
                "sample": ann_30[:10] or ann_items[:5],
                "meta": data.get("meta"),
            }
            if len(ann_30) == 0 and len(ann_90) > 0:
                report["quality_notes"].append("公告：30天较少/为空，已扩大到90天窗口。")
        else:
            report[key] = {
                "ok": True,
                "count": data.get("count"),
                "sample": (data.get("items") or [])[:5],
                "meta": data.get("meta"),
                "message": data.get("message"),
            }

    return report
