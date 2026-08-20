# Final Analyst Second Audit

**标的**：600519（贵州茅台）+ Debate Flip fixtures + 跨行业结构样本  
**审计类型**：Final Analyst 第二轮 — Analytical Quality Upgrade  
**审计日期**：2026-08-15  
**模式**：`grounded`（主路径）+ `openai`（同契约 mock A/B + 失败降级）

> 核心命题：Final Analyst 不是 Research + Debate 的结构化摘要器；其判断必须随 Challenge / Rebuttal / Debate resolution 有理由地变化。

---

## 1. Test Status

| Suite | Result |
|------|--------|
| `tests.test_final_analyst` | **41/41 PASS** |
| `tests.test_debate` | 25/25 PASS |
| `tests.test_research_agents` | 30/30 PASS |
| `tests.test_research_stability` | 62/62 PASS |
| **`judgment_flip`** | **PASS（硬门槛）** |

本轮关键新增断言（节选）：

- `test_judgment_flip` / `judgment_flip_signatures_differ`
- `test_debate_resolution_changes_assessment`
- `test_challenge_blocks_overclaim`
- `test_rebuttal_changes_assessment`
- `test_interpretation_not_claim_copy`
- `test_base_case_selection` / `test_assessment_strength`
- `test_scenario_variable_link` / `test_scenario_explanation_shift`
- `test_openai_*`（same_contract / traceability / no_external_fact / quality_floor / fallback）
- `test_analytical_increment_v2` / `test_bull_bear_not_mechanical_balance`

---

## 2. 本轮修改

### 新增 / 重写（均在 `src/final_analyst/`）

| 路径 | 说明 |
|------|------|
| `schemas.py` | `DebateResolution`、`AssessmentBasis`、`assessment_strength`、`bull/bear_reference`、Scenario `explanation_shift_variable` |
| `resolution.py` | Challenge/Rebuttal → `DebateResolution`（禁止按 claim 条数机械中性） |
| `synthesize.py` | Debate-driven executive / Base / Scenario / interpretation 重写 |
| `validators.py` | v2 质量门：interpretation 非 claim 复制、Base 选择、flip 签名、OpenAI 契约等 |
| `llm.py` / `agent.py` | OpenAI 不合格 → 拒收或降级 grounded |

### 测试与产物

| 路径 | 说明 |
|------|------|
| `tests/test_final_analyst.py` | 扩展至 **41** 项 |
| `examples/600519_final_analyst.json` | 真实 grounded 产出 |
| `examples/fa_fixtures/debate_flip_*.json` | unresolved / bull / bear |
| `examples/fa_fixtures/grounded_vs_openai.json` | A/B 对照 |

### 未修改（边界遵守）

Evidence schema / Pack / Research canonical / relevance / weight / PIT 窗口 / Retriever / Embedding / Vector DB / Debate 主流程（claims→challenges→rebuttals）/ `ResearchOutputContract` 核心结构。

**未**通过增加 Research finding 数量“堆深度”。

---

## 3. Research → Debate → FA 数据流

```
Research Canonical (tension / finding)
        ↓
Bull / Bear claims（canonical_finding_ids）
        ↓
Challenge → Rebuttal
        ↓
DebateResolution（FA 内部）
  resolution ∈ {bull_supported, bear_supported, partially_resolved, unresolved}
  assessment_strength ∈ {strong, moderate, tentative, unresolved}
        ↓
Final Analyst Assessment + assessment_basis
        ↓
Base / Bull / Bear Scenario（explanation_shift_variable）
        ↓
What Would Change（可验证触发）
```

禁止路径：`Research → Tension → 直接写 FA conclusion`（无 Debate resolution）。

---

## 4. Debate Resolution 示例（600519 实盘）

`TENSION_FUND_PROFIT_VS_GROWTH`：

| 字段 | 值 |
|------|-----|
| bull_position | 盈利韧性（ROE/毛利率） |
| bear_position | 增速承压削弱增长叙事 |
| unresolved_challenges | `CH_BULL_01`, `CH_BEAR_01` |
| partially_accepted_rebuttals | `RB_BULL_01`, `RB_BEAR_01` |
| **resolution** | **unresolved** |
| **assessment_strength** | **tentative** |
| resolution_reason | interpretation_conflict 未关闭 + partially_accept → 不能机械平均，只能保留未决 |

Interpretation（非 claim 原文）：

- Bull：**若**增长压力主要来自阶段性因素，**则**高盈利缓冲仍可约束“崩塌”叙事；但 resolution=unresolved，该解释仅为条件假设。
- Bear：**若**同比反映更持久压力，**则**增长不确定性应主导框架；单期同比升级为结构性仍受 Challenge 约束。

---

## 5. Judgment Flip 示例（同 Research，改 Debate）

同一 Research canonical（`TENSION_FUND_PROFIT_VS_GROWTH`），仅改 Debate metadata / Challenge-Rebuttal 驱动的 resolution：

| Fixture | primary_resolution | assessment_strength | Base 核心 |
|---------|-------------------|---------------------|-----------|
| A unresolved | unresolved | unresolved | 事实清楚、解释框架**无法裁定**（非“两边都有理所以中性”） |
| B bull_supported | bull_supported | moderate | 主解释：**增长压力尚未被证伪为结构性、盈利缓冲仍有效** |
| C bear_supported | bear_supported | moderate | 主解释：**增长不确定性应主导、估值恢复门槛提高** |

**三个 judgment signature 互不相同** → `test_judgment_flip` PASS。

关键问题回答：

> 如果删除 Debate，FA 是否仍给出完全相同结论？

**否。** Executive 明确写入：删除 Debate 将无法得到该未决/单边裁定；Base Case 文本与 `assessment_strength` 随 resolution 切换。

---

## 6. Research vs FA 对照

| Research | FA（本轮） | 升维？ |
|----------|------------|--------|
| 高 ROE × 增长承压并存（事实关系） | 选择解释框架：当前 **unresolved / tentative**，不以 claim 条数中性化 | 是 |
| Debate claim 文本 | `bull_reference` / `bear_reference` 仅作指针；interpretation 重写含义 | 是 |
| unresolved issues 列表 | 进入 `debate_resolution` + `uncertainty` + what-would-change | 消费，非丢弃 |
| 估值×增长 tension | Scenario 绑定可验证变量（多期同比方向），非“涨→Bull / 跌→Bear”空话 | 是 |

---

## 7. Grounded vs OpenAI 对照

| 维度 | Grounded | OpenAI（同契约 mock） |
|------|----------|----------------------|
| Input Contract | `FinalAnalystInput` | 同一 |
| 读 raw EvidencePack | 否（校验可用 pack） | 否 |
| primary_resolution | unresolved | unresolved（quality floor） |
| 外源事实 / BUY | 无 | 不合格样例触发 **fallback → grounded** |
| analytical floor | baseline | 至少不低于 grounded resolution；允许同契约丰富表述 |

产物：`examples/fa_fixtures/grounded_vs_openai.json`  
说明：本环境以 **mock + validator + fallback** 证明契约与拒收路径；**真实 API 文风丰富度**仍属下一阶段优化项（见残余问题）。

---

## 8. 人工评分（1–5）

| 维度 | 分 | 说明 |
|------|----|------|
| Analytical Depth | **4** | 条件化解释 + resolution 驱动 Base |
| Analytical Increment | **4** | 非 claim 复制；implication 绑定 unresolved/supported |
| Evidence Grounding | **5** | FACT/数字可追溯 evidence_ids |
| Evidence Preservation | **5** | 关键数字 33.65% / 91.18% / 4.53% / 1.21% 保留 |
| Fact / Inference Separation | **4** | kind 分层；语言强度受 strength 约束 |
| Uncertainty Preservation | **5** | unresolved 生存；不抹掉 Challenge |
| Scenario Quality | **4** | explanation_shift_variable + 可验证触发 |
| Debate Consumption | **5** | Judgment Flip 证明 Debate 是 judgment driver |
| Traceability | **5** | canonical + evidence + debate_refs |
| Non-Redundancy | **4** | 复制 Research claim 会被 validator 拒收 |
| Judgment Sensitivity | **5** | 仅改 Debate → 核心判断变 |
| OpenAI Quality | **3** | 契约/降级已验证；**live 质量未充分证明** |

硬门槛维度（要求 ≥4）：Depth / Increment / Grounding / Preservation / Debate Consumption / Scenario / Traceability / Uncertainty / Non-Redundancy → **全部 ≥4**。

---

## 9. 失败项

本轮自动化：**无 FAIL**。  
硬门槛：`judgment_flip` **PASS**。

---

## 10. 残余问题

1. Grounded 文案仍偏结构化（可读性/分析师语感可再优化，但不回退到摘要器）。  
2. OpenAI **live** A/B 丰富度与稳定性未在本机 API 上做充分人工对照。  
3. 跨行业样本主要为结构/非白酒规则锁定测试；尚未用完整异行业 Evidence Pack 做端到端深度审计。  
4. `force_resolution` metadata 便于 flip fixture；生产路径应继续以真实 Challenge/Rebuttal 推导为主（当前实盘 600519 已走真实 unresolved 路径）。

---

## 11. GO / NO-GO

### **GO（进入下一阶段：Analytical Depth / OpenAI live quality）**

依据：

1. 41/41 FA 测试 PASS，上游回归未破坏。  
2. **Judgment Flip PASS** — 同 Research、不同 Debate → FA 核心判断实质变化。  
3. Debate Resolution 成为 Base / executive / strength 的驱动，而非 citation 附件。  
4. Interpretation 禁止 claim 原文直出；Scenario 绑定解释框架变化变量。  
5. OpenAI 不合格输出拒收/降级，不静默接受。  
6. 硬门槛人工维度均 ≥4。

**不宣称**：OpenAI live 已达“更强分析师文风”终局；那是下一阶段目标。
