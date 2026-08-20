# Final Analyst Eighth Audit — Failure Attribution & Reliability Diagnosis

**审计日期**：2026-08-17（更新：正式 84% 锁定 + 16 失败拆解 + quota 分离）  
**范围**：解释 Round-8 正式 84% 的失败来源；低成本定位；不默认重跑正式 10×10  
**Provider**：DeepSeek `deepseek-v4-flash`  
**原则**：先保证实验可信；不改 Gate / Benchmark / fallback 定义制造 90%

---

## 0. 正式结果锁定（不可覆盖）

| Artifact | 状态 |
|----------|------|
| `examples/evaluation/stability_10x10_openai_r8.json` | **正式 Round-8**：openai_success **84/100** |
| `examples/evaluation/stability_10x10_openai_r8_quota_exhaust.json` | **作废**（32% 额度耗尽二次跑） |
| `examples/evaluation/stability_10x10_grounded.json` | Grounded baseline：**100/100 acceptable** |
| `examples/evaluation/round8_failure_diagnosis_formal84.json` | 正式 16 失败离线重分类锁定 |
| `examples/evaluation/round8_failed_runs_formal84.json` | 16 条失败明细 |
| `examples/evaluation/round8_failure_diagnosis.json` | 与 formal84 同步（诊断主文件） |

**禁止**：用 32% quota 跑覆盖正式 84%。  
**禁止**：默认再跑正式 10×10。脚本已拒绝写入 `stability_10x10_openai_r8.json`；新结果写 `*_r8_final.json` / `*_5x2_*`。

---

## 1. 正式裁决（基于锁定 84/100）

### **GO — Production Ready with Reliability Risk**

| 门槛 | 目标 | 正式 R8 | 结果 |
|------|------|---------|------|
| openai_success | ≥90% | **84%**（84/100） | 未达 Strict（差 6pp） |
| acceptable | ≥80% | **100%** | PASS |
| information_loss | 0 | **0** | PASS |
| unsupported_external_fact（gate） | 0 | **0** | PASS |
| contract_violation | 0 | **0** | PASS |
| debate_state_drift | 0 | **0** | PASS |
| primary_axis_drift | 0 | **0** | PASS |
| reject | 极低 | **0** | PASS |

Grounded baseline：acceptable **100/100**。

---

## 2. 核心问题：16% 到底是什么？

**Attribution 可信：否，并非 16× PROVIDER_FAILURE。**

离线按 `cause` 重分类（`PROVIDER_QUOTA_FAILURE` 已从普通 provider 拆出）：

| failure_code | 次数 | 占比（/16） | 性质 |
|--------------|------|-------------|------|
| **PROVIDER_QUOTA_FAILURE** | **9** | 56% | HTTP **402 Payment Required**（额度） |
| **UNSUPPORTED_EXTERNAL_FACT** | **3** | 19% | `fabricated_evidence_hint`（校验 fail-closed） |
| **EVIDENCE_REPAIR_FAILURE** | **3** | 19% | `unresolved_numbers`（含 `100%` / `1347.13`） |
| **PROVIDER_FAILURE** | **1** | 6% | `Response ended prematurely` |
| VALIDATION_FAILURE | 0 | — | — |
| JSON_PARSE_FAILURE | 0 | — | — |
| SCHEMA_SANITIZATION_FAILURE | 0 | — | — |

### 分桶回答

| 问题 | 答案 |
|------|------|
| 真正 Provider/API（非额度） | **1**（premature） |
| Quota / 402 | **9**（单独记 `PROVIDER_QUOTA_FAILURE`） |
| Validation（可恢复类） | **0** |
| Unsupported / fabricated | **3**（安全拦截，不应 regenerate） |
| Evidence repair | **3** |
| JSON | **0** |
| Schema | **0** |

### 正式计数（锁定 JSON 顶栏）

| 指标 | 值 |
|------|-----|
| fallback | 16 |
| regenerate（note） | 16 |
| retry | 0 |
| repair（成功 openai 路径 REPAIR note） | 84 |
| openai_success | 84（**不因排除 402 而改写**） |

叙事参考（**不重新定义** success）：排除 9 次 402 后，剩余 91 run 中成功 84 → ≈**92.3%**；剩余软件失败 **7**（3 fabricated + 3 repair + 1 premature）。

---

## 3. 16 条失败明细（按原因排序）

完整列表：`round8_failed_runs_formal84.json`

### A. PROVIDER_QUOTA_FAILURE（9）— 全部 E10 run 2–10

`402 Client Error: Payment Required`  
→ **不 retry**；fallback；openai_success=false  
→ **污染正式 success，不是模型能力问题**

### B. UNSUPPORTED_EXTERNAL_FACT（3）

| fixture | run | cause 摘要 |
|---------|-----|------------|
| E05 | 1 | fabricated_evidence_hint … `akshare_fact_600519_...` |
| E07 | 4 | fabricated_evidence_hint … `derived_derived_600519_...` |
| E09 | 8 | fabricated_evidence_hint … `derived_derived_600519_...` |

`pack=None` 时仅允许 INPUT 表面可见 evidence_ids；模型挂了输入外 id → **正确 fail-closed**。  
已从 recoverable validation whitelist **排除**（禁止 regenerate 绕过）。

### C. EVIDENCE_REPAIR_FAILURE（3）— 全部 E06

| run | unresolved |
|-----|------------|
| 4 | `100%` |
| 6 | `100%` |
| 10 | `1347.13,100%` |

1× regenerate 后仍失败；**禁止** scrub / 扩 ALLOWED_NUMBERS / 造数字。

### D. PROVIDER_FAILURE（1）

E01#8：`Response ended prematurely`（连接中断类；属 transient，允许最多 1× retry；本跑 retry=0 可能发生在 retry 逻辑强化前）。

---

## 4. Quota 污染结论

1. 正式 84% **含** 9×402；后半段 E10 被额度打穿。  
2. 后续完整 32% 跑 = **作废**，不得覆盖正式 artifact。  
3. 402 ≠ 普通 provider reliability；taxonomy 新增 **`PROVIDER_QUOTA_FAILURE`**（与 `PROVIDER_FAILURE` 兼容并列）。  
4. **不对 402 做 retry**。

---

## 5. Failure Attribution 机制

已确认 wrapper `openai_rejected_or_failed_fallback_grounded` **不再**吞真实 code。  
结构化 `failure_attribution=` + `classify_from_notes` 优先。  
单测：`tests/test_final_analyst_round8.py` **32/32**；既有套件全 PASS。

---

## 6. 本轮具体修复（相对“再猜着修”）

1. 锁定正式 84% / 作废 32%  
2. 新增 `PROVIDER_QUOTA_FAILURE` + `is_quota_provider_failure`；402 不 retry  
3. `fabricated_evidence*` 不可 regenerate  
4. 离线重分类正式 16 失败 → diagnosis / failed_runs  
5. 稳定性脚本禁止覆盖 `stability_10x10_openai_r8.json`；输出 `*_final` / `FA_BENCH_OUT`  
6. `FA_DIAG_OUT` 避免 live 诊断覆盖 formal84 diagnosis  

**未改**：Production Gate、JudgmentFrame 0.7、expected、contract_pin、structure-first axis、ALLOWED_NUMBERS 边界、scrub、phrase seal。

---

## 7. 低成本 5×2 live diagnostic（已跑）

规格：`FA_BENCH_FIXTURES=5 FA_BENCH_RUNS=2`，单进程。

| 指标 | 结果 |
|------|------|
| total_runs | 10 |
| openai_success | **10/10（100%）** |
| fallback | 0 |
| 402 / quota | **0** |
| validation / repair / JSON / schema | **0** |
| regenerate / retry | 0 / 0 |
| acceptable | **10/10** |
| drift / 硬安全 | **全 0** |

产物：

- `examples/evaluation/stability_5x2_openai_r8_diag.json`
- `examples/evaluation/round8_failure_diagnosis_5x2.json`

**解读**：额度恢复后，小样本路径健康；正式 84% 的主污染源（E10 尾段 402）与偶发 fabricated/repair 在 5×2 未复现。  
**仍不**据此宣称 Strict GO；正式再裁决需完整 10×10 → `stability_10x10_openai_r8_final.json`（且中途 402 则整次作废）。

---

## 8. 剩余根因与下一步（仍不默认 10×10）

| 根因 | 建议 |
|------|------|
| 402 quota | 额度充足 + 单进程；正式写 `stability_10x10_openai_r8_final.json` |
| fabricated_evidence_hint | prompt 强调仅用 INPUT evidence_ids；保持 fail-closed |
| unresolved_numbers（E06） | 加强 regenerate feedback；不扩 ALLOWED_NUMBERS |
| premature disconnect | 已纳入 transient 1× retry |

正式再裁决条件：quota 足够、attribution 正确、本地测试 PASS、明确准备写 `*_r8_final.json`、中途 402 则**整次作废**。

---

## 9. 二十问（锁定口径）

1. 正式 OpenAI success = **84%**  
2. 正式样本 = **100**  
3. 后续 32% = **作废**  
4. 真实分布 = §2 表  
5. quota 是否污染 = **是（9/16）**  
6. retry = **0**（正式跑）  
7. regenerate = **16**（note 计数）  
8. repair = **84**  
9. fallback = **16**  
10. acceptable = **100%**  
11–13. Judgment / debate_state / primary_axis drift = **0**  
14–16. information_loss / unsupported(gate) / contract = **0**  
17. grounded baseline = **100/100 acceptable**  
18. 本轮修复 = §6  
19. 剩余根因 = §8  
20. 裁决 = **GO — Production Ready with Reliability Risk**（非 Strict GO；不降低 90% 门槛）
