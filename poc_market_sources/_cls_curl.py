import hashlib
import json
from datetime import datetime

from curl_cffi import requests as creq


def sign(params):
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.md5(hashlib.sha1(qs.encode()).hexdigest().encode()).hexdigest()


params = {
    "appName": "CailianpressWeb",
    "os": "web",
    "sv": "7.7.5",
    "last_time": "",
    "refresh_type": "1",
    "rn": "30",
}
qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
url = f"https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign(params)}"
print("url", url)
for i in range(3):
    r = creq.get(url, impersonate="chrome124", headers={"Referer": "https://www.cls.cn/telegraph"}, timeout=20)
    print("attempt", i + 1, "status", r.status_code, "bytes", len(r.content))
    try:
        d = r.json()
        rows = ((d.get("data") or {}).get("roll_data")) or []
        print("errno", d.get("errno"), "rows", len(rows))
        if rows:
            print("first title", rows[0].get("title"))
            print("ctime", rows[0].get("ctime"), datetime.fromtimestamp(rows[0].get("ctime")))
            # keyword filter moutai
            hits = []
            for row in rows:
                blob = f"{row.get('title','')}{row.get('content','')}{row.get('brief','')}"
                if any(k in blob for k in ["茅台", "600519", "白酒"]):
                    hits.append(row.get("title"))
            print("keyword hits in page", hits[:5], "count", len(hits))
            break
    except Exception as e:
        print("err", e, r.text[:200])
