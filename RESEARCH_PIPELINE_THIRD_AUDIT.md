# Research Pipeline Third Audit

**标的**：600519（贵州茅台）+ 合成叙事对照样本  
**审计类型**：Research Layer 第三阶段（Compression / Relevance / Analytical Quality）  
**审计日期**：2026-08-15  
**对照**：第二轮 `RESEARCH_PIPELINE_SECOND_AUDIT.md`（总分 25/40，NO-GO，Compression=2）

> 原则：测试 PASS ≠ 自动 GO。验收核心是「压缩重复的研究表达，而不是压缩事实数字」。  
> Grounded 模式仍是离线确定性合成，**不宣称 Autonomous Research**。

---

## 1. Test Status

| Suite | Result |
|------|--------|
| `tests.test_evidence` | 13/13 PASS |
| `tests.test_research_context_modules` | 23/23 PASS |
| `tests.test_research_agents` | 30/30 PASS |
| `tests.test_research_compression`（新增） | 29/29 PASS |
| `tests.test_debate` | 25/25 PASS |
| **合计** | **120/120 PASS** |

新增覆盖：`compression` / `evidence_preservation` / `relevance_precision` / `weight_selection` / `finding_increment` / `citation_completeness` / `narrative_change` fixture。

---

## 2. Pipeline 状态（本阶段后）

```
Evidence Pack
  → PIT / Time Window
  → Relevance + research_role
  → Weight ranking & candidate selection
  → Research Question bundles
  → Canonical Cross / Tension（数字保留）
  → Compat sections：reference → canonical（不克隆全文）
  → Bull / Bear / Challenge / Rebuttal（未重构）
  → Final Analyst（仍未实现；本阶段不自动开工）
```

---

## 3. 本阶段相对上轮的关键改动

| 问题（上轮） | 本轮处理 |
|--------------|----------|
| 同一命题多 section 克隆 | `canonical_findings` + `finding_kind=reference` |
| 弱相关进核心 | 强行业 token；外汇局→macro；富维/*ST/CDN→excluded |
| Weight 只装饰排序 | `select_by_weight` / `select_best_per_subtype` 进入 bundle |
| Grounded subtype 固定句 | 改为 bundle → 共同研究问题 → 有关系才生成；否则 insufficient |
| 压缩时丢掉数字 | Canonical claim **显式保留** ROE/毛利率/同比等 |
| 伪 Cross 拼盘 | 禁止弱资讯拼盘；macro/industry 分层，不进核心 tension |

---

## 4. Evidence Preservation（新增）

随机核心 Canonical Finding（600519 Fundamental 全部 4 条）：

| Finding | 关键数字保留 | 引用完整 | 分析增量 | 非纯罗列 |
|---------|:------------:|:--------:|:--------:|:--------:|
| PROFIT_VS_GROWTH | 33.65% / 91.18% / -4.53% / -1.21% | ✓ | ✓ | ✓ |
| CASH_QUALITY | 74.74% / 269.10 / 272.43 | ✓ | ✓ | ✓ |
| BALANCE_OP | 16.42% / 487.87 / 539.09 / 272.43 | ✓ | ✓ | ✓ |
| VALUATION_VS_GROWTH | PE 20.28 / PB 6.19 + 财务同比 | ✓ | ✓ | ✓ |

测试：`evidence_preservation_ratio = 4/4 = 1.00`（≥90%）。

**代表性 L3/L4（数字未隐去）**：

> 2025-12-31 ROE 为 **33.65%**、毛利率为 **91.18%**；同时归母净利润同比下降 **4.53%**、营收同比下降 **1.21%**。这表明盈利能力仍处较高水平，但增长端已出现压力……现有证据可支持分化判断，但单期同比不足以判定短期 vs 结构性。

**Evidence Preservation Score：4**

---

## 5. Information Compression

| 检查 | 结果 |
|------|------|
| Canonical 命题权威陈述 | Fundamental 4 条；Market 3 条 |
| profitability / strengths 等 | **reference → TENSION_…**，非全文克隆 |
| `full_clones`（compat vs canonical） | **0** |
| 同一“高 ROE×增长承压”全文复制次数 | 上轮 5–10+ → **本轮 1（canonical）+ refs** |

按新标准：

- 核心命题已集中；compat 通过 reference 消费。  
- 仍有意保留 `cross_evidence_findings` 作为 Debate 兼容脊柱（内容=canonical，非第三份改写）。  
- Grounded 句式仍可辨（“需对照…理解”），但不再靠多栏目堆同一分析。

**Information Compression：2 → 3**（达到进入 Final Analyst 评估门槛；尚未到 4/5）

---

## 6. Research Depth

| 区域 | 主导 Level | 说明 |
|------|----------:|------|
| Fundamental canonical | **3–4** | 数字 + 多证据 + 关系 + 边界 |
| Market price/MA / short×long | **3–4** | 多头排列 + 长短期尺度张力 |
| Core facts / gaps | 1–2 / — | 锚点与缺口，正确 |
| 新闻叙事（600519） | — | Current 个股资讯不足 → insufficient（正确） |

数字本身未降级 Level；关系成立。

**Research Depth：3**（持平达标；非 Autonomous）

---

## 7. Relevance Precision

600519 实盘 context：

| 样本 | 分类 / 去向 |
|------|-------------|
| 外汇局经常账户顺差 | `macro_market` → `macro_background` |
| 富维股份座椅定点 | **irrelevant / excluded** |
| *ST 闻泰亏损 | **irrelevant / excluded** |
| CDN/GPU/液冷 | **irrelevant / excluded** |
| 白酒行业… | `industry_related`（单测） |
| 贵州茅台公告 | `stock_specific`（单测） |
| 联发科技等弱“行业”窗 | **不再进入 industry_30d**（本轮 industry_ctx=[]） |

`research_role`：macro→`macro_background`；industry→`industry_context`；irrelevant→`excluded`。

**Relevance Precision：2（上轮）→ 3**

残余：强 token 规则偏白酒友好；跨行业泛化仍粗；非本阶段向量检索。

---

## 8. Weight Selection

- Bundle 内按 subtype 取 **最高 weight** 候选。  
- 单测：`roe_high`(1.0) 优先于 `roe_low`(stale/low)。  
- stale 不再在同等条件下覆盖 very_recent（via weight 定义未改）。

**判定：USED（选题级）**，非复杂模型。

---

## 9. Time Context / Narrative Change

| 项 | 600519 | 合成 fixture |
|----|--------|----------------|
| as_of / PIT | ✓ | ✓ |
| 7d / 8–30d 不重叠 | ✓ | ✓ |
| Current+Previous 双边个股新闻 | Current 空 → insufficient | **两边均有 → 生成 NEWS_NARRATIVE tension** |
| 宏观不进 news core | ✓ 外汇局进 macro | ✓ |

**Time Context：4**

---

## 10. Fundamental / Market Quality

| 能力 | 判定 |
|------|------|
| 高盈利 × 增长张力（带数字） | **是** |
| 估值 × 增长假设条件判断 | **是** |
| 短×长均线冲突 | **是** |
| 禁止伪 Cross 资讯拼盘 | **是** |
| 新闻 narrative change（实盘） | 本样本证据不足 → insufficient |
| 新闻 narrative change（对照样本） | **已验证** |

仍不是成熟自主研究员；是可复现的 grounded 综合器。

---

## 11. Citation / Debate 遗留

| 层 | 状态 |
|----|------|
| Research claim/reasoning/interpretation → 本 Finding evidence_ids | **PASS**（agents + compression 测试） |
| Debate citation-incomplete（如 BULL reasoning 数字漏引） | **遗留，本阶段不重构** |
| Debate 消费新 schema | **25/25 PASS**（compat sections + 默认字段） |

---

## 12. Scorecard

沿用 1–5 分；本轮增加 Preservation / Relevance / Time，并突出 Compression 门槛。

| 维度 | 第二轮 | 本轮 | 变化 |
|------|------:|-----:|------|
| Evidence Grounding | 4 | **4** | 持平 |
| Evidence Preservation | — | **4** | 新增达标 |
| Research Depth | 3 | **3** | 持平 |
| Fundamental Analysis | 4 | **4** | 持平 |
| Market Analysis | 3 | **3** | 持平（伪 cross 消除） |
| Information Compression | **2** | **3** | **+1（硬门槛翻过）** |
| Relevance Precision | ~2 | **3** | +1 |
| Time Context | 3 | **4** | +1 |
| Bull/Bear Differentiation | 3 | **3** | 持平（未改） |
| Challenge Quality | 3 | **3** | 持平 |
| Rebuttal Quality | 3 | **3** | 持平 |

原 8 维续算（便于对照上轮 25/40）：

| 原 8 维 | 上轮 | 本轮 |
|---------|-----:|-----:|
| Grounding | 4 | 4 |
| Depth | 3 | 3 |
| Fundamental | 4 | 4 |
| Market | 3 | 3 |
| Bull/Bear | 3 | 3 |
| Challenge | 3 | 3 |
| Rebuttal | 3 | 3 |
| Compression | 2 | **3** |
| **Total** | **25** | **26** |

---

## 13. 成功标准核对（进入 Final Analyst 评估门槛）

| 指标 | 要求 | 本轮 | 结果 |
|------|------|-----:|------|
| Evidence Grounding | ≥4 | 4 | PASS |
| Evidence Preservation | ≥4 | 4 | PASS |
| Research Depth | ≥3 | 3 | PASS |
| Fundamental Analysis | ≥3 | 4 | PASS |
| Market Analysis | ≥3 | 3 | PASS |
| Information Compression | **≥3** | **3** | **PASS** |
| Relevance Precision | ≥3 | 3 | PASS |
| Time Context | ≥3 | 4 | PASS |

# 最终判定：**GO**（仅指：允许重新评估是否开发 Final Analyst）

**明确边界**：

1. **本阶段不自动开始 Final Analyst。**  
2. Grounded ≠ Autonomous；若 Final Analyst 依赖“真实涌现研究”，仍需另议 LLM 模式与评测。  
3. Debate citation-incomplete、Bull/Bear 未充分吸收 canonical tensions，建议在 Final Analyst 之前或并行小修，但不阻塞本轮 Research 门槛。  
4. Compression 刚到 3：后续可把 compat 引用再瘦、减少 residual 模板套话，冲 4。

---

## 14. Major Remaining Problems（非本轮阻塞）

1. Grounded 仍可预判句式（降低模板感有进步，未消除）。  
2. Debate 层 citation 与 Research tension 消费不足。  
3. 600519 实盘缺双边个股新闻 → narrative change 靠合成样本证明能力。  
4. Relevance 强 token 对白酒友好；其他行业需扩展规则表。  
5. Final Analyst 尚未设计输入契约（应消费 `canonical_findings`，而非再扫 compat 克隆）。

---

## 附录：十问直答

1. 数字是否被隐去？→ **否**，核心 Finding 保留关键数字并参与分析。  
2. Compression ≥3？→ **是（3）**。  
3. 同命题是否多 section 全文重复？→ **否**（reference）。  
4. Weight 是否参与选题？→ **是**。  
5. Relevance 是否挡住外汇局/富维/*ST/CDN？→ **是**。  
6. 是否仍有伪 Cross 资讯拼盘？→ **核心已消除**。  
7. Research citation？→ **合格**；Debate 遗留。  
8. Depth 是否因保留数字下降？→ **否**。  
9. Grounded 是否被描述成 Autonomous？→ **否**。  
10. 可否开工 Final Analyst？→ **门槛 GO，但本阶段不自动开工**；需产品决策。

---

*End of Third Audit — GO for Final Analyst re-evaluation; do not auto-start Final Analyst.*
