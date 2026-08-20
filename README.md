# A-Share Deep Research — Data Service (MVP Stage 1)

Python + AKShare 数据获取层。本阶段只做稳定的结构化数据拉取与本地衍生指标计算，不包含 Multi-Agent / 前端。

## 分层

| Layer | 职责 |
| --- | --- |
| `layers.raw` | AKShare / 同源接口原始字段，统一为英文 snake_case |
| `layers.derived` | 纯 Python 计算（同比、ROE、MA/MACD/RSI 等） |
| `layers.ai_analysis` | 预留，本阶段为空 |

## 快速开始

```bash
pip install -r requirements.txt
# 单模块验证
python -m tests.run_module_tests company --symbol 600519
python -m tests.run_module_tests history --symbol 600519
# 全部模块
python -m tests.run_module_tests all --symbol 600519
# 拉取完整 JSON bundle
python -m tests.run_module_tests bundle --symbol 600519 --save
```

输出示例：`examples/600519_bundle.json`  
Schema：`schema/stock_research_bundle.schema.json`

## 数据源映射（真实 AKShare API）

| 模块 | 主接口 | 回退 |
| --- | --- | --- |
| 公司基础信息 | `stock_individual_info_em` | Eastmoney F10 CompanySurvey + `stock_value_em` |
| 主营构成 | `stock_zygc_em` | TODO → CNINFO |
| 三大报表 | `stock_*_sheet_by_report_em` | TODO → Sina/Tushare |
| 历史行情 | `stock_zh_a_hist` | `stock_zh_a_daily`（新浪） |
| 估值快照 | `stock_value_em` | 换手率尝试 `stock_zh_a_spot_em` |

说明：`push2*.eastmoney.com` 在部分网络下不稳定；代码已内置无代理 + 重试，并在失败时回退到可用源。无法稳定获取的字段会写入 `todos`，不会伪造。

## 目录

```
src/data_service/
  raw/          # 原始数据模块
  derived/      # 衍生指标
  service.py    # 聚合入口
schema/         # JSON Schema + 示例
tests/          # 独立 test 函数入口
```
