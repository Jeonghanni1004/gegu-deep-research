# Research Pipeline Audit

**标的**：600519（贵州茅台）  
**审计类型**：End-to-End Research Pipeline 收口测试（只读，不改代码）  
**审计日期**：2026-08-14  
**范围**：Data Source → Evidence → Fundamental/Market → Bull/Bear → Challenge → Rebuttal  
**未覆盖**：Final Analyst（尚未实现）

> 原则：优先发现问题，不美化结果。  
> 说明：按要求运行了现有测试；`test_research_agents` / `test_debate` 会按既有逻辑重写 `examples/` 产物。本审计**未手工改写** `src/`、`tests/`、`examples/`。

---

## 1. Test Status

| Suite | Command | Total | PASS | FAIL | WARNING |
|------|---------|------:|-----:|-----:|--------:|
| Evidence | `python -m tests.test_evidence --symbol 600519` | 13 | 13 | 0 | 0 |
| Research Agents | `python -m tests.test_research_agents --symbol 600519` | 24 | 24 | 0 | 0 |
| Debate | `python -m tests.test_debate --symbol 600519` | 25 | 25 | 0 | 0 |
| **合计** | | **62** | **62** | **0** | **0** |

**结论**：契约测试与 schema / 可追溯性测试全部通过。  
**警告（非测试失败）**：测试通过 ≠ 研究质量合格；当前测试主要验证“有没有 `evidence_id` / schema / 并行 / 不联网”，**几乎不验证分析深度、对抗质量、时效过滤、权重使用**。

---

## 2. Pipeline Overview

```
Evidence Pack (112)
  FACT 62 / DERIVED 18 / EVENT 29 / EXPECTATION 3
        ↓
EvidenceRetriever（结构化过滤）
        ↓
Fundamental Agent  ‖  Market Agent     ← asyncio.gather
        ↓
Bull Agent         ‖  Bear Agent       ← 共享同一 shared_context
        ↓
Challenges（各挑战对方 3 claims）
        ↓
Rebuttals
        ↓
DebateResult（含 evidence_weights 附件 + debate_summary）
```

**产物**：

- `examples/600519_evidence_pack.json`
- `examples/600519_fundamental_research.json`
- `examples/600519_market_research.json`
- `examples/600519_bull.json` / `600519_bear.json`
- `examples/600519_debate.json`

**实现特征（代码阅读）**：

- Research / Debate 默认走 `GroundedLLMClient` / `debate/grounded.py` **确定性模板合成**，不是真实多轮 LLM 辩论。
- 这解释了：测试极快（ms 级）、输出稳定、同时深度有限且模板感强。

---

## 3. Evidence → Research Audit

### 抽样方法

从 Fundamental / Market 各抽取 **10 条** `status=supported` 的 findings，核对：

`claim → evidence_ids[0] → Evidence.claim`

### Fundamental（10）

| # | Agent claim（摘要） | Evidence | 判定 |
|---|---------------------|----------|------|
| 1 | 股票名称为贵州茅台 | stock_name 同文 | **A** |
| 2 | 所属行业…酒饮料… | industry 同文 | **A** |
| 3 | 上市日期 2001-08-27 | listing_date 同文 | **A** |
| 4 | 总股本… | total_shares 同文 | **A** |
| 5 | 流通股本… | float_shares 同文 | **A** |
| 6 | 2026-03-31 营收 539.09 亿 | operating_revenue 同文 | **A** |
| 7 | 2026-03-31 归母净利 272.43 亿 | net_profit_parent 同文 | **A** |
| 8 | 2025 营收同比 -1.21% | revenue_yoy 同文 | **A** |
| 9 | 2025 归母净利同比 -4.53% | net_profit_yoy 同文 | **A** |
| 10 | 2025 ROE 33.65% | roe 同文 | **A** |

### Market（10）

| # | Agent claim（摘要） | Evidence | 判定 |
|---|---------------------|----------|------|
| 1 | 最新价 1341.99 | close_price 同文 | **A** |
| 2 | 52周位置 0.5016 | price_position… 同文 | **A** |
| 3 | PE 20.28 | pe 同文 | **A** |
| 4 | PB 6.19 | pb 同文 | **A** |
| 5 | PS 9.57 | ps 同文 | **A** |
| 6–9 | MA5/20/60/250 数值 | 对应 DERIVED 同文 | **A** |
| 10 | MA5（均线结构段重复） | ma5 同文 | **A** |

### 统计

| 等级 | Fundamental | Market | 合计 |
|------|-------------:|-------:|-----:|
| A 直接支持 | 10 | 10 | **20** |
| B 部分支持 | 0 | 0 | 0 |
| C 关系较弱 | 0 | 0 | 0 |
| D 无法支持 | 0 | 0 | 0 |

### 关键发现

1. **Grounding 很强，但几乎是“复述 Evidence”**：多数 `claim` 与 `Evidence.claim` **逐字相同**。  
2. **interpretation 高度模板化**（例如业务段统一：“仅复述证据，不外推…”；财务段统一：“单一年度不足以外推…”）。这不是事实跳跃，而是**分析空洞**。  
3. **未发现“Evidence 是 A，结论却是无关 B”的硬幻觉**；问题是相反方向——**过度忠实复述，缺少综合**。  
4. Market `trend.narrative` 有一处真正综合：由 MA5>MA20>MA60 推出“短中期多头排列迹象”——这属于允许的派生解释，且基于已引用数值，**不算事实跳跃**。

---

## 4. Research Quality Audit

### Level 定义回顾

1. 只重复数据  
2. 事实 + 简单解释  
3. 事实之间建立关系  
4. 发现真正研究问题

### Fundamental Agent

| 观察 | Level |
|------|------:|
| 大量 findings = Evidence 原文 | 1 |
| summary / financial_performance narrative 提到“盈利增速承压” | 2 |
| 同时列出高 ROE 与净利同比下滑，但**未在同一 finding 内真正建模矛盾** | 2→3 边缘 |
| `insufficient_evidence`（客户结构等）是正确元认知 | 加分，但不等于深度 |

**主导 Level：1–2（偏复述与栏目化）**

### Market Agent

| 观察 | Level |
|------|------:|
| 价格/估值/均线大量复述 | 1 |
| 均线多头排列 + MA250 压力（narrative） | **3（少量）** |
| CLS `market_news` 大量与茅台弱相关（AI/CDN/北向等）被收入 recent_market_events | 组织噪音，非洞察 |
| 未形成“估值 vs 增速 vs 技术结构”的统一问题陈述 | 缺少 4 |

**主导 Level：1–2，偶发 3**

### 总判

Research Agent **完成了分区整理与引用纪律**，但**尚未稳定产出 Level 3–4 研究**。  
真正接近 Level 4 的表述，更多出现在后续 Bull/Bear / Debate Summary，而不是 Fundamental/Market 本体。

---

## 5. Bull / Bear Adversarial Audit

### Claims 对照

| Bull | Bear | 关系类型 |
|------|------|----------|
| BULL_01 盈利韧性（ROE/毛利率），并承认净利同比 -4.53% | BEAR_01 增速承压削弱增长叙事，并承认 ROE 仍高 | **B 同一事实不同解释**（高质量对立核心） |
| BULL_02 现金流/低负债 = 缓冲 | BEAR_02 价格低于 MA250 / 区间中部 = 结构压力 | **C 不相关维度**（基本面缓冲 vs 技术结构） |
| BULL_03 短中期均线 + 一致预期偏积极 | BEAR_03 估值/预期不足以证明风险已消化 + 夹带事件 | **B/E 混合**：有对抗，但 BEAR_03 论证偏松、事件引用弱 |

### 是否存在“同 Evidence 双解释”？

**有，而且是当前最有价值的部分：**

- Evidence：`net_profit_yoy = -4.53%`、`roe = 33.65%`、`gross_margin = 91.18%`
- Bull：高盈利能力仍在，增速承压是需承认的负面事实  
- Bear：增速转弱削弱投资叙事，高 ROE 不能对冲  

→ 明确的 **interpretation_conflict**（Challenge 中也已标注）。

### 诚实评价

- **不是空壳命名对立**：至少 BULL_01 ↔ BEAR_01 形成有效对抗。  
- **仍有模板化对立**：claims 数量固定 3、结构对称、措辞模式高度可预测（由 `debate/grounded.py` 按 subtype 存在与否分支生成）。  
- **不是充分 adversarial reasoning**：更像“预写好的多空立场卡片 + 固定互相点名”，而非围绕新信息动态升级的辩论。

---

## 6. Challenge Quality

共 6 条 Challenge，逐条评级：

| ID | target | type | Level | 是否削弱对方可信度 |
|----|--------|------|------:|--------------------|
| CH_BULL_01 | BEAR_01 | interpretation_conflict | **4** | 是：指出“单期下滑 ≠ 系统性恶化” |
| CH_BULL_02 | BEAR_02 | time_sensitivity | **4** | 是：时间尺度过宽 |
| CH_BULL_03 | BEAR_03 | assumption | **3** | 弱–中：指出假设，但自身也较抽象 |
| CH_BEAR_01 | BULL_01 | interpretation_conflict | **5** | 是：用对方同场 Evidence（净利同比）证明“韧性”解释不唯一 |
| CH_BEAR_02 | BULL_02 | scope | **4** | 是：指出范围外推 |
| CH_BEAR_03 | BULL_03 | evidence_insufficient | **3–4** | 中：指出遗漏 MA250，有效但模式化 |

**平均约 Level 3.5–4。**

### 关键问题

1. Challenge **不是 Level 1 的“我不同意”**——逻辑点是对的。  
2. 但它们是 **claim_id 分支模板**，不是阅读对方全文后的涌现批评。  
3. “是否真正改变可信度”：在结构化层面上改变了（对方随后大量 `partially_accept`）；在研究认知上，**没有引入新证据组合或新矛盾发现**，更多是把已知矛盾再说一遍。

---

## 7. Rebuttal Quality

| Rebuttal | response | 判定 | 说明 |
|----------|----------|------|------|
| RB_BULL_01 | partially_accept | **A/B** | 高质量：收窄 Claim 边界（能力水平 ≠ 增长已改善） |
| RB_BULL_02 | reject | **B** | 维度切割合理，但接近“重申原立场” |
| RB_BULL_03 | partially_accept | **B** | 承认缺长期均线；“缺的是综合权重”说法正确，但系统其实**没用 weight** |
| RB_BEAR_01 | partially_accept | **A/B** | 接受非永久恶化，坚持高 ROE 不能对冲增长风险 |
| RB_BEAR_02 | accept | **A** | 真正收缩 Bear Claim 口径（最佳回应之一） |
| RB_BEAR_03 | partially_accept | **B** | 把假设降级为 uncertainty，程序正确但内容浅 |

**分布粗估**：A×2，B×4，C/D/E≈0。

### 关键问题

- Rebuttal **多数在处理逻辑边界**（好），但很少用**新的 evidence 组合**升级论点。  
- 出现“提到综合权重”却 **WEIGHT_NOT_USED**（见第 10 节）——这是元层面不一致。

---

## 8. Grounding / Hallucination Audit

### 总体

- 所有核心 Claim / Challenge / Rebuttal 均带 `evidence_ids`，且 ID 均存在于 Evidence Pack。  
- **未发现编造财务数字、伪造日期、伪造 EPS 一致预期**这类硬幻觉。

### UNSUPPORTED_FACT（相对“该 Claim 的 evidence_ids”）

| 位置 | 内容 | 问题 |
|------|------|------|
| BULL_01.reasoning | 引用净利同比 **-4.53%** | 该 Claim 只 cite 了 ROE / 毛利率，**未 cite** `net_profit_yoy` |
| BEAR_01.reasoning | 引用 ROE **33.65%** | 该 Claim 未 cite ROE evidence |
| BEAR_03.reasoning | 引用毛利率 **91.18%** | 该 Claim 未 cite gross_margin |

这些数字在 Pack 中真实存在，属于 **跨 Claim 泄漏 / 引用不完整**，不是凭空捏造。按审计标准仍标记：

> **UNSUPPORTED_FACT（citation-incomplete）** ×3

### 其他

- BEAR_03 引用 `shareholder_change`（2025-12-30，stale）与“风险未消化”之间逻辑链条弱 → 更接近 **弱推理**，不是幻觉。  
- Market recent events 中大量非茅台相关快讯被当作“市场事件证据” → **相关性幻觉风险**（把宏观噪音当公司证据）。

---

## 9. Freshness Audit

Evidence Pack freshness 分布（审计时）：

- `very_recent`: 62  
- `periodic`: 44  
- `stale`: 5  
- `historical_recent`: 1  

### 问题实例

| 现象 | 判定 |
|------|------|
| Fundamental `recent_events` 纳入多条 **stale** 股东变动（含 2023-06-28）与“近期事件”并列 | **STALENESS_IGNORED** |
| Bear 用 stale 股东事件支撑“风险未消化”叙事 | **STALENESS_IGNORED**（权重上未降权使用） |
| CLS very_recent 市场新闻与茅台弱相关，却进入 Market Agent 主视野 | 时效新，但 **relevance 差** |
| 财务 `periodic` 与行情 `very_recent` 在辩论中几乎同等叙述权重 | 未体现 freshness 差异化 |

**结论**：freshness 字段存在，但 Agent **基本未按 freshness 做解释权重分化**。

---

## 10. Evidence Weight Audit

- `calculate_evidence_weight()` 实现正确（测试验证：high×very_recent=1.0，low×stale=0.24）。  
- DebateResult 附带 `evidence_weights`（本次 19 条）。  

### 是否进入推理？

检查 Bull / Bear / Challenge / Rebuttal 文本与生成路径：

- **生成阶段不读取 weight**  
- **Claim 选择不按 weight 排序**  
- **Challenge.strength 为模板常数，不是 weight 函数**  
- 仅在 `debate_engine` 结束后把 weight **附录**进结果

> **标记：WEIGHT_NOT_USED**

唯一相关文本是 Rebuttal 提到“综合权重”，属于口头提及，**不是计算使用**。

---

## 11. Information Compression

| 对象 | 约字符数（JSON） |
|------|-----------------:|
| Evidence Pack | ~93k |
| Fundamental + Market | ~41k |
| Debate | ~12k |
| Research+Debate 合计 | ~53k |

### 是否降低信息处理成本？

**有一部分，但不够：**

| 能力 | 现状 |
|------|------|
| Data compression | **弱**：大量 claim=原文复制；同一 MA 在 trend / MA structure / technical 重复出现 |
| Information organization | **中**：分栏目（盈利/现金流/均线等）确实比 112 条扁平列表好读 |
| Conflict identification | **中偏上**：Debate 明确标出 ROE vs 增速 interpretation_conflict |

对普通用户：

- 看 Fundamental/Market：**比直接啃 112 条省事**，但仍像“带引用的摘录本”。  
- 看 Bull/Bear/Debate：**第一次出现真正可消费的研究冲突**。  

若去掉 Debate，Research 层单独的压缩收益有限。

---

## 12. Top Research Insights

当前系统**可以**提炼出少数有价值 insight（主要来自 Debate，而非 Research Agent 主动陈述）。以下不超过 5 条；不强行凑数。

### Insight 1（高价值）

- **Insight**：当前核心矛盾不是“茅台是否具备高盈利能力”，而是“高盈利能力与近期盈利/营收增速下滑如何共存、谁主导叙事”。  
- **Evidence**：ROE 33.65%；毛利率 91.18%；净利同比 -4.53%；营收同比 -1.21%。  
- **Reasoning**：Bull/Bear 对同一证据组给出能力韧性 vs 增长恶化两种解释，Challenge 将其标为 interpretation_conflict。  
- **Why it matters**：这是后续 Final Analyst 真正该裁决的问题；其余多为派生噪声。

### Insight 2（中高价值）

- **Insight**：市场结构存在时间尺度分裂——短中期均线偏多头，价格仍低于 MA250。  
- **Evidence**：MA5/MA20/MA60/MA250；close 1341.99。  
- **Reasoning**：Market narrative + BULL_03/BEAR_02 + time_sensitivity Challenge。  
- **Why it matters**：避免把“短线动能”误写成“趋势已确认”。

### Insight 3（中价值）

- **Insight**：财务缓冲（经营现金流、低资产负债率）与增长叙事是不同维度，不能互相替代。  
- **Evidence**：ocf_to_net_profit、operating_cash_flow、debt_to_asset_ratio、net_profit_yoy。  
- **Reasoning**：BULL_02 vs CH_BEAR_02(scope) → 部分拒绝/切割。  
- **Why it matters**：防止把“资产负债表健康”偷换成“增长故事成立”。

### Insight 4（有限价值）

- **Insight**：Evidence Pack 缺少客户结构/管理层指引，因此任何关于护城河可持续性的强结论都不可靠。  
- **Evidence**：`insufficient_evidence` 标记（非财务数字）。  
- **Reasoning**：元认知正确。  
- **Why it matters**：限制了 Bull/Bear 能走多远——这也是系统诚实之处。

### 未能稳定形成的 Insight

- 估值（PE 20.28）与一致预期（EPS 2026/27/28）之间是否“定价充分”：**Bear 提出了，但论证弱，事件引用混杂，不算扎实 insight。**

> 若只看 Fundamental/Market 而不看 Debate：更接近  
> **“当前 Agent Layer 研究价值有限，主要是证据编排。”**  
> 加上 Debate 后：出现了真正研究问题，但仍偏模板。

---

## 13. Scorecard

| # | 维度 | 分数 (0–5) | 简要理由 |
|---|------|----------:|----------|
| 1 | Evidence Grounding | **4** | 引用纪律强；存在 citation-incomplete 与弱相关事件 |
| 2 | Research Depth | **2** | 以 Level 1–2 复述为主，Level 3 偶发，Level 4 稀缺 |
| 3 | Fundamental Analysis | **3** | 栏目完整、缺口诚实，但综合浅 |
| 4 | Market Analysis | **2** | 均线综合尚可；CLS 噪声与重复严重 |
| 5 | Bull/Bear Differentiation | **3** | 有真实 interpretation conflict，但模板对称 |
| 6 | Challenge Quality | **3** | 逻辑点到位，非涌现式深挖 |
| 7 | Rebuttal Quality | **3** | 多次 partially_accept/收窄口径，升级有限 |
| 8 | Information Compression | **2** | 有组织，压缩不足，重复多 |
| | **Total** | **22 / 40** | |

---

## 14. Major Problems

1. **研究层深度不足**：Fundamental/Market 更像 “Evidence 分拣机”，不是研究员。  
2. **Agent 智能主要是模板**：`research/llm.py` grounded synthesizer + `debate/grounded.py` 主导输出；多 Agent 形态具备，**对抗认知偏脚本化**。  
3. **WEIGHT_NOT_USED**：权重只落盘，不参与推理。  
4. **STALENESS_IGNORED / 弱相关 EVENT**：过时股东变动、无关快讯进入“近期/市场事件”。  
5. **citation-incomplete**：reasoning 引用了未列入该 Claim `evidence_ids` 的数字。  
6. **信息膨胀式重复**：同一指标在多 section / 多 claim 重复出现，压缩失败。  
7. **测试虚高**：62/62 PASS 掩盖了质量短板（测契约不测研究）。

---

## 15. What Should NOT Be Changed

以下环节**已经足够，不宜继续过度开发**：

1. **Evidence Schema / Pack / 禁止 opinion 字段** —— 地基正确。  
2. **“Agent 不得直连数据源 / 不得造事实”硬约束** —— 必须保留。  
3. **Claim 必须挂 evidence_id 的契约** —— 保留并加强（补齐 reasoning 引用）。  
4. **结构化 Debate 流程（Claims→Challenges→Rebuttals，限轮次）** —— 框架正确，不要改成自由聊天。  
5. **禁止 bull_score / 概率化买卖建议** —— 在 Final Analyst 之前必须继续禁止。  
6. **不足证据显式 `insufficient_evidence`** —— 这是优点，不要为了“完整报告”删掉。

---

## 16. Final Analyst Readiness

若现在接入 Final Analyst，**最可能出现的问题**：

1. 把模板化 Bull/Bear 当成“充分辩论后的收敛”，**过度自信产出评级**。  
2. 被 CLS 噪声事件与 stale 股东变动误导。  
3. 看到 `evidence_weights` 却误以为辩论已按权重完成，**造成程序正义幻觉**。  
4. 在客户结构/管理层指引缺失时，仍被要求给投资结论 → **缺口被强行填平**。  
5. Research 层未把核心矛盾写清楚时，Final Analyst 可能退化为“复述 Debate Summary + 拍板”。

---

## 17. GO / NO-GO

### 门槛核对

| 条件 | 要求 | 实际 | 结果 |
|------|------|------|------|
| Evidence Grounding | ≥ 4 | 4 | PASS |
| Research Depth | ≥ 3 | **2** | **FAIL** |
| Bull/Bear Differentiation | ≥ 3 | 3 | PASS |
| Challenge Quality | ≥ 3 | 3 | PASS |
| Rebuttal Quality | ≥ 3 | 3 | PASS |
| Information Compression | ≥ 3 | **2** | **FAIL** |

# 最终判定：**NO-GO**

### 最小必要修改项（仅建议，本次不改代码）

1. **提升 Research Depth（最高优先）**  
   - Fundamental/Market 强制产出跨指标关系句（至少把 ROE×增速、价格×MA250 写成 Level 3 finding），禁止大量 `claim == Evidence.claim` 灌水。  
2. **让 weight/freshness 进入推理**  
   - Claim 选择、Challenge.strength、事件是否进入“近期”上下文，必须读取 `calculate_evidence_weight` / freshness。  
3. **事件相关性过滤**  
   - CLS 弱相关快讯不得进入公司/个股 Market 主证据池；stale 事件不得与 very_recent 等价叙述。  
4. **收紧 citation**  
   - reasoning 中出现的数字必须出现在该对象的 `evidence_ids` 中。  
5. **去重压缩**  
   - 同一 evidence_id 默认只在一个主 section 完整展开。

完成以上后，再评估是否 **GO** 进入 Final Analyst。

---

## 附录：对六个关键问题的直接回答

1. **是不是真正的 Multi-Agent Research Pipeline？**  
   **结构上是，认知上偏弱。** 它是可运行的多模块研究流水线；但核心“智能”大量是确定性模板，不是充分自治的多智能体推理。

2. **Bull/Bear 是否形成有效 Adversarial Reasoning？**  
   **部分有效。** 在“高盈利 vs 增速承压”上有效；整体仍是对称模板对抗，不是深度攻防升级。

3. **当前最大问题是什么？**  
   **Research Depth 不足 + 模板化对抗 + 权重/时效未进入推理。**

4. **哪一环节最需要继续迭代？**  
   **Fundamental/Market 的综合分析质量（Depth & Compression）**，其次才是把 weight/freshness 接入 Debate。

5. **哪些已经足够、不应过度开发？**  
   Evidence 层契约、只读 Evidence 约束、结构化 Debate 轮次、禁止评分式概率买卖。

6. **现在接 Final Analyst 最可能出什么问题？**  
   在浅层研究与未使用权重的辩论之上，**过早给出看似权威的投资裁决**。

---

*End of Audit — NO-GO for Final Analyst.*
