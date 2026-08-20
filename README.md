# 个股 Deep Research

面向 A 股**单只股票**的 AI 深度研究工作台（Stock Deep Research）。

定位很明确：我们做的是**个股 Deep Research**——不是行业周报，也不是自动买卖建议，而是针对一只股票，把分散的财务、公告、新闻与辩论过程，组织成：

> **哪些变化值得关注 → 为什么可能相关 → 下一步该研究什么**

最终条件判断仍由 Final Analyst 给出；Insight Layer 负责帮用户发现研究方向，而不是替用户下投资结论。

---

## 一、项目能做什么

1. **拉取并结构化 A 股证据**（财务、估值、行情、公告、宏观/市场新闻等）
2. **Research Agent** 在证据约束下形成基本面 / 市场命题
3. **Debate**（多空立论 → 质询 → 回应）暴露解释冲突
4. **Final Analyst** 在 fail-closed / grounding 规则下给出条件判断
5. **前端 Demo** 以 Replay 方式回放完整研究链路，并展示 **研究洞察层（Insight Layer）**

当前 Demo 可回放标的示例：

| 代码 | 名称 | 说明 |
| --- | --- | --- |
| `600519` | 贵州茅台 | 完整 grounded artifacts |
| `601127` | 赛力斯 | 完整 grounded artifacts |

---

## 二、产品理念

### 不是什么

- 不是传统研报网页（KPI 表 + 模板段落）
- 不是自动评级 / 目标价 / 买卖建议系统
- 不是「把所有新闻标成利好/利空」的情绪工具

### 是什么

用户进入一只股票后，第一屏应回答：

1. 最近发生了什么？
2. AI 认为最值得关注的 3–5 个变化是什么？
3. 为什么这些变化重要？
4. 哪些来自公司自身，哪些来自外部环境？
5. 哪些地方存在值得继续研究的问题？

研究逻辑从：

`Event → Evidence → Conclusion`

升级为：

```text
Event / Financial Change
        ↓
      Insight
        ↓
Possible Company Link
        ↓
Impact Channel
        ↓
Research Question
```

---

## 三、系统架构（简图）

```text
Data Service (AKShare 等)
        ↓
Evidence Pack Builder
        ↓
Fundamental / Market Research
        ↓
Bull / Bear → Challenge → Rebuttal
        ↓
Final Analyst (+ Production Gate)
        ↓
Web Assemble / Insight Layer / Presentation
        ↓
Browser Workspace (Brief / Judgment / Evidence / Debate)
```

### 核心目录

```text
src/
  data_service/     # 原始数据 + 衍生指标
  evidence/         # Evidence Pack 构建与 schema
  research/         # 基本面 / 市场研究 Agent
  debate/           # 多空辩论引擎
  final_analyst/    # 最终判断、校准、门禁
  pipeline/         # 端到端编排
web/
  server.py         # Demo HTTP 服务
  assemble.py       # 产物组装为前端 snapshot
  insight_layer.py  # 洞察排序层（展示层，不改 FA 判断）
  report_format.py  # 报告呈现
  static/           # 前端（index.html / app.js / styles.css）
examples/           # 冻结 artifacts（可 Replay）
tests/              # 单元 / Demo 测试
scripts/            # 建包、预扫、稳定性脚本
schema/             # JSON Schema
```

---

## 四、前端 Workspace（已包含）

前端代码已在仓库中：`web/static/`。

启动后默认打开：**http://127.0.0.1:8765**

### Brief 页主要区块

| 区块 | 作用 |
| --- | --- |
| **当前最值得研究的变化** | 一句话 Insight + 为什么 / 意味着什么 / 下一步 |
| **Research Signals** | Top 3–5 洞察卡片（财务关系或外部信号） |
| **Fundamental Picture** | 增长 / 盈利 / 现金流等「关系」摘要 |
| **External Signals** | 宏观、行业、政策、新闻（区分邻接 / 背景 / 噪音） |
| **Where They Might Connect** | 外部变化 → 可能渠道 → 暴露度 → 研究问题 |
| **Evidence / Debate / Final Judgment** | 可追溯底层与最终条件判断 |

### 启动方式

```powershell
cd ashare-deep-research   # 本地目录名可保持不变
pip install -r requirements-web.txt
$env:PYTHONPATH = "src;web"
python web\server.py
```

浏览器打开后：

1. 选择 `600519` 或 `601127`
2. 点击「开始深度研究」（Replay，不调用新 LLM）
3. 进入 **Research Brief** 查看洞察层

> 若页面结构新了但内容为空，请 **重启 `server.py` 并硬刷新**（`Ctrl+Shift+R`）。

### Demo 自检（无 API）

```powershell
$env:PYTHONPATH = "src;web"
python -m tests.test_demo_web
```

---

## 五、Insight Layer（研究洞察层）

实现位置：`web/insight_layer.py`（**仅展示层**）。

### 财务洞察

不默认输出「盈利能力仍强，增长动能承压」这类模板句。  
从指标**关系**中动态寻找主轴，例如：

- 利润降幅 > 收入降幅 → 研究利润弹性
- 营收扩张快、利润几乎不动 → 研究增长是否转化为利润
- 利润为正但现金流偏弱 → 研究利润质量

### 外部信号

不做简单利好/利空标签，而是输出：

- 事件是什么
- Agent Insight（反映什么环境变化）
- 与公司的可能关联（可弱可强）
- 影响渠道（收入、成本、估值叙事、供应链等）
- 下一步研究问题

弱关联会明确标为「产业链邻接 / 行业背景 / 主题噪音」，避免强行因果。

### 明确不改动的边界

Insight Layer **不会**修改：

- Evidence schema / Pack Builder
- Research / Debate 合约
- Final Analyst / Production Gate / JudgmentFrame
- grounding / citation / ALLOWED_NUMBERS 等安全规则

---

## 六、后端能力概览

### 1. Data Service

- 公司信息、主营构成、三大报表、行情、估值等
- 衍生指标：ROE、毛利率、同比、均线等
- 依赖：`requirements.txt` + AKShare

```powershell
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m tests.run_module_tests bundle --symbol 600519 --save
```

### 2. Evidence → Research → Debate → Final Analyst

完整链路产物保存在 `examples/`（如 `600519_evidence_pack.json`、`601127_final_analyst.json`）。

Demo 默认 **Replay grounded artifacts**，不发起新的模型调用。  
若要跑 live LLM，需自行配置环境变量（见 `.env` 示例；**仓库不上传真实密钥**）。

### 3. 一键为新标的建 Demo 包

```powershell
$env:PYTHONPATH = "src;web"
python scripts\build_demo_symbol.py --symbol 601127
```

---

## 七、依赖文件

| 文件 | 用途 |
| --- | --- |
| `requirements.txt` | 数据服务 / 主链路 |
| `requirements-evidence.txt` | Evidence 相关 |
| `requirements-web.txt` | Demo Web（FastAPI 等） |

---

## 八、重要说明

1. **本项目输出为研究备忘录 / 条件判断，不构成投资建议。**
2. 不对「合理市值」「买入/卖出评级」作结论。
3. 所有事实性数字应可回溯到 Evidence；缺证据时允许提出研究问题，但不编造事实。
4. `.env` 已在 `.gitignore` 中，请勿把 API Key 提交进仓库。

---

## 九、相关文档

仓库内还有多份审计与设计笔记（英文文件名），例如：

- `EVIDENCE_SCHEMA.md`
- `RESEARCH_PIPELINE_AUDIT.md`
- `FINAL_ANALYST_PRODUCTION_READINESS.md`
- `DATA_SOURCE_EVALUATION.md`
- `web/README.md`（Demo 启动速查）

---

## 十、快速体验清单

```powershell
# 1. 安装 Web 依赖并启动
pip install -r requirements-web.txt
$env:PYTHONPATH = "src;web"
python web\server.py

# 2. 浏览器打开
# http://127.0.0.1:8765

# 3. 打开赛力斯或茅台 → 看 Research Brief 洞察层
```

项目名：**个股 Deep Research**。从 Brief 页的 **Research Signals** 开始体验即可。
