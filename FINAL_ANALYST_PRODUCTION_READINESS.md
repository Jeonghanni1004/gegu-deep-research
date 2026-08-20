# Final Analyst Production Readiness

**日期**：2026-08-18  
**状态**：冻结（Freeze）— 不再进行功能性优化，不再启动 live benchmark

---

## 正式声明

Final Analyst 已达到 Strict GO；R10 正式 10×10 为 94% OpenAI success、100% acceptable，硬安全项及 JudgmentFrame drift 全部为 0。R8 的 84% 作为历史锁定基线保留，不因 R10 改写。

---

## 1. 正式证据（Production Gate）

| 产物 | 角色 | 关键数字 |
|------|------|----------|
| `examples/evaluation/stability_10x10_openai_r10_final.json` | **正式 Production Gate 证据** | 100 runs，openai_success **94**，acceptable **100**，`formal_adjudicable=true` |
| `examples/evaluation/round10_failure_diagnosis.json` | R10 失败归因 | fallback 6；402=0 |
| `examples/evaluation/stability_10x10_openai_r8.json` | **历史锁定基线** | openai_success **84**（禁止改写） |
| `examples/evaluation/round8_failure_diagnosis_formal84.json` | R8 归因锁定 | 16 fallback，含 9×402 |
| `examples/evaluation/round8_failed_runs_formal84.json` | R8 失败明细 | 16 条 |
| `examples/evaluation/stability_10x10_grounded.json` | Grounded baseline | acceptable **100/100** |
| `FINAL_ANALYST_TENTH_AUDIT.md` | R10 审计 | Strict GO |
| `FINAL_ANALYST_NINTH_AUDIT.md` | R9 审计 | retry 加固，未改 repair |
| `FINAL_ANALYST_EIGHTH_AUDIT.md` | R8 审计 | 84% + Reliability Risk |

R10 artifact 自洽校验：

- `total_runs=100`，`incomplete=false`，`aborted_quota=false`
- `openai_success_rate=0.94`，`acceptable_rate=1.0`，`fallback_rate=0.06`
- `locked_r8_success_baseline=84`
- R8 文件仍为 `openai_success=84`，未被覆盖

---

## 2. R8 → R9 → R10 汇总

| 轮次 | 问题 | 修复 | 验证 | 裁决 |
|------|------|------|------|------|
| **R8** | 正式 84%；16 fallback 曾被误标 PROVIDER；含 9×402 | 归因可信化；quota 与真实失败分离；不放宽 Gate | 正式 10×10：84/100，acceptable 100%，drift/硬安全 0 | **GO — Production Ready with Reliability Risk**（锁定 84%） |
| **R9** | 1× premature 可 retry；E06 `100%` / `1347.13` 是否可修 | 仅加固 transient retry；402 永不 retry；**不**放行 rounding | 单测 16/16；5×2 live 10/10 | 仍继承 R8 正式 84%；不冲 90% |
| **R10** | 是否值得正式 10×10 | **无功能编码**；运维：独立 r10 产物、402 熔断、per-run 归因 | 正式 10×10：94/100，acceptable 100%，402=0，可裁决 | **STRICT GO** |

禁止口径：不得把 R8 的 84/91≈92.3% 写成正式 success。

---

## 3. R10 六次 fallback（正确 fail-closed，不构成待修安全 bug）

| n | code | 说明 |
|--:|------|------|
| 3 | EVIDENCE_REPAIR_FAILURE | E06 无 source 的 `100%` |
| 2 | UNSUPPORTED_EXTERNAL_FACT | fabricated evidence_id |
| 1 | PROVIDER_FAILURE | timeout，已 1× retry 后仍 fallback |

不扩大 regenerate/retry，不把 fallback 算 success。

---

## 4. 冻结范围（Frozen）

以下核心逻辑视为冻结版本，后续不得为抬高 success 而修改：

- `src/final_analyst/evidence_repair.py`
- `src/final_analyst/production_gate.py`
- `src/final_analyst/judgment_frame.py`
- `src/final_analyst/contract_pin.py`
- `src/final_analyst/schemas.py`
- `src/final_analyst/validators.py`
- `src/final_analyst/live_quality.py`
- `src/final_analyst/calibration.py`
- `src/final_analyst/live_prompt.py`（ALLOWED_NUMBERS 边界）
- `src/final_analyst/llm.py`（retry/regenerate 上限：各最多 1 次）
- `src/final_analyst/failures.py`（taxonomy 语义）
- Evidence schema / Research canonical / Debate 主流程
- fixture expected / compare threshold `score >= 0.7` / 90% success 定义

运维可保留、不得覆盖 R8：

- `scripts/run_openai_stability_r10.py`
- `src/final_analyst/stability_bench.py`（熔断与归因；不改变 success 定义）

---

## 5. 本地回归（冻结时点）

| Suite | 结果 |
|-------|------|
| `tests.test_final_analyst` | 67/67 |
| `tests.test_final_analyst_round5` | 41/41 |
| `tests.test_final_analyst_e2e` | 13/13 |
| `tests.test_final_analyst_evaluation` | 43/43 |
| `tests.test_final_analyst_round7` | 23/23 |
| `tests.test_final_analyst_round8` | 32/32 |
| `tests.test_final_analyst_round9` | 16/16 |

本收口阶段 **不启动** 新的 live 10×10 / 5×2。

---

## 6. 剩余风险（可接受）

1. 模型偶发写出无 source 数字（如 E06 `100%`）→ fail-closed fallback。  
2. 模型偶发挂非法 evidence_id → fail-closed fallback。  
3. 偶发 provider timeout：最多 1× retry，仍失败则 fallback。  
4. 额度耗尽（402）会污染 live 数字：正式跑须完整 100 且 `formal_adjudicable=true`；部分结果不作裁决。

以上均不降低安全门槛，不作为本轮编码项。

---

## 7. Production Gate 裁决

**STRICT GO**

证据：R10 正式 10×10（`stability_10x10_openai_r10_final.json`）。

R8 的 84% 仅作历史锁定基线，不因 R10 改写。
