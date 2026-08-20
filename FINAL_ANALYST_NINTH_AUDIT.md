# Final Analyst Ninth Audit — Transient Provider Retry (Fail-Closed Numbers)

**审计日期**：2026-08-17  
**基线**：Round-8 正式锁定 `stability_10x10_openai_r8.json`（openai_success **84/100**，acceptable **100%**）  
**原则**：不将未经 grounding 证明的数字改写视为 repair；不冲 90% 而放宽安全边界

---

## 0. 一句话结论

> Round-9 不将合法但未经 grounding 证明的数字改写视为 repair opportunity；`1347.1280 → 1347.13` 被保留为 fail-closed。唯一实施的是低风险的 transient provider retry 加固。

**最终裁决（本轮，无新正式 10×10）**：**GO — Production Ready with Reliability Risk**（继承 R8 正式口径；未宣称 Strict GO）

正式 OpenAI success 仍为 **84%**。禁止写成 92.3%。

---

## 1. E06 三次 failure 的真实原因（诊断确认，未放宽）

| token | 原因 | R9 处理 |
|-------|------|---------|
| `100%` | INPUT 中 **不存在** | 保持 FAIL |
| `1347.13` | 对 `1347.1280` 的 **rounding**，非 truncation | **保持 FAIL**（明确不批准 round 例外） |
| 调用链 | repair → regenerate×1 → 仍 unresolved → fallback | 不变 |

---

## 2–3. `100%` / `1347.13` 是否可安全 repair？False positive 风险？

- `100%`：**不可** repair（无 source）。  
- `1347.1280 → 1347.13`：**不**视为安全 repair（改变数字序列；多 eid 同族）。  
- False positive 风险：若放行 round，可能把改写精度当成 grounded → **已拒绝**。  
- 合法 trailing-zero：仅当 **source 本身是 `1347.13`** 时，`1347.1300` 可通过（既有 soft-match；单测覆盖）。

**`evidence_repair.py`：本轮零修改。**

---

## 4–5. Premature stage 与 retry

- stage / code：`provider` / `PROVIDER_FAILURE`  
- 非 JSON_PARSE  
- **已增加 / 加固**：最多 1× transient retry；成功 → `openai_success` + `retry_used=true` + `provider_retry_recovered=true` + 保留 `provider_retry_first_error`  
- 失败 → fallback，`retry_used=true`，attribution 保留  
- **402 `PROVIDER_QUOTA_FAILURE`：永不 retry**（显式 guard）

---

## 6. R9 修改了哪些代码

| 文件 | 变更 |
|------|------|
| `src/final_analyst/llm.py` | quota 显式不 retry；retry 成功 audit notes；fallback/error 文件补 attempt/retry/first_error |
| `tests/test_final_analyst_round9.py` | **新增** retry / 402 / E06 fail-closed 回归 |
| `FINAL_ANALYST_NINTH_AUDIT.md` | 本文件 |

未改：`evidence_repair.py`、Gate、JudgmentFrame、contract_pin、axis、ALLOWED_NUMBERS、R8 正式 artifact。

---

## 7. 明确未修改

Evidence schema / Pack Builder / Research / Debate / FA 业务 schema / Production Gate / JudgmentFrame threshold / expected / 90% 定义 / fallback≠success / scrub / phrase seal / R8 `stability_10x10_openai_r8.json`。

---

## 8. 本地测试

| Suite | 结果 |
|-------|------|
| test_final_analyst | 67/67 |
| round5 | 41/41 |
| e2e | 13/13 |
| evaluation | 43/43 |
| round7 | 23/23 |
| round8 | 32/32 |
| **round9** | **16/16** |

---

## 9. 5×2 live 诊断（已完成）

| 指标 | 结果 |
|------|------|
| total_runs | 10 |
| openai_success | **10/10** |
| fallback | **0** |
| regenerate（成功路径中曾用） | 1 |
| retry | 0 |
| 402 / quota | **0** |
| evidence/repair/validation/json/schema failure | **0** |
| acceptable | **10/10** |
| drift / hard safety | **全 0** |

产物：

- `examples/evaluation/stability_5x2_openai_r9_diag.json`
- `examples/evaluation/round9_failure_diagnosis_5x2.json`

**解读**：无 regression；额度健康时小样本干净。  
**正式 10×10**：仍不默认执行——需确认额度足够、单进程、独立写入 `stability_10x10_openai_r9_final.json` 后再议。

---

## 10. 正式 10×10

**本轮未跑。**  
理由：R9 不把冲 90% 作为默认目标；R8 已证明额度不足会 402 污染；仅在额度充足、单进程、写入独立 `stability_10x10_openai_r9_final.json`（不覆盖 R8）时再裁决。

---

## 11–17. 正式指标（继承 R8 锁定）

| 项 | 值 |
|----|-----|
| openai_success（正式） | **84%**（R8 locked） |
| acceptable | **100%** |
| fallback（R8） | 16（含 9×402） |
| JudgmentFrame / debate_state / primary_axis drift | **0** |
| hard safety | **0** |
| Strict GO | **否**（84% &lt; 90%） |

---

## 18. 最终裁决

**GO — Production Ready with Reliability Risk**

未达到 Strict GO，因为正式 OpenAI success &lt; 90%（锁定 84%）。  
R9 仅降低 transient transport 类失败的残留风险；**不**通过数字 round 或改统计口径抬高 success。
