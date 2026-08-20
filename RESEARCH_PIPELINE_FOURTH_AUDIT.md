# Research Pipeline Fourth Audit

**标的**：600519（贵州茅台）+ 跨行业合成样本 + 双边 narrative fixture  
**审计类型**：Final Analyst 开发前稳定性审计（契约 / Canonical Integrity / 质量抽检）  
**审计日期**：2026-08-15  
**对照**：第三轮 `RESEARCH_PIPELINE_THIRD_AUDIT.md`（GO，允许重新评估）

> 原则：压缩研究表达，不压缩证据事实；Canonical 是研究事实源，Compat 是引用接口。  
> 本阶段**未实现 Final Analyst**；仅定义 `ResearchOutputContract`。  
> Grounded ≠ Autonomous Research；Weight ≠ 投资概率。

---

## 1. Test Status

| Suite | Result |
|------|--------|
| `tests.test_evidence` | 13/13 PASS |
| `tests.test_research_context_modules` | 23/23 PASS |
| `tests.test_research_agents` | 30/30 PASS |
| `tests.test_research_compression` | 29/29 PASS |
| `tests.test_research_stability`（本阶段新增） | 62/62 PASS |
| `tests.test_debate` | 25/25 PASS |
| **合计** | **182/182 PASS** |

新增覆盖：`canonical_uniqueness` / `reference_is_not_new_finding` / `evidence_preservation` / `numeric_citation` / `incremental_finding_value` / `cross_industry_relevance` / `weight_conflict_selection` / `narrative_shift` / `narrative_insufficient` / `debate_canonical_consumption` / `ResearchOutputContract`。

---

## 2. 本阶段做了什么（非大规模重构）

| 项 | 动作 |
|----|------|
| Canonical 唯一权威 | `canonical_findings` 为唯一完整研究表达；`key_*` / `research_tensions` / `cross_evidence_findings` / compat → **reference** |
| FA 契约 | 新增 `src/research/contract.py` → `ResearchOutputContract` |
| Relevance 泛化 | 消费品 / 制造 / 半导体 profile；禁止「产业/市场」泛 token 升 industry |
| Narrative | 主题标签变化才记 shift；同主题不强制；缺一侧 insufficient |
| Debate | 小修：Bull/Bear 对齐 `TENSION_FUND_PROFIT_VS_GROWTH`；补齐 BULL 对净利同比的 evidence_id；shared context 暴露 canonical ids |
| 未做 | Final Analyst 实现；时间窗修改；Weight 重设计；Debate schema 重构 |

---

## 3. 人工抽检

### 3.1 Fundamental Canonical（≥3）

| ID | 数字保留 | 关系 | Interpretation | Boundary | Level |
|----|----------|------|----------------|----------|------:|
| `TENSION_FUND_PROFIT_VS_GROWTH` | ROE 33.65% / 毛利率 91.18% / 净利同比 -4.53% / 营收同比 -1.21% | 盈利强 vs 增长承压 | 分化判断 | 单期不足以判结构 | **4** |
| `FINDING_FUND_CASH_QUALITY` | OCF/净利 74.74% + 现金流/净利金额 | 现金含量约束利润 | 有 | 多期趋势不作定论 | **3–4** |
| `TENSION_FUND_VALUATION_VS_GROWTH` | PE 20.28 / PB 6.19 + 财务同比 | 估值截面 × 财报期 | 条件判断 | 无目标估值 | **3–4** |

### 3.2 Market Canonical（≥3）

| ID | 要点 | Level |
|----|------|------:|
| `FINDING_MKT_PRICE_MA` | 价 1341.99 + MA5/20/60/250；短中期多头排列 | **3** |
| `TENSION_MKT_SHORT_VS_LONG` | MA5/20 vs MA250 时间尺度冲突 | **3–4** |
| `FINDING_MKT_VAL_PRICE` | PE/PB × 价格/52周位置 | **3** |

### 3.3 Relevance（≥2 领域）

| 领域 | stock | industry | macro | irrelevant |
|------|-------|----------|-------|------------|
| 消费品（海天/调味品） | ✓ 公司名 | 调味品去库存 ✓ | 外汇局 ✓ | CDN ✓ |
| 制造（潍柴/汽车零部件） | ✓ | 新能源车链 ✓ | 社融/央行 ✓ | 富维定点 ✓ |
| 科技（中芯/半导体） | ✓ | 晶圆代工 ✓ | 美联储/国债 ✓ | 白酒批价 ✓ |

### 3.4 Narrative Change（主题不同）

Previous：渠道去库存 / 需求承压 → Current：提价 / 销量恢复 / 管理层  
→ 产出 `narrative change` + 双侧 evidence_ids；同主题样本明确「不得强行」。

### 3.5 Debate × Canonical

Bull/Bear reasoning 显式引用 `TENSION_FUND_PROFIT_VS_GROWTH`；**不复制** canonical 全文；BULL_01 对净利同比数字已挂对应 evidence_id（小修）。

---

## 4. ResearchOutputContract（FA 输入面）

```
research_as_of_date
canonical_findings          ← 唯一权威研究表达
research_tensions           ← 从 canonical 过滤（kind=tension）
research_gaps
evidence_references
excluded_audit
relevance / research_role notes
time_context
uncertainty_boundaries
```

**Final Analyst 默认不得：**

- 以 raw EvidencePack 作主研究输入  
- 扫描 compat sections 寻找新事实  
- 把数字再总结一遍当成分析  
- 把 weight 当买卖概率  

---

## 5. Scorecard（1–5）

| 维度 | 第三轮 | 本轮 | 说明 |
|------|------:|-----:|------|
| Evidence Grounding | 4 | **4** | Research citation 稳定；Debate 遗留基本消除于本标的 Bull 数字漏引（小修） |
| Evidence Preservation | 4 | **4** | 关键数字仍在 canonical；4/4 保留+引用 |
| Research Depth | 3 | **3** | 不以 finding 数量堆深度；核心 L3–4 |
| Fundamental Analysis | 4 | **4** | 稳定 |
| Market Analysis | 3 | **3** | 价格/均线张力稳定；实盘新闻仍常不足 |
| Information Compression | 3 | **4** | 全文仅存于 canonical；其余 reference |
| Relevance Precision | 3 | **3** | 跨行业合成达标；非学习型分类器 |
| Time Context | 4 | **4** | 窗口未改；叙事质量验证补齐 |
| Weight Selection | — | **4** | 选题优先；冲突时不删低 weight；非概率 |
| Canonical Integrity | — | **4** | uniqueness + reference 非新洞察 |
| Debate Consumption | — | **3** | 能引用 canonical id；仍 grounded 立场卡，非深度消费全文张力 |

---

## 6. A/B/C/D/E 分层结论

### A. 已稳定

- Canonical 作为唯一完整研究表达  
- Evidence Preservation（数字 + evidence_ids）  
- PIT / 7d / 8–30d 时间契约  
- Weight 进入候选选择（非装饰）  
- Research → FA 的 `ResearchOutputContract` 面已定义  
- 回归测试 182/182  

### B. 机制通过测试，质量仍需产品侧证明

- 跨行业 Relevance：规则表扩展，非模型泛化  
- Narrative shift：合成主题标签有效；真实盘面双边个股新闻仍稀缺  
- Debate 对 canonical 的「引用」已有；「深度辩论消费」仍浅  

### C. Research Layer 真实残余问题

- Grounded 仍是确定性合成，模板感降低但未消失  
- 部分 finding 的 relation marker 启发式不完全（如估值句依赖「若/则」而非「但」）  
- 行业 profile 需随标的扩展维护  

### D. 下游（Debate / Final Analyst）问题

- Challenge/Rebuttal 仍主要打 Evidence 卡，而非系统性攻击 canonical tension 结构  
- Final Analyst 尚未实现；输入契约已就绪待设计  

### E. 是否具备进入 Final Analyst **正式设计**？

**是（GO）**——在「设计阶段」意义下：输入面清晰、权威源唯一、数字不被压缩掉、compat 不再冒充新研究。

---

## 7. GO 门槛核对

| 指标 | 要求 | 本轮 | 结果 |
|------|------|-----:|------|
| Evidence Grounding | ≥4 | 4 | PASS |
| Evidence Preservation | ≥4 | 4 | PASS |
| Research Depth | ≥3 | 3 | PASS |
| Fundamental | ≥3 | 4 | PASS |
| Market | ≥3 | 3 | PASS |
| Information Compression | ≥3 | **4** | PASS |
| Relevance Precision | ≥3 | 3 | PASS |
| Time Context | ≥3 | 4 | PASS |
| Canonical Integrity | ≥4 | **4** | PASS |

# 最终判定：**GO**

**含义**：允许进入 **Final Analyst 正式设计阶段**。  
**不等于**：已实现 Final Analyst；也**不自动开工实现**。

建议 FA 设计时强制：

1. 只读 `ResearchOutputContract`（或等价字段）  
2. 对每个结论回溯 `canonical_finding_id` + `evidence_ids`  
3. 禁止再做 Research 层筛选 / 伪 Cross  
4. 显式输出 uncertainty / boundary，而不是买卖标签  

---

## 8. 若未来 NO-GO 时的最小修复清单（当前不适用）

（本轮全部门槛达标；下列仅作预案）

1. Canonical Integrity <4 → 检查 compat 是否又写入全文  
2. Preservation <4 → 禁止为 compression 删数字  
3. Relevance <3 → 扩 profile，不引入向量库  

---

*End of Fourth Audit — GO for Final Analyst design; do not auto-implement Final Analyst.*
