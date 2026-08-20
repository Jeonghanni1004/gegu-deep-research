# Final Analyst Seventh Audit — Live Reliability & Judgment Stability Hardening

**审计日期**：2026-08-17  
**范围**：针对 Round-6 DeepSeek 10×10 失败，提升 OpenAI success / JudgmentFrame 稳定性  
**Provider（live）**：DeepSeek `deepseek-v4-flash`（thinking disabled）  
**原则**：不降 Production Gate；不把 fallback 算 openai success；不放宽 JudgmentFrame acceptable；不恢复 phrase seal / scrub-as-PASS

---

## 1. 裁决

### **GO — Production Ready with Reliability Risk**

| 门槛 | 目标 | Round-6 | Round-7 | 结果 |
|------|------|---------|---------|------|
| Judgment acceptable | ≥80% | 60% | **100%**（100/100） | **PASS** |
| OpenAI success | ≥90% | 54% | **89%**（89/100） | **未达严格 90%** |
| unsupported_external_fact | 0 | 0 | **0** | PASS |
| information_loss | 0 | 0 | **0** | PASS |
| contract_violation | 0 | 0 | **0** | PASS |
| reject | 极低 | 0 | **0** | PASS |
| debate_state_drift | 0 | 10/10 fixture 混乱 | **0** | PASS |
| primary_axis_drift | 0 | 普遍 | **0** | PASS |

按第六轮明文放宽条件：

> OpenAI success &lt;90%，但 acceptable≥80%，且硬安全项为 0，fallback 安全  
> → **GO — Production Ready with Reliability Risk**

本轮适用该裁决（openai **89%**，acceptable **100%**）。

---

## 2. Round-6 → Round-7 问题变化

| 问题 | Round-6 | Round-7 |
|------|---------|---------|
| OpenAI success | 54% | **89%**（+35pp） |
| Fallback rate | 46% | **11%** |
| Acceptable | 60% | **100%** |
| Judgment drift（fixture） | 10/10 | **0** |
| debate_state 翻转 | 普遍（openai vs fallback） | **0** |
| consumer → volume_vs_margin 误伤 | 是 | **已消除**（structure-first） |
| 硬安全三项 | 0 | **0** |

诊断原文：`examples/evaluation/round7_failure_diagnosis.json`

---

## 3. Failure taxonomy 分布（10×10 openai）

文件：`examples/evaluation/stability_10x10_openai_r7.json`

| 指标 | 值 |
|------|-----|
| openai_success | 89 |
| grounded_fallback | 11 |
| failure_codes_before_fallback | `PROVIDER_FAILURE`: 11 |
| repair（成功 openai 路径） | 89 |
| reject | 0 |

说明：11 次 fallback 的 notes 经 taxonomy 归入 `PROVIDER_FAILURE`（含 validation/repair/API 综合失败串）。**未**出现 information_loss / unsupported_external_fact / contract_violation。

---

## 4. unresolved_numbers 根因（已确认）

1. **主因**：LLM 写出不在 `ALLOWED_NUMBERS` / `numbers_preserved` 中的数字。  
2. **次因**：小数截断/改写导致 token_map miss（已加强 truncation soft-match，但禁止短 truncation 误匹配发明数字）。  
3. **非误杀**：真正发明的数字（如测试用 `99.99123%`）必须 REGENERATE，不得 PASS。

**修复**：

- Prompt 增加 `ALLOWED_NUMBERS` + 禁止自造比率  
- 失败后 **1 次 regenerate-with-feedback**（仍禁止 scrub PASS）  
- citation Level-1/2 repair 优先补 evidence_ids

---

## 5. Schema failure 根因

DeepSeek 常见：`evidence_ids` 单值、`null` 字符串、scenario label 别名、缺省 optional list。

**修复**：`_sanitize_llm_json` 增强（scalar→list、empty optional、label alias），并写入 `sanitizer_action=...` notes。  
**约束**：不创造 evidence / 不创造事实。

---

## 6. Citation repair 成功率（定性）

- Round-6：repair 后仍大量 unresolved → fallback  
- Round-7：成功 openai 路径 `evidence_repair_action=REPAIR` 计数 **89**；fallback 降至 11%  
- 单元：`r7_unresolved_numbers_repair` / `r7_unresolved_numbers_reject_or_regenerate` PASS

---

## 7–12. Live / Frame 指标

| # | 指标 | Round-7 |
|---|------|---------|
| 7 | OpenAI success | **89%** |
| 8 | fallback rate | **11%** |
| 9 | acceptable rate | **100%** |
| 10 | JudgmentFrame drift | **0** |
| 11 | assessment drift（&gt;2 档） | **0**（E04/E09 允许 moderate↔strong 同校准带） |
| 12 | primary_axis drift | **0** |
| — | debate_state drift | **0** |

---

## 13–15. 硬安全

| 指标 | 值 |
|------|-----|
| information_loss | **0** |
| unsupported_external_fact | **0** |
| contract_violation | **0** |

---

## 16–17. Stability 正式跑

### Grounded 10×10

`examples/evaluation/stability_10x10_grounded.json`

| 指标 | 值 |
|------|-----|
| acceptable | **100%** |
| judgment_drift | **0** |
| hard zeros | **0/0/0** |

### OpenAI 10×10

`FA_LIVE=1 FA_BENCH_FIXTURES=10 FA_BENCH_RUNS=10 python scripts/run_openai_stability_10x10.py`  
产物：`examples/evaluation/stability_10x10_openai_r7.json`

| 指标 | Round-6 | Round-7 |
|------|---------|---------|
| openai_success | 54% | **89%** |
| acceptable | 60% | **100%** |
| fallback | 46% | **11%** |
| debate_state_drift | 高 | **0** |
| primary_axis_drift | 高 | **0** |

---

## 18. 测试结果

| Suite | Result |
|------|--------|
| `tests.test_final_analyst` | **67/67 PASS** |
| `tests.test_final_analyst_round5` | **41/41 PASS**（live 3/3 openai success 样本） |
| `tests.test_final_analyst_e2e` | **13/13 PASS** |
| `tests.test_final_analyst_evaluation` | **43/43 PASS** |
| `tests.test_final_analyst_round7` | **23/23 PASS** |

Benchmark 阈值：**未放宽**（`compare_judgment_frame` score≥0.7 / debate_state 硬否决保持不变）。

---

## 19. Failure Before Repair vs After Repair

| 阶段 | Round-6 行为 | Round-7 行为 |
|------|--------------|--------------|
| Before Repair | LLM JSON 常过 schema，但含未 grounding 数字 / 改写 resolution | 同左，但有 ALLOWED_NUMBERS + FIXED_DEBATE_CONTRACT |
| After Repair | 无法匹配 → 直接 raise → fallback（46%） | 可匹配 → REPAIR；不可匹配 → **一次 regenerate**；仍失败 → fallback（11%）并记 taxonomy |
| After Contract Pin | LLM 可改写 debate_state → JudgmentFrame drift | **pin_debate_contract** 强制 INPUT resolution → debate_state_drift=0 |
| After Axis Extract | 关键词「毛利率」→ volume_vs_margin 误伤 | **structure-first**（PROFIT_VS_GROWTH / VOLUME_VS_MARGIN / SEMI_UTIL） |

---

## 20. 残余风险

1. OpenAI success **89% &lt; 90%**：剩余 11% 仍走 grounded fallback（可靠性风险）。  
2. Provider/validation 偶发失败仍存在（taxonomy 记为 PROVIDER_FAILURE）。  
3. Assessment 在 strong 边界上可有 moderate↔strong 波动（校准矩阵内，非 debate_state 翻转）。  
4. Evidence Repair Level-3（搜索新 evidence）仍未做。  
5. 未把 fallback 计为 openai success；若未来要冲严格 90%，需继续压 provider/repair 失败，而不是改门槛。

---

## 21. 核心修复文件

| 路径 | 作用 |
|------|------|
| `src/final_analyst/contract_pin.py` | **新增** Debate resolution / support / pressure 钉死为 INPUT 合约 |
| `src/final_analyst/judgment_frame.py` | structure-first primary_axis；可选 inp；**不放宽** compare |
| `src/final_analyst/llm.py` | pin + calibrate；1× regenerate；sanitizer 增强与 audit notes |
| `src/final_analyst/live_prompt.py` | ALLOWED_NUMBERS / FIXED_DEBATE_CONTRACT |
| `src/final_analyst/evidence_repair.py` | 收紧发明数字匹配；保留合法 truncation |
| `src/final_analyst/stability_bench.py` | failure_code 直方图；debate/axis/assessment drift |
| `tests/test_final_analyst_round7.py` | Round-7 回归 |
| `examples/evaluation/round7_failure_diagnosis.json` | 先诊断后改代码的记录 |

**未修改**：Evidence schema/builder、Research canonical、Debate 主流程、Time/Weight/Relevance、FinalAnalystOutput 业务字段、Production Gate 硬安全标准。

---

## 22. 最终一句话

第七轮在**不降低门槛**的前提下，把 Live OpenAI success 从 **54%→89%**、Judgment acceptable 从 **60%→100%**，并消灭 debate_state / primary_axis drift。因 openai success 距 90% 差 1pp，正式裁决为：

### **GO — Production Ready with Reliability Risk**
