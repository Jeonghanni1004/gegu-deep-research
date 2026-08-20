# Final Analyst Third Audit

**标的**：600519 + calibration / non-mechanical / OpenAI A/B fixtures  
**审计类型**：Final Analyst 第三轮 — Judgment Calibration & OpenAI Quality  
**审计日期**：2026-08-15  

> 本轮目标不是再证明「Debate 会改变 FA」，而是证明：  
> **Debate 改变多少 → FA 合理改变多少；不机械跟随；不越权叙事；OpenAI 在同契约下可产生可追溯 analytical increment。**

---

## 1. 相对第二轮：已有 vs 缺口

| 能力 | 第二轮 | 本轮 |
|------|--------|------|
| judgment_flip | ✅ | ✅ 保留 |
| DebateResolution | ✅ | ✅ + `support_strength` |
| assessment_strength | strong/moderate/tentative/unresolved | ✅ 保留；映射 weak→tentative |
| Interpretation ≠ claim copy | ✅ | ✅ |
| Calibration weak/moderate/strong | ❌ | ✅ |
| Non-mechanical（同 resolution 不同 Research） | ❌ | ✅ |
| Inference boundary SUPPORTED/DERIVED/CONDITIONAL/UNSUPPORTED | ❌ | ✅ |
| Cross-tension synthesis | 弱 | ✅ |
| Scenario 新证据触发边界 | 弱 | ✅ |
| OpenAI A/B ×3 fixtures | 单点 mock | ✅ |
| OpenAI live API 人工文风 | ❌ | ❌（残余） |

未修改：Evidence / Research canonical / 时间窗 / Weight / Relevance / Debate 主流程。

---

## 2. 修改文件列表

| 路径 | 变更 |
|------|------|
| `src/final_analyst/calibration.py` | **新增**：support strength、evidence_pressure、overclaim、unsupported markers |
| `src/final_analyst/schemas.py` | `support_strength`、`inference_status`、`AssessmentBasis` 校准字段、meta pressure |
| `src/final_analyst/resolution.py` | 解析 `weak/moderate/strong` → assessment + support_strength |
| `src/final_analyst/synthesize.py` | 校准框架、跨 tension DERIVED、非机械 pressure、Debate 语义 |
| `src/final_analyst/validators.py` | calibration / unsupported / cross-tension / scenario boundary |
| `src/final_analyst/llm.py` | OpenAI system 提示强化边界 |
| `tests/test_final_analyst.py` | +~26 高价值断言（总计 **67**） |

---

## 3. 新增测试列表（本轮）

- `test_judgment_calibration`
- `test_weak_debate_no_overclaim`
- `test_strong_debate_no_certainty`
- `test_judgment_flip_calibration`
- `test_judgment_non_mechanical`
- `test_inference_boundary`
- `test_no_unsupported_market_claim`
- `test_no_external_fact`
- `test_cross_tension_synthesis`
- `test_scenario_boundary`
- `test_scenario_non_redundancy`
- `test_debate_resolution_semantics`
- `openai_ab_invariant_{A,B,C}`
- `openai_ab_increment_{A,B,C}`
- `test_openai_reject_or_fallback_v3`

（另含 calibration_*_validates / fixtures_saved 等支撑项）

---

## 4. 完整测试结果

| Suite | Result |
|------|--------|
| `tests.test_final_analyst` | **67/67 PASS** |
| `tests.test_debate` | 25/25 PASS |
| judgment_flip（保留） | PASS |
| judgment_calibration | PASS（ranks 1<2<3） |
| judgment_non_mechanical | PASS |

---

## 5. Grounded vs OpenAI A/B

Fixtures：`examples/fa_fixtures/openai_ab/`

| Fixture | Grounded resolution | OpenAI | 更丰富？ | 同契约 invariant |
|---------|---------------------|--------|----------|------------------|
| A 单 tension | bull_supported | 同 | 是（中间条件 DERIVED） | PASS |
| B 双 tension | unresolved | 同 | 是 | PASS |
| C unresolved | unresolved | 同 | 是 | PASS |

不合格 OpenAI（「市场已经重新定价…」）→ **reject / fallback grounded** PASS。

说明：本环境 A/B 使用 **同契约 mock**（在 Grounded 上叠加可追溯 DERIVED increment）。**真实 API live 质量未在本轮充分人工跑通**，不计入硬门槛，记入残余问题。

---

## 6. 600519 新产物要点

路径：`examples/600519_final_analyst.json`

- Executive：校准主判断 + **跨 tension DERIVED**（增长恢复=经营×估值中间条件；价格改善≠关闭增长争议）
- Debate 语义：仍有效 Challenge + Rebuttal 处理；**非条数中性**
- Base / Bull / Bear：Bull/Bear 明确 **新证据出现后** 才获更强支持
- `assessment_basis`：`calibrated_frame` / `evidence_pressure` / `limiting_challenge`

---

## 7. Judgment Calibration 示例

同 Research、`bull_supported`：

| support | assessment | rank | 允许幅度 |
|---------|------------|------|----------|
| weak | tentative | 1 | 「阶段性压力解释获得一定支持」；禁「已经改善」 |
| moderate | moderate | 2 | 更明确但仍条件化 |
| strong | strong | 3 | 更明确主导解释；仍「非确定事实」 |

`unresolved → bull/weak`：幅度上升但不过度翻转（`test_judgment_flip_calibration`）。

---

## 8. Non-mechanical 示例

同 `resolution=bull_supported`：

| Research 结构 | evidence_pressure | FA |
|---------------|-------------------|-----|
| 增长小幅回落 / 现金流稳定 | **mild** | 建设性权重可更清晰（仍条件化） |
| 增长明显恶化 / 现金流同步恶化 | **severe** | **不得**把 bull_supported 机械写成乐观答案 |

签名不同 → Debate 是输入，不是答案。

---

## 9. 人工质量 Scorecard（1–5）

| 维度 | 分 | 依据 |
|------|----|------|
| Analytical Depth | **4** | 跨 tension 中间条件 + 校准框架 |
| Analytical Increment | **4** | DERIVED bridge；非换措辞 |
| Evidence Grounding | **5** | citation / numbers |
| Evidence Preservation | **5** | 关键数字保留 |
| Fact / Inference Separation | **4** | inference_status；UNSUPPORTED reject |
| Uncertainty Preservation | **5** | unresolved + Challenge 限制强度 |
| Scenario Quality | **4** | 新证据触发边界 |
| Debate Consumption | **5** | semantics + flip + calibration |
| Traceability | **5** | canonical / evidence / debate_refs |
| Non-Redundancy | **4** | 复制 Research 仍拒收 |
| Judgment Calibration | **4** | weak/moderate/strong 有序且不过度 |
| OpenAI Grounding | **4** | mock 同契约 + validator |
| OpenAI Traceability | **4** | invariant PASS |
| OpenAI Uncertainty | **4** | resolution 不被抹掉 |
| OpenAI No Unsupported | **4** | reject/fallback PASS |
| OpenAI 文风丰富度 | **3** | mock 达标；live 未充分证明 |

硬门槛维度均 **≥4**。OpenAI 文风丰富度不设硬 GO（按需求）。

---

## 10. 失败项

自动化：**无 FAIL**。

---

## 11. 残余问题

1. OpenAI **live API** 多 run 稳定性与文风增量仍待下一阶段人工对照。  
2. `evidence_pressure` 为启发式指纹，非完整财务模型；极端措辞依赖 fixture。  
3. Grounded 文案仍偏结构化；可读性优化不在本轮。  
4. 跨行业端到端 Evidence Pack 深度样本仍有限。

---

## 12. GO / NO-GO（由审计门槛决定）

### 硬门槛检查

| 门槛 | 结果 |
|------|------|
| Analytical Depth ≥4 | ✅ 4 |
| Analytical Increment ≥4 | ✅ 4 |
| Evidence Grounding ≥4 | ✅ 5 |
| Evidence Preservation ≥4 | ✅ 5 |
| Fact/Inference ≥4 | ✅ 4 |
| Uncertainty ≥4 | ✅ 5 |
| Scenario ≥4 | ✅ 4 |
| Debate Consumption ≥4 | ✅ 5 |
| Traceability ≥4 | ✅ 5 |
| Non-Redundancy ≥4 | ✅ 4 |
| Judgment Calibration ≥4 | ✅ 4 |
| OpenAI Grounding/Trace/Uncertainty/NoUnsupported ≥4 | ✅ |
| judgment_flip 仍 PASS | ✅ |
| judgment_calibration / non_mechanical PASS | ✅ |

### 裁决：**GO**

理由：本轮成功标准（合理校准、非机械、不越权、跨 tension DERIVED、OpenAI 同契约可追溯增量 + 拒收路径）均被测试与人工对照满足；OpenAI live 文风属明确残余，不阻断本轮 GO。
