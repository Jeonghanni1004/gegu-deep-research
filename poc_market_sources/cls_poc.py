"""Cailianpress (财联社) PoC — telegraph + keyword relevance filter."""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timedelta
from typing import Any

from .common import attempt, get, now_iso

STOCK_CODE = "600519"
STOCK_NAME = "贵州茅台"
KEYWORDS = ["贵州茅台", "茅台", "600519", "白酒"]


def _cls_sign(params: dict[str, str]) -> str:
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.md5(hashlib.sha1(qs.encode()).hexdigest().encode()).hexdigest()


def _normalize_item(item: dict, api: str) -> dict[str, Any]:
    ts = item.get("ctime") or item.get("time") or item.get("modified_time")
    published = ""
    if ts:
        try:
            published = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OSError):
            published = str(ts)
    title = item.get("title") or item.get("brief") or ""
    content = item.get("content") or item.get("brief") or item.get("sharecontent") or ""
    article_id = item.get("id") or item.get("article_id") or ""
    url = ""
    if article_id:
        url = f"https://www.cls.cn/detail/{article_id}"
    elif item.get("shareurl"):
        url = item.get("shareurl")
    subjects = item.get("subjects") or item.get("stock_list") or []
    text_blob = f"{title}\n{content}"
    matched = [k for k in KEYWORDS if k in text_blob]
    stock_related = bool(matched) or any(
        STOCK_CODE in str(s) or STOCK_NAME in str(s) or "茅台" in str(s) for s in subjects
    )
    category = "company" if stock_related else "market"
    if any(k in text_blob for k in ("政策", "央行", "宏观", "降准", "降息")):
        category = "macro"
    elif any(k in text_blob for k in ("白酒", "消费", "食品饮料")) and not stock_related:
        category = "industry"
    return {
        "type": "market_news",
        "stock_code": STOCK_CODE if stock_related else None,
        "title": re.sub(r"<[^>]+>", "", str(title)).strip(),
        "published_at": published,
        "source": "财联社",
        "url": url,
        "content": re.sub(r"<[^>]+>", "", str(content)).strip(),
        "category": category,
        "matched_keywords": matched,
        "stock_related": stock_related,
        "api": api,
        "raw_subjects": subjects[:5] if isinstance(subjects, list) else subjects,
    }


def fetch_cls_v1_roll(page_size: int = 100, retries: int = 3, max_pages: int = 5) -> dict[str, Any]:
    """Signed v1 roll API with optional backward pagination via last_time.

    Plain requests often returns empty roll_data on this network.
    curl_cffi Chrome impersonation is required for stable access.
    """
    from curl_cffi import requests as creq

    all_items: list[dict[str, Any]] = []
    last_time = ""
    pages_meta = []
    for page in range(max_pages):
        page_items = []
        last_meta = None
        for i in range(retries):
            params = {
                "appName": "CailianpressWeb",
                "os": "web",
                "sv": "7.7.5",
                "last_time": last_time,
                "refresh_type": "1" if not last_time else "2",
                "rn": str(page_size),
            }
            sign = _cls_sign(params)
            qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
            url = f"https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign}"
            resp = creq.get(
                url,
                impersonate="chrome124",
                headers={
                    "Referer": "https://www.cls.cn/telegraph",
                    "Accept": "application/json, text/plain, */*",
                },
                timeout=20,
            )
            last_meta = {
                "request": {
                    "method": "GET",
                    "url": "https://www.cls.cn/v1/roll/get_roll_list",
                    "signed": True,
                    "page": page + 1,
                    "attempt": i + 1,
                    "transport": "curl_cffi.chrome124",
                    "last_time": last_time,
                },
                "http_status": resp.status_code,
                "bytes": len(resp.content),
            }
            try:
                payload = resp.json()
            except Exception:
                time.sleep(0.4 * (i + 1))
                continue
            rows = ((payload.get("data") or {}).get("roll_data")) or []
            if rows:
                page_items = [_normalize_item(r, "v1/roll/get_roll_list") for r in rows]
                pages_meta.append({**last_meta, "count": len(page_items), "errno": payload.get("errno")})
                break
            time.sleep(0.4 * (i + 1))
        if not page_items:
            break
        # stop if this page largely duplicates already collected items
        existing_titles = {i.get("title") for i in all_items}
        novel = [i for i in page_items if i.get("title") not in existing_titles]
        if not novel:
            pages_meta.append({**(last_meta or {}), "count": 0, "duplicate_page": True})
            break
        all_items.extend(novel)
        oldest = None
        for it in novel:
            raw = it.get("published_at")
            try:
                ts = int(datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").timestamp())
            except Exception:
                continue
            if oldest is None or ts < oldest:
                oldest = ts
        if oldest is None:
            break
        last_time = str(oldest)
        if datetime.fromtimestamp(oldest) < datetime.now() - timedelta(days=90):
            break

    return {
        "meta": {"pages": pages_meta, "transport": "curl_cffi.chrome124"},
        "parse_ok": True,
        "count": len(all_items),
        "items": all_items,
        "pages_fetched": len(pages_meta),
    }


def fetch_cls_legacy_telegraph(page_size: int = 50) -> dict[str, Any]:
    """Legacy endpoint still referenced by TradingAgents-astock get_global_news."""
    url = "https://www.cls.cn/nodeapi/telegraphList"
    params = {"rn": str(page_size), "page": "1"}
    resp = get(url, params=params, headers={"Referer": "https://www.cls.cn/"})
    meta = {
        "request": {"method": "GET", "url": url, "params": params},
        "http_status": resp.status_code,
        "content_type": resp.headers.get("Content-Type"),
        "bytes": len(resp.content),
        "text_preview": resp.text[:240],
    }
    try:
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        return {
            "meta": meta,
            "parse_ok": False,
            "error": f"JSON parse failed (likely HTML after Next.js migration): {exc}",
            "items": [],
        }
    rows = ((payload.get("data") or {}).get("roll_data")) or []
    items = [_normalize_item(r, "nodeapi/telegraphList") for r in rows]
    return {"meta": meta, "parse_ok": True, "count": len(items), "items": items}


def fetch_cls_search(keyword: str, page: int = 1) -> dict[str, Any]:
    """Try website search endpoint (unstable / often empty)."""
    from curl_cffi import requests as creq

    params = {
        "app": "CailianpressWeb",
        "os": "web",
        "sv": "7.7.5",
        "keyword": keyword,
        "type": "telegram",
        "page": str(page),
    }
    sign = _cls_sign({k: str(v) for k, v in params.items()})
    resp = creq.get(
        "https://www.cls.cn/api/sw",
        params={**params, "sign": sign},
        impersonate="chrome124",
        headers={"Referer": "https://www.cls.cn/"},
        timeout=20,
    )
    meta = {
        "request": {"method": "GET", "url": "https://www.cls.cn/api/sw", "params": params},
        "http_status": resp.status_code,
        "content_type": resp.headers.get("Content-Type"),
        "bytes": len(resp.content),
        "text_preview": resp.text[:240],
        "transport": "curl_cffi.chrome124",
    }
    try:
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"meta": meta, "parse_ok": False, "error": str(exc), "items": []}

    data = payload.get("data") if isinstance(payload, dict) else None
    rows: list = []
    if isinstance(data, dict):
        for key in ("telegram", "roll_data", "list", "data"):
            if isinstance(data.get(key), list):
                rows = data.get(key) or []
                break
    elif isinstance(data, list):
        rows = data
    items = [_normalize_item(r, "api/sw") for r in rows if isinstance(r, dict)]
    return {
        "meta": meta,
        "parse_ok": True,
        "count": len(items),
        "items": items,
        "raw_top_keys": list(payload.keys()) if isinstance(payload, dict) else [],
    }


def filter_recent(items: list[dict], days: int) -> tuple[list[dict], dict]:
    cutoff = datetime.now() - timedelta(days=days)
    kept = []
    for item in items:
        raw = str(item.get("published_at") or "")
        try:
            dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if dt >= cutoff:
            kept.append(item)
    return kept, {"cutoff": cutoff.isoformat(timespec="seconds"), "kept": len(kept)}


def run_cls_poc(code: str = STOCK_CODE) -> dict[str, Any]:
    report: dict[str, Any] = {
        "stock_code": code,
        "stock_name": STOCK_NAME,
        "retrieved_at": now_iso(),
        "source": "cls",
        "reference": [
            "TradingAgents-astock get_global_news (legacy nodeapi/telegraphList)",
            "a-stock-data cls_telegraph (v1/roll/get_roll_list + local sign)",
        ],
        "attempts": {},
        "quality_notes": [],
    }

    v1 = attempt("v1_roll", lambda: fetch_cls_v1_roll(page_size=50, max_pages=6))
    legacy = attempt("legacy_telegraph", lambda: fetch_cls_legacy_telegraph(50))
    search_name = attempt("search_name", lambda: fetch_cls_search(STOCK_NAME))
    search_code = attempt("search_code", lambda: fetch_cls_search(code))

    for name, att in [
        ("v1_roll", v1),
        ("legacy_telegraph", legacy),
        ("search_name", search_name),
        ("search_code", search_code),
    ]:
        report["attempts"][name] = {k: att[k] for k in ("ok", "elapsed_sec", "error")}
        report[name] = att.get("data") if att["ok"] else {"ok": False, "error": att["error"]}

    primary_items: list[dict] = []
    if v1["ok"] and (v1["data"] or {}).get("items"):
        primary_items = v1["data"]["items"]
        report["primary_api"] = "v1/roll/get_roll_list"
        report["quality_notes"].append(
            "稳定访问依赖 curl_cffi Chrome impersonation；plain requests 常返回空 roll_data。"
        )
    elif legacy["ok"] and (legacy["data"] or {}).get("items"):
        primary_items = legacy["data"]["items"]
        report["primary_api"] = "nodeapi/telegraphList"
        report["quality_notes"].append("使用 TradingAgents 旧接口成功；新签名接口未返回可用数据。")
    else:
        report["primary_api"] = None
        report["quality_notes"].append("财联社主接口均未返回可用快讯。")

    # Also merge search hits if any
    for block in (search_name.get("data"), search_code.get("data")):
        if block and block.get("items"):
            primary_items.extend(block["items"])

    # dedupe by title+time
    seen = set()
    deduped = []
    for item in primary_items:
        key = (item.get("title"), item.get("published_at"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    primary_items = deduped

    related = [i for i in primary_items if i.get("stock_related")]
    related_30, meta_30 = filter_recent(related, 30)
    related_90, meta_90 = filter_recent(related, 90)
    all_30, all_meta_30 = filter_recent(primary_items, 30)
    industry = [i for i in all_30 if i.get("category") in {"industry", "macro"}]

    report["summary"] = {
        "roll_total": len(primary_items),
        "stock_related_total": len(related),
        "stock_related_30d": len(related_30),
        "stock_related_90d": len(related_90),
        "all_30d": len(all_30),
        "industry_or_macro_in_30d_sample": len(industry),
        "filter_30": meta_30,
        "filter_90": meta_90,
        "all_30_meta": all_meta_30,
        "can_filter_by_code_native": False,
        "can_filter_by_keyword_client_side": True,
        "has_published_at": all(bool(i.get("published_at")) for i in primary_items[:10])
        if primary_items
        else False,
        "has_title": all(bool(i.get("title")) for i in primary_items[:10]) if primary_items else False,
        "has_content": all(bool(i.get("content")) for i in primary_items[:10]) if primary_items else False,
        "has_url": all(bool(i.get("url")) for i in primary_items[:10]) if primary_items else False,
        "related_30_sample": related_30[:10],
        "related_90_sample": related_90[:10],
        "market_30_sample": all_30[:10],
    }
    if len(related_30) == 0 and len(related_90) > 0:
        report["quality_notes"].append("与茅台直接相关快讯在30天窗口不足，已扩大到90天。")
    if primary_items and len(related_30) == 0 and len(related_90) == 0:
        report["quality_notes"].append(
            "已拿到全市场滚动快讯，但本页未命中茅台关键词；需持续滚动/扩大窗口或改用搜索。"
        )
    if not (search_name.get("data") or {}).get("items") and not (search_code.get("data") or {}).get("items"):
        report["quality_notes"].append("cls.cn/api/sw 关键词搜索未返回可用结构化结果。")
    return report
