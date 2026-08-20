"""Run market-source PoC for 600519 and write example JSON + evaluation."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poc_market_sources.cls_poc import run_cls_poc
from poc_market_sources.common import save_json
from poc_market_sources.eastmoney_poc import run_eastmoney_poc
from poc_market_sources.ths_poc import run_ths_poc


def _news_from_eastmoney(em: dict) -> list[dict]:
    rows = []
    news = em.get("news") or {}
    for item in news.get("recent_30_sample") or news.get("recent_90_sample") or news.get("sample") or []:
        rows.append(
            {
                "title": item.get("title"),
                "published_at": item.get("published_at"),
                "source": item.get("source") or "东方财富",
                "url": item.get("url"),
                "content": item.get("content"),
                "category": "company",
            }
        )
    # include a few EM global/market items if available
    global_news = em.get("global_news_em") or {}
    for item in (global_news.get("items") or [])[:8]:
        rows.append(
            {
                "title": item.get("title"),
                "published_at": item.get("published_at"),
                "source": item.get("source") or "东方财富",
                "url": item.get("url"),
                "content": item.get("content"),
                "category": item.get("category") or "market",
            }
        )
    return rows


def _news_from_cls(cls: dict) -> list[dict]:
    summary = cls.get("summary") or {}
    rows = []
    for item in summary.get("related_30_sample") or summary.get("related_90_sample") or []:
        rows.append(
            {
                "title": item.get("title"),
                "published_at": item.get("published_at"),
                "source": "财联社",
                "url": item.get("url"),
                "content": item.get("content"),
                "category": item.get("category") or "company",
            }
        )
    # add a few macro/industry from market sample for Fundamental Agent relevance
    for item in (summary.get("market_30_sample") or [])[:5]:
        if item.get("category") in {"macro", "industry"}:
            rows.append(
                {
                    "title": item.get("title"),
                    "published_at": item.get("published_at"),
                    "source": "财联社",
                    "url": item.get("url"),
                    "content": item.get("content"),
                    "category": item.get("category"),
                }
            )
    return rows


def _announcements(em: dict) -> list[dict]:
    ann = em.get("announcements") or {}
    rows = []
    for item in ann.get("sample") or []:
        rows.append(
            {
                "title": item.get("title"),
                "published_at": item.get("published_at"),
                "source": item.get("source"),
                "url": item.get("url"),
                "content": item.get("content") or "",
                "category": "company",
            }
        )
    return rows


def _events(em: dict) -> list[dict]:
    events = []
    lhb = em.get("dragon_tiger_90d") or {}
    if lhb.get("ok") and lhb.get("count"):
        events.append(
            {
                "type": "dragon_tiger",
                "count": lhb.get("count"),
                "sample": lhb.get("sample"),
                "source": "东方财富",
            }
        )
    lockup = em.get("lockup") or {}
    if lockup.get("ok") and lockup.get("count"):
        events.append(
            {
                "type": "lockup",
                "count": lockup.get("count"),
                "sample": lockup.get("sample"),
                "source": "东方财富",
            }
        )
    holder = em.get("holder_change") or {}
    if holder.get("ok") and holder.get("count"):
        events.append(
            {
                "type": "holder_change",
                "count": holder.get("count"),
                "sample": holder.get("sample"),
                "source": "东方财富",
            }
        )
    flow = em.get("fund_flow_hist") or {}
    if flow.get("ok") and flow.get("count"):
        events.append(
            {
                "type": "fund_flow",
                "count": flow.get("count"),
                "sample": flow.get("sample"),
                "source": "东方财富",
            }
        )
    return events


def build_evaluation(em: dict, cls: dict, ths: dict) -> str:
    em_news_ok = (em.get("news") or {}).get("total_returned", 0) > 0
    em_ann_ok = ((em.get("announcements") or {}).get("total_returned") or 0) > 0
    cls_ok = ((cls.get("summary") or {}).get("roll_total") or 0) > 0
    cls_related = ((cls.get("summary") or {}).get("stock_related_30d") or 0) + (
        (cls.get("summary") or {}).get("stock_related_90d") or 0
    )
    ths_ok = bool((ths.get("summary") or {}).get("got_current_consensus"))

    lines = [
        "# 数据源可行性评估（PoC）",
        "",
        f"- 测试标的：`600519` 贵州茅台",
        f"- 生成时间：`{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}`",
        "- 原则：全部为真实 HTTP 请求结果，无 LLM 模拟数据。",
        "",
        "## 总表",
        "",
        "| 数据源 | 数据类型 | 可获取性 | 完整度 | 稳定性 | Bull/Bear价值 | 建议 |",
        "|---|---|---|---|---|---|---|",
        "| AKShare | 财务/行情 | ★★★★★ | ★★★★★ | ★★★★☆ | ★★★☆☆（偏事实底座，非观点） | **保留为 Evidence 底座** |",
        f"| 东方财富 | 新闻/公告/事件 | {'★★★★☆' if em_news_ok or em_ann_ok else '★★☆☆☆'} | {'★★★★☆' if em_ann_ok else '★★★☆☆'} | ★★★☆☆（push2/search 偶发风控） | ★★★★☆ | **保留：公告+事件优先，新闻作补充** |",
        f"| 财联社 | 新闻/快讯 | {'★★★★☆' if cls_ok else '★★☆☆☆'} | ★★★☆☆（全市场滚动，个股召回不稳定） | ★★★★☆ | ★★★★☆（时效观点强） | **保留：宏观/行业/突发；个股需关键词过滤** |",
        f"| 同花顺 | 一致预期 | {'★★★★☆' if ths_ok else '★★☆☆☆'} | {'★★★☆☆' if ths_ok else '★★☆☆☆'}（截面有，历史弱） | ★★★★☆ | ★★★★★（市场预期锚） | **保留：当前一致预期进 Evidence；历史序列另寻** |",
        "",
        "## 1. 东方财富实测",
        "",
        f"- 个股新闻条数：`{(em.get('news') or {}).get('total_returned')}`；30天：`{(em.get('news') or {}).get('recent_30_count')}`；90天：`{(em.get('news') or {}).get('recent_90_count')}`",
        f"- 公告条数：`{(em.get('announcements') or {}).get('total_returned')}`；30天：`{(em.get('announcements') or {}).get('recent_30_count')}`",
        f"- 龙虎榜(90d)：`{(em.get('dragon_tiger_90d') or {}).get('count')}` / ok=`{(em.get('dragon_tiger_90d') or {}).get('ok')}`",
        f"- 解禁：`{(em.get('lockup') or {}).get('count')}` / ok=`{(em.get('lockup') or {}).get('ok')}`",
        f"- 股东增减持：`{(em.get('holder_change') or {}).get('count')}` / ok=`{(em.get('holder_change') or {}).get('ok')}`",
        f"- 资金流向：`{(em.get('fund_flow_hist') or {}).get('count')}` / ok=`{(em.get('fund_flow_hist') or {}).get('ok')}`",
        f"- notes: {em.get('quality_notes')}",
        "",
        "### 评价维度",
        "",
        "| 维度 | 结论 |",
        "|---|---|",
        f"| 可获取性 | 新闻/公告/事件接口多数可打通；资金流依赖 push2his，本机可能失败 |",
        f"| 稳定性 | datacenter / notice 较稳；search-api / push2 有风控 |",
        f"| 完整度 | 公告元数据好；新闻多为摘要；正文不全 |",
        f"| 时间准确性 | 公告时间较准；新闻搜索偏相关度，不完全等于时间窗 |",
        f"| 是否有原文 | 多数无完整原文，仅摘要/标题+链接 |",
        f"| 是否适合 Agent | 适合作为事件与公告证据 |",
        f"| Bull/Bear | 适合争论“供给/减持/龙虎榜/公告落地” |",
        f"| 中短期研究 | 公告+资金/龙虎榜更有用；泛新闻噪音大 |",
        "",
        "## 2. 财联社实测",
        "",
        f"- primary_api: `{cls.get('primary_api')}`",
        f"- 滚动快讯总数: `{(cls.get('summary') or {}).get('roll_total')}`",
        f"- 茅台相关 30d/90d: `{(cls.get('summary') or {}).get('stock_related_30d')}` / `{(cls.get('summary') or {}).get('stock_related_90d')}`",
        f"- 是否原生按股票代码筛选: `{(cls.get('summary') or {}).get('can_filter_by_code_native')}`",
        f"- notes: {cls.get('quality_notes')}",
        "",
        "### 评价维度",
        "",
        "| 维度 | 结论 |",
        "|---|---|",
        "| 可获取性 | v1 签名接口或旧接口至少应验证；个股相关靠客户端关键词 |",
        "| 稳定性 | 相对东财 push2 更稳，但搜索接口易变 |",
        "| 完整度 | 快讯正文短，适合情绪/事件触发，不适合深度事实 |",
        "| 时间准确性 | ctime 时间戳通常准确 |",
        "| 是否有原文 | 快讯即正文（短） |",
        "| 是否适合 Agent | 适合 News/Macro 输入 |",
        "| Bull/Bear | 高价值，尤其突发与政策解读 |",
        "| 中短期研究 | 强；但必须做标的相关性过滤，否则噪音极大 |",
        "",
        "## 3. 同花顺实测",
        "",
        f"- 拿到一致预期: `{(ths.get('summary') or {}).get('got_current_consensus')}`",
        f"- 年份: `{(ths.get('summary') or {}).get('forecast_years')}`",
        f"- 机构数字段: `{(ths.get('summary') or {}).get('has_institution_count')}`",
        f"- 更新时间: `{(ths.get('summary') or {}).get('has_updated_at')}`",
        f"- 历史序列: `{(ths.get('summary') or {}).get('has_historical_timeseries_api')}`",
        f"- notes: {ths.get('quality_notes')}",
        "",
        "### 评价维度",
        "",
        "| 维度 | 结论 |",
        "|---|---|",
        "| 可获取性 | worth.html 可解析当前 EPS 一致预期（需 UA） |",
        "| 稳定性 | 较好；偶发反爬 |",
        "| 完整度 | 当前截面可用；净利润/评级/目标价不一定结构化；历史变化弱 |",
        "| 时间准确性 | 有页面更新时间则可用，否则只能记 retrieved_at |",
        "| 是否有原文 | 表格数值，非文本观点 |",
        "| 是否适合 Agent | 非常适合作为“市场预期锚” |",
        "| Bull/Bear | 高价值（预期差/上修下修） |",
        "| 中短期研究 | 截面足够做估值锚；若要做预期修订轨迹需另找源 |",
        "",
        "## 4. 哪些可直接进 Evidence Layer",
        "",
        "1. **可直接进入**：东财公司公告元数据；同花顺一致预期截面；东财解禁/龙虎榜/增减持（若返回非空）；AKShare 财务/行情。",
        "2. **可进入但需清洗**：东财个股新闻摘要；财联社快讯（必须相关性过滤）。",
        "3. **质量不足/暂缓**：依赖 push2 的分钟/日资金流（网络不稳时）；财联社“原生按代码筛选”；同花顺一致预期历史时间序列。",
        "",
        "## 5. 下一步建议保留的数据源",
        "",
        "1. **保留 AKShare**：基本面与行情硬证据。",
        "2. **保留东方财富**：公告 + 解禁/龙虎榜/股东事件；新闻作辅助。",
        "3. **保留财联社**：宏观/行业/突发快讯（加关键词与标的过滤）。",
        "4. **保留同花顺**：当前一致预期 EPS（及机构数）。",
        "5. **暂不自建复杂清洗**；先把上述字段写入统一 Evidence schema。",
        "",
    ]
    # Append dynamic related counts for transparency
    lines.append(f"- 财联社相关命中合计(30+90窗口统计字段): `{cls_related}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    print("Running Eastmoney PoC...")
    em = run_eastmoney_poc("600519")
    save_json("600519_eastmoney_test.json", em)
    print("Saved 600519_eastmoney_test.json")

    print("Running CLS PoC...")
    cls = run_cls_poc("600519")
    save_json("600519_cls_test.json", cls)
    print("Saved 600519_cls_test.json")

    print("Running THS PoC...")
    ths = run_ths_poc("600519")
    save_json("600519_ths_test.json", ths)
    print("Saved 600519_ths_test.json")

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
    print("Saved 600519_market_information.json")

    report = {
        "retrieved_at": market_info["retrieved_at"],
        "stock_code": "600519",
        "eastmoney": {
            "attempts": em.get("attempts"),
            "news_total": (em.get("news") or {}).get("total_returned"),
            "news_30": (em.get("news") or {}).get("recent_30_count"),
            "announcements_total": (em.get("announcements") or {}).get("total_returned"),
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
            "quality_notes": ths.get("quality_notes"),
        },
    }
    save_json("data_source_test_report.json", report)
    print("Saved data_source_test_report.json")

    eval_md = build_evaluation(em, cls, ths)
    eval_path = ROOT / "DATA_SOURCE_EVALUATION.md"
    eval_path.write_text(eval_md, encoding="utf-8")
    print(f"Saved {eval_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
