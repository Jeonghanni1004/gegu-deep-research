import json
from pathlib import Path

b = json.loads(Path("examples/600519_bundle.json").read_text(encoding="utf-8"))
m = json.loads(Path("examples/600519_market_information.json").read_text(encoding="utf-8"))
em = json.loads(Path("examples/600519_eastmoney_test.json").read_text(encoding="utf-8"))
ths = json.loads(Path("examples/600519_ths_test.json").read_text(encoding="utf-8"))
cls = json.loads(Path("examples/600519_cls_test.json").read_text(encoding="utf-8"))

print("bundle keys", list(b.keys()))
print("raw", list(b["layers"]["raw"].keys()))
print("derived", list(b["layers"]["derived"].keys()))
ci = b["layers"]["raw"]["company_info"]
print("company fields", {k: ci.get(k) for k in ["stock_code","stock_name","industry","listing_date","total_shares","total_market_cap"]})
inc = b["layers"]["raw"]["financials"]["income_statement"]["items"]
bal = b["layers"]["raw"]["financials"]["balance_sheet"]["items"]
cash = b["layers"]["raw"]["financials"]["cash_flow"]["items"]
print("income periods", len(inc), "latest report", inc[0].get("report_date") if inc else None)
print("income0 keys", list(inc[0].keys()) if inc else None)
print("balance0 keys", list(bal[0].keys()) if bal else None)
print("cash0 keys", list(cash[0].keys()) if cash else None)
print("hist bars", len(b["layers"]["raw"]["market_history"]["items"]))
print("snapshot", {k: b["layers"]["raw"]["market_snapshot"].get(k) for k in ["latest_price","pe","pb","ps","total_market_cap","turnover_rate","data_date"]})
print("fund", b["layers"]["derived"]["fundamentals"].get("latest"))
print("tech", b["layers"]["derived"]["technicals"].get("latest"))
print("market info counts", {k: (len(v) if isinstance(v, list) else type(v).__name__) for k, v in m.items()})
print("news0", (m.get("news") or [None])[0])
print("ann0", (m.get("announcements") or [None])[0])
print("cons", m.get("consensus"))
print("events types", [e.get("type") for e in (m.get("events") or [])])
holder = em.get("holder_change") or {}
print("holder count", holder.get("count"), "sample0 keys", list(((holder.get("sample") or [{}])[0] or {}).keys())[:20])
print("holder0", (holder.get("sample") or [None])[0])
print("cls related", (cls.get("summary") or {}).get("stock_related_30d"), "roll", (cls.get("summary") or {}).get("roll_total"))
print("cls market0", ((cls.get("summary") or {}).get("market_30_sample") or [None])[0])
print("ths consensus", ths.get("consensus_normalized"))
