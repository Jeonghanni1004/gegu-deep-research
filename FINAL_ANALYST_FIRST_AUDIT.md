# Final Analyst First Audit

**标的**：600519（贵州茅台）  
**审计类型**：Final Analyst 第一轮质量审计（测试 + 人工对照 Research）  
**审计日期**：2026-08-15  
**模式**：`grounded`（确定性综合；**不是** Autonomous Research）

> 原则：测试 PASS ≠ Quality PASS。核心问题是：**FA 是否真的比 Research 高一层？**

---

## 1. 交付物

### 新增

| 路径 | 说明 |
|------|------|
| `src/final_analyst/schemas.py` | FinalAnalystOutput / AnalyzedStatement / Scenario / … |
| `src/final_analyst/contract.py` | FinalAnalystInput + fail-closed as_of |
| `src/final_analyst/synthesize.py` | Grounded FA |
| `src/final_analyst/validators.py` | 质量校验门 |
| `src/final_analyst/llm.py` | grounded / openai（失败降级 grounded） |
| `src/final_analyst/agent.py` | FinalAnalystAgent |
| `src/final_analyst/pipeline.py` | CLI 入口 |
| `tests/test_final_analyst.py` | 26 项质量测试 |
| `examples/600519_final_analyst.json` | 产物 |

### 最小修改（允许范围）

| 路径 | 说明 |
|------|------|
| `src/debate/schemas.py` | `ResearchClaim.canonical_finding_ids` |
| `src/debate/grounded.py` | 填充 canonical 链接 |

### 未修改

Evidence / Time / Weight / Relevance / Research canonical 生成 / Debate 主流程 / 数据源。

---

## 2. 测试结果

| Suite | Result |
|------|--------|
| `tests.test_final_analyst` | **26/26 PASS** |
| `tests.test_debate` | 25/25 PASS |
| `tests.test_research_agents` | 30/30 PASS |
| `tests.test_research_stability` | 62/62 PASS |

（Evidence / compression / context 未在本轮重复全跑，但 FA 实现未触及其核心逻辑。）

---

## 3. Research vs FA 逐条对照（600519）

| Research（已有） | FA（本轮） | 是否重复？ |
|------------------|------------|------------|
| ROE 33.65% × 毛利率 91.18% × 净利同比 -4.53% × 营收同比 -1.21% → 盈利强、增长承压 | **不复述关系**；升维为「增长不确定性优先于盈利能力恶化担忧」 | **否**（有 analytical increment） |
| 估值 × 增长：估值更依赖增长恢复 | 解释为「估值约束应主要来自增长能否被验证」并进入 Base/Bull/Bear 条件分支 | **半重叠但升维**（implication + scenario） |
| 短×长均线冲突 | 「市场叙事不能单独消解财务增长争议」 | **否**（跨层解释优先级） |
| Debate unresolved：阶段性 vs 结构性 | 进入 `current_assessment` + `uncertainty` + what-would-change | **消费而非丢弃** |

### FA executive（摘录）

> 主导解释框架应是：增长不确定性优先于盈利能力恶化担忧；估值与乐观叙事的约束应主要来自增长能否被验证……关键事实数字（33.65%、91.18%、4.53%、1.21%）支撑该优先级，但单期同比不足以裁定阶段性 vs 结构性。

### Traceability

- `canonical_finding_ids`: PROFIT_VS_GROWTH / VALUATION_VS_GROWTH / SHORT_VS_LONG  
- `evidence_ids`: 10+  
- `debate_refs`: BULL_01 / BEAR_01；core_tensions 含 challenges + rebuttals  
- `numbers_used`: 保留关键同比与 ROE/毛利率  

---

## 4. Analytical Increment 检查

| 检查 | 结果 |
|------|------|
| 是否仅同义复述「高 ROE × 增长承压」 | **否** |
| 是否有 interpretation priority | **是** |
| 是否有 conditional scenario + ASSUMPTION | **是** |
| 是否消费 Challenge/Rebuttal | **是**（结构化挂载；评估语句仍偏 grounded 模板） |
| 是否补全客户结构 gap | **否**（明确「不得补全」） |
| 是否输出买卖/概率 | **否** |

**结论**：存在真实的 Research→Analyst 跃迁，但 **Grounded 仍是确定性模板综合**，深度有上限。

---

## 5. Grounded vs OpenAI

| | Grounded（本轮默认产物） | OpenAI |
|--|--------------------------|--------|
| 行为 | 规则选 tension → 映射 Debate → implication/scenario | 同 Input/Output schema；校验失败降级 grounded |
| 声明 | `grounded_is_not_autonomous=true` | `analyst_mode=openai`，仍禁止契约外事实 |
| 本轮审计 | **已跑 600519** | 未作为主审计样本（无强制要求联网） |

---

## 6. Scorecard（1–5）

| 维度 | 分 | 说明 |
|------|---:|------|
| 1. Analytical Depth | **3** | 有优先级与条件判断；非深度涌现 |
| 2. Analytical Increment | **4** | 相对 Research 有明确升维 |
| 3. Evidence Grounding | **4** | FACT/INFERENCE 可追溯 |
| 4. Evidence Preservation | **4** | 关键数字保留在 executive |
| 5. Fact / Inference Separation | **3** | 结构有；FACT 锚点偏机械 |
| 6. Uncertainty Preservation | **4** | gaps / unresolved 继承 |
| 7. Scenario Quality | **3** | 条件化合格；句式模板化 |
| 8. Debate Consumption | **3** | 链路齐全；消解深度中等 |
| 9. Traceability | **4** | canonical + evidence + debate_refs |
| 10. Non-Redundancy | **4** | 未克隆 canonical 全文 |

**均分约 3.6**；硬质量项无 <3。

---

## 7. 诚实问题清单（不美化）

1. Grounded FA **可预判** implication 句式；不能称为自主分析。  
2. `bull_interpretation` / `bear_interpretation` 目前直接复用 Debate claim 文本——这是**引用**，不是二次升维；升维主要在 `current_assessment` / executive。  
3. OpenAI 模式未做真人抽检；仅有降级与 schema 约束。  
4. FA 仍依赖 Research 已选中的 tension；若 Research 漏张力，FA 不会“发现”新张力（符合设计，但是能力边界）。

---

## 8. GO / NO-GO

### 门槛式问题

**FA 是否只是更漂亮地重新总结 Research？** → **否。**  
有解释优先级、条件 Scenario、Debate 未决继承、改口条件；且禁止全文复述。

**是否具备作为 Pipeline 最后一层 MVP 的资格？** → **是。**

# 最终判定：**GO（MVP）**

边界：

- GO 的是「可追溯、有增量、契约正确的 Final Analyst 第一版」。  
- **不是** GO「Grounded = 高质量自主投研」。  
- 下一阶段若要提高 Analytical Depth，应优先强化 Debate 消解质量与 OpenAI 模式下的严格校验，而不是再堆 Research finding。

---

*End of Final Analyst First Audit — GO (MVP), grounded ≠ autonomous.*
