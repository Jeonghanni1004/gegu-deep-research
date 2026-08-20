"""Deep probe failing endpoints with raw response capture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from poc_market_sources.common import get, save_json


def cls_sign(params: dict[str, str]) -> str:
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.md5(hashlib.sha1(qs.encode()).hexdigest().encode()).hexdigest()


def probe_cls():
    out = {}
    # v1
    params = {
        "appName": "CailianpressWeb",
        "os": "web",
        "sv": "7.7.5",
        "last_time": "",
        "refresh_type": "1",
        "rn": "50",
    }
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    sign = cls_sign(params)
    url = f"https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign}"
    r = get(url, headers={"Referer": "https://www.cls.cn/"})
    out["v1"] = {
        "status": r.status_code,
        "ctype": r.headers.get("Content-Type"),
        "preview": r.text[:800],
        "json": None,
    }
    try:
        out["v1"]["json"] = r.json()
    except Exception as e:
        out["v1"]["json_error"] = str(e)

    # try with app=CailianpressWeb variant seen on site
    params2 = {
        "app": "CailianpressWeb",
        "os": "web",
        "sv": "8.4.6",
        "last_time": "",
        "refresh_type": "1",
        "rn": "20",
    }
    qs2 = "&".join(f"{k}={params2[k]}" for k in sorted(params2))
    sign2 = cls_sign(params2)
    url2 = f"https://www.cls.cn/v1/roll/get_roll_list?{qs2}&sign={sign2}"
    r2 = get(url2, headers={"Referer": "https://www.cls.cn/telegraph"})
    out["v1_alt"] = {
        "status": r2.status_code,
        "preview": r2.text[:800],
        "json": None,
    }
    try:
        out["v1_alt"]["json"] = r2.json()
    except Exception as e:
        out["v1_alt"]["json_error"] = str(e)

    # legacy
    r3 = get(
        "https://www.cls.cn/nodeapi/telegraphList",
        params={"rn": "20", "page": "1"},
        headers={"Referer": "https://www.cls.cn/"},
    )
    out["legacy"] = {
        "status": r3.status_code,
        "ctype": r3.headers.get("Content-Type"),
        "preview": r3.text[:500],
    }
    return out


def probe_em_news():
    out = {}
    # code keyword
    for keyword in ["600519", "贵州茅台"]:
        inner = {
            "uid": "",
            "keyword": keyword,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": 10,
                    "preTag": "",
                    "postTag": "",
                }
            },
        }
        params = {
            "cb": "jQuery_news",
            "param": json.dumps(inner, ensure_ascii=False, separators=(",", ":")),
            "_": "1",
        }
        r = get(
            "https://search-api-web.eastmoney.com/search/jsonp",
            params=params,
            headers={"Referer": "https://so.eastmoney.com/"},
            eastmoney=True,
        )
        preview = r.text[:1000]
        parsed = None
        keys = None
        try:
            start = preview.index("(") + 1 if "(" in r.text else -1
            if start > 0:
                parsed = json.loads(r.text[r.text.index("(") + 1 : r.text.rindex(")")])
                keys = list((parsed.get("result") or {}).keys())
        except Exception as e:
            keys = [f"parse_error:{e}"]
        out[keyword] = {
            "status": r.status_code,
            "bytes": len(r.content),
            "result_keys": keys,
            "preview": preview,
            "cms_count": len(((parsed or {}).get("result") or {}).get("cmsArticleWebOld") or []) if parsed else None,
        }

    # alternative: eastmoney stock news list page API
    # https://np-listapi.eastmoney.com/comm/web/getNewsByColumns
    r2 = get(
        "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns",
        params={
            "client": "web",
            "biz": "web_news_col",
            "column": "350",
            "order": "1",
            "needInteractData": "0",
            "page_index": "1",
            "page_size": "20",
            "req_trace": "poc",
            "fields": "code,showTime,title,mediaName,summary,url,uniqueUrl,Np_dst",
            "types": "1,20",
        },
        headers={"Referer": "https://finance.eastmoney.com/"},
        eastmoney=True,
    )
    out["np_listapi"] = {
        "status": r2.status_code,
        "preview": r2.text[:600],
    }
    try:
        out["np_listapi"]["json_keys"] = list(r2.json().keys())
    except Exception as e:
        out["np_listapi"]["error"] = str(e)

    # stock-specific news via guba/list? try report detail news
    r3 = get(
        "https://search-api-web.eastmoney.com/search/jsonp",
        params={
            "cb": "jQuery",
            "param": json.dumps(
                {
                    "uid": "",
                    "keyword": "600519",
                    "type": ["cmsArticleWebOld", "noticeWeb", "gubaWeb"],
                    "client": "web",
                    "clientType": "web",
                    "clientVersion": "curr",
                    "param": {
                        "cmsArticleWebOld": {
                            "searchScope": "default",
                            "sort": "default",
                            "pageIndex": 1,
                            "pageSize": 10,
                            "preTag": "",
                            "postTag": "",
                        },
                        "noticeWeb": {
                            "searchScope": "default",
                            "sort": "default",
                            "pageIndex": 1,
                            "pageSize": 5,
                            "preTag": "",
                            "postTag": "",
                        },
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
        headers={"Referer": "https://so.eastmoney.com/"},
        eastmoney=True,
    )
    try:
        parsed = json.loads(r3.text[r3.text.index("(") + 1 : r3.text.rindex(")")])
        out["multi_type"] = {
            "status": r3.status_code,
            "result_keys": list((parsed.get("result") or {}).keys()),
            "counts": {
                k: len(v) if isinstance(v, list) else type(v).__name__
                for k, v in (parsed.get("result") or {}).items()
            },
        }
    except Exception as e:
        out["multi_type"] = {"error": str(e), "preview": r3.text[:400]}
    return out


if __name__ == "__main__":
    payload = {"cls": probe_cls(), "em_news": probe_em_news()}
    path = save_json("_poc_raw_probes.json", payload)
    print("saved", path)
    print("CLS v1 errno", ((payload["cls"]["v1"].get("json") or {}).get("errno")))
    print("CLS v1 data keys", list((((payload["cls"]["v1"].get("json") or {}).get("data") or {}) or {}).keys()))
    print("CLS v1 alt", (payload["cls"]["v1_alt"].get("json") or {}).get("errno"), list((((payload["cls"]["v1_alt"].get("json") or {}).get("data") or {}) or {}).keys()))
    for k, v in payload["em_news"].items():
        if isinstance(v, dict):
            print("EM", k, "keys", v.get("result_keys"), "cms", v.get("cms_count"), "counts", v.get("counts"))
