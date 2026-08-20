# Evidence Layer 说明

## 1. 为什么需要 Evidence Layer

下游 Fundamental / Market / Bull / Bear Agent 不应直接消费各数据源的原始异构 JSON。  
Evidence Layer 把已验证数据统一成：

- 可引用
- 可追溯
- 无投资观点
- 可按类型/来源/时间查询

的事实材料包（Evidence Pack）。

## 2. Evidence 类型（仅四种）

| 类型 | 含义 | 典型来源 |
|---|---|---|
| FACT | 原始结构化事实 | AKShare |
| DERIVED | Python 计算指标 | derived fundamentals / technicals |
| EVENT | 近期事件 | 东财公告、股东增减持、财联社快讯 |
| EXPECTATION | 市场预期 | 同花顺一致预期 |

## 3. Schema（核心字段）

```text
Evidence
- evidence_id
- stock_code
- evidence_type: FACT | DERIVED | EVENT | EXPECTATION
- subtype
- claim                 # 程序模板生成，禁止 LLM
- value                 # 结构化原值
- source                # provider/source_type/url/retrieved_at/published_at/updated_at
- time                  # data_date/report_date/published_at/retrieved_at
- freshness             # age_hours + status
- reliability           # high | medium_high | medium | low
- metadata
```

禁止字段：`bull_score` / `bear_score` / `stance` / `investment_rating` 等观点字段。

## 4. Source

- AKShare：财务、公司信息、行情快照
- 东方财富：公告、股东增减持
- 财联社：宏观/市场快讯
- 同花顺：EPS 一致预期

新浪新闻暂不进入核心 Evidence Layer。

## 5. Freshness

| status | 规则 |
|---|---|
| very_recent | 0–24h |
| recent | 1–7d |
| historical_recent | 7–30d |
| stale | >30d |
| periodic | 财报/一致预期等周期数据，不按 report_date 机械过期 |

## 6. Reliability（默认）

| 来源 | reliability |
|---|---|
| AKShare 原始财务/行情 | high |
| Python derived | high |
| 东财正式公告/股东事件 | high |
| 财联社快讯 | medium_high |
| 同花顺一致预期 | medium_high |

## 7. Evidence 与 Agent Reasoning 的边界

Evidence 只陈述事实，例如：

- “2025 年归母净利润为 823.20 亿元”
- “2026 年 EPS 一致预期为 68.70 元，共 46 家机构”

不陈述：

- “基本面恶化”
- “股价偏高”
- “市场看好”

观点只能由后续 Agent 产生。

## 8. EvidencePack 查询

```python
pack.get_by_type("EVENT")
pack.get_by_subtype("eps_consensus")
pack.get_by_source("eastmoney")
pack.get_recent(hours=24*7)
pack.get_by_date_range("2026-07-15", "2026-08-14")
pack.get_company_events()
pack.get_expectations()
pack.get_fundamental_facts()
pack.get_market_facts()
```

## 9. 完整示例（摘要）

```json
{
  "stock_code": "600519",
  "generated_at": "2026-08-14T...",
  "evidence": [
    {
      "evidence_id": "akshare_fact_600519_20251231_xxxx",
      "evidence_type": "FACT",
      "subtype": "net_profit_parent",
      "claim": "2025-12-31 归母净利润为 823.20 亿元",
      "value": {"metric": "net_profit_parent", "value": 82320067101.68, "unit": "CNY", "period": "2025-12-31"},
      "source": {"provider": "akshare.stock_profit_sheet_by_report_em", "source_type": "income_statement"},
      "reliability": "high"
    },
    {
      "evidence_type": "EXPECTATION",
      "subtype": "eps_consensus",
      "claim": "2026 年 EPS 一致预期为 68.70 元，共 46 家机构（更新于 2026-08-14）",
      "source": {"provider": "tonghuashun", "url": "https://basic.10jqka.com.cn/new/600519/worth.html"}
    }
  ]
}
```

## 10. 生成命令

```bat
cd /d C:\Users\86137\ashare-deep-research
pip install -r requirements.txt
python -m evidence.build --symbol 600519
python -m tests.test_evidence --symbol 600519
```

输出：`examples/600519_evidence_pack.json`
