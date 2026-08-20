from poc_market_sources.cls_poc import run_cls_poc
from poc_market_sources.common import save_json
import json
from datetime import datetime, timezone
from pathlib import Path
from poc_market_sources.run_poc import (
    _announcements,
    _events,
    _news_from_cls,
    _news_from_eastmoney,
    build_evaluation,
)

cls = run_cls_poc("600519")
print("primary", cls.get("primary_api"))
print("attempts", cls.get("attempts"))
print("v1 count", (cls.get("v1_roll") or {}).get("count"), "pages", (cls.get("v1_roll") or {}).get("pages_fetched"))
print("summary", {k: (cls.get("summary") or {}).get(k) for k in [
    "roll_total", "stock_related_total", "stock_related_30d", "stock_related_90d", "all_30d", "has_content", "has_url"
]})
print("notes", cls.get("quality_notes"))
rel = ((cls.get("summary") or {}).get("related_30_sample") or (cls.get("summary") or {}).get("related_90_sample") or [])
print("related sample titles", [x.get("title") for x in rel[:5]])
print("market sample titles", [x.get("title") for x in ((cls.get("summary") or {}).get("market_30_sample") or [])[:5]])
if cls.get("attempts", {}).get("v1_roll", {}).get("error"):
    print("v1 error", cls["attempts"]["v1_roll"]["error"])

save_json("600519_cls_test.json", cls)

em = json.loads(Path("examples/600519_eastmoney_test.json").read_text(encoding="utf-8"))
ths = json.loads(Path("examples/600519_ths_test.json").read_text(encoding="utf-8"))
market_info = {
    "stock_code": "600519",
    "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "news": _news_from_eastmoney(em) + _news_from_cls(cls),
    "announcements": _announcements(em),
    "consensus": ths.get("consensus_normalized") or [],
    "events": _events(em),
    "source_status": {
        "eastmoney": em.get("attempts"),
        "cls": cls.get("attempts"),
        "ths": ths.get("attempts"),
    },
}
save_json("600519_market_information.json", market_info)
report = {
    "retrieved_at": market_info["retrieved_at"],
    "stock_code": "600519",
    "eastmoney": {
        "attempts": em.get("attempts"),
        "news_total": (em.get("news") or {}).get("total_returned"),
        "news_30": (em.get("news") or {}).get("recent_30_count"),
        "news_source_used": (em.get("news") or {}).get("source_used"),
        "announcements_total": (em.get("announcements") or {}).get("total_returned"),
        "announcements_30": (em.get("announcements") or {}).get("recent_30_count"),
        "announcements_90": (em.get("announcements") or {}).get("recent_90_count"),
        "global_news_count": (em.get("global_news_em") or {}).get("count"),
        "dragon_tiger": (em.get("dragon_tiger_90d") or {}).get("count"),
        "lockup": (em.get("lockup") or {}).get("count"),
        "holder_change": (em.get("holder_change") or {}).get("count"),
        "fund_flow_ok": (em.get("fund_flow_hist") or {}).get("ok"),
        "quality_notes": em.get("quality_notes"),
    },
    "cls": {
        "attempts": cls.get("attempts"),
        "primary_api": cls.get("primary_api"),
        "summary": cls.get("summary"),
        "quality_notes": cls.get("quality_notes"),
    },
    "ths": {
        "attempts": ths.get("attempts"),
        "summary": ths.get("summary"),
        "consensus": ths.get("consensus_normalized"),
        "quality_notes": ths.get("quality_notes"),
    },
}
save_json("data_source_test_report.json", report)
Path("DATA_SOURCE_EVALUATION.md").write_text(build_evaluation(em, cls, ths), encoding="utf-8")
print("market news", len(market_info["news"]), "ann", len(market_info["announcements"]), "consensus", len(market_info["consensus"]), "events", len(market_info["events"]))
