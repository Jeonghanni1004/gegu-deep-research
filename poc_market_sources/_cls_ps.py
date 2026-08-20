from poc_market_sources.cls_poc import fetch_cls_v1_roll

for ps in [20, 50, 100]:
    data = fetch_cls_v1_roll(page_size=ps, max_pages=1)
    print("page_size", ps, "count", data.get("count"), "pages", data.get("pages_fetched"), "bytes", ((data.get("meta") or {}).get("pages") or [{}])[0].get("bytes"))
