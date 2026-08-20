from poc_market_sources.cls_poc import fetch_cls_v1_roll, run_cls_poc
import json

print("direct fetch...")
data = fetch_cls_v1_roll(page_size=50, max_pages=3)
print("count", data.get("count"), "pages", data.get("pages_fetched"))
print("meta", json.dumps(data.get("meta"), ensure_ascii=False)[:500])
if data.get("items"):
    print("first", data["items"][0]["title"], data["items"][0]["published_at"])
    related = [i for i in data["items"] if i.get("stock_related")]
    print("related", len(related), [i["title"] for i in related[:5]])
else:
    print("EMPTY", data)
