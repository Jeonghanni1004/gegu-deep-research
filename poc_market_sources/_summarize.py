import json
from pathlib import Path

p = Path("examples")
em = json.loads((p / "600519_eastmoney_test.json").read_text(encoding="utf-8"))
cls = json.loads((p / "600519_cls_test.json").read_text(encoding="utf-8"))
ths = json.loads((p / "600519_ths_test.json").read_text(encoding="utf-8"))
mi = json.loads((p / "600519_market_information.json").read_text(encoding="utf-8"))

print("=== EM ===")
print("attempts", {k: v.get("ok") for k, v in em["attempts"].items()})
n = em["news"]
print(
    "news total/30/90/dup/avg_len",
    n["total_returned"],
    n["recent_30_count"],
    n["recent_90_count"],
    n["duplicate_titles"],
    n["avg_content_len"],
)
a = em.get("announcements") or {}
print("ann total/30/90", a.get("total_returned"), a.get("recent_30_count"), a.get("recent_90_count"))
for k in ["dragon_tiger_90d", "lockup", "holder_change", "fund_flow_hist"]:
    d = em.get(k) or {}
    print(k, "ok=", d.get("ok"), "count=", d.get("count"), "error=", d.get("error"))
print("notes", em.get("quality_notes"))
sample = (n.get("recent_30_sample") or n.get("sample") or [None])[0]
print("news0", sample)
print("ann0", (a.get("sample") or [None])[0])

print("=== CLS ===")
print("primary", cls.get("primary_api"))
print("attempts", {k: v.get("ok") for k, v in cls["attempts"].items()})
s = cls.get("summary") or {}
print(
    {
        k: s.get(k)
        for k in [
            "roll_total",
            "stock_related_total",
            "stock_related_30d",
            "stock_related_90d",
            "has_url",
            "has_content",
            "has_published_at",
        ]
    }
)
print("v1", (cls.get("v1_roll") or {}).get("errno"), (cls.get("v1_roll") or {}).get("count"))
print("legacy parse", (cls.get("legacy_telegraph") or {}).get("parse_ok"), (cls.get("legacy_telegraph") or {}).get("error"))
print("search_name", (cls.get("search_name") or {}).get("count"), (cls.get("search_name") or {}).get("error"))
rel = s.get("related_30_sample") or s.get("related_90_sample") or []
print("related0", rel[0] if rel else None)
print("notes", cls.get("quality_notes"))

print("=== THS ===")
print("attempts", {k: v.get("ok") for k, v in ths["attempts"].items()})
print("summary", ths.get("summary"))
print("consensus", ths.get("consensus_normalized"))
print("notes", ths.get("quality_notes"))
wh = ths.get("worth_html") or {}
print("table_count", wh.get("table_count"), "blocked", wh.get("blocked_guess"), "title", wh.get("html_title"))
print("rating hits", wh.get("rating_or_target_text_hits"))

print("=== MARKET INFO ===")
print("news", len(mi["news"]), "ann", len(mi["announcements"]), "consensus", len(mi["consensus"]), "events", len(mi["events"]))
print("event types", [e.get("type") for e in mi["events"]])
