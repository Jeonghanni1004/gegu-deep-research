# Final Analyst Tenth Audit — Formal 10×10 (Ops-only + Independent Adjudication)

**审计日期**：2026-08-18  
**R8 锁定基线**：openai_success **84/100**（禁止写成 92.3%）  
**本轮正式产物**：`examples/evaluation/stability_10x10_openai_r10_final.json`  
**诊断**：`examples/evaluation/round10_failure_diagnosis.json`  
**formal_adjudicable**：true（完整 100 runs，未 quota 熔断）

---

## 0. 一句话

**无需 Round-10 功能编码。** 仅运维：独立 r10 artifact、402 熔断、per-run 归因。正式 10×10：**94/100 openai_success**，acceptable **100%**，硬安全与 drift **全 0**。

**裁决：Strict GO。**

R8 正式数字仍锁定 84%，不回溯改写。

---

## 1. 修改了什么

| 项 | 内容 |
|----|------|
| 功能 / repair / Gate / Frame / ALLOWED_NUMBERS | **未改** |
| `stability_bench.py` | 402 连续/累计熔断；`aborted_quota` / `incomplete` / `formal_adjudicable`；attempt 从 notes 解析 |
| `scripts/run_openai_stability_r10.py` | 写入 `stability_10x10_openai_r10_final.json`，拒绝覆盖 R8 |
| `scripts/run_openai_stability_10x10.py` | 默认改为 r10 路径，仍锁 R8 |

---

## 2. 测试结果

- Round-8：**32/32**
- Round-9：**16/16**
- evaluation：**43/43**
- R10 smoke 1×1：success（额度探测）
- Grounded baseline（R8 已有）：100/100 acceptable；本轮未重烧 API

---

## 3. 正式 10×10 结果

| 指标 | R8 locked | R10 formal |
|------|-----------|------------|
| total | 100 | **100**（完整） |
| openai_success | 84 | **94** |
| acceptable | 100 | **100** |
| fallback | 16 | **6** |
| regenerate (note) | 16 | 11 |
| retry | 0 | **1**（timeout 后仍 fallback） |
| 402 quota | 9 | **0** |
| information_loss | 0 | **0** |
| unsupported_external_fact (gate) | 0 | **0** |
| contract_violation | 0 | **0** |
| debate_state_drift | 0 | **0** |
| primary_axis_drift | 0 | **0** |
| reject | 0 | **0** |
| incomplete / aborted_quota | — | **false** |

---

## 4. Failure attribution（6 次 fallback）

| code | n | 样本 |
|------|--:|------|
| EVIDENCE_REPAIR_FAILURE | 3 | E06 run 6/8/10：`unresolved_numbers=100%`（无 source，fail-closed；regenerate 后仍失败） |
| UNSUPPORTED_EXTERNAL_FACT | 2 | E05#8 fabricated `akshare_fact_...`；E10#7 fabricated `derived_derived_...` |
| PROVIDER_FAILURE | 1 | E09#6 Read timeout；**retry_used=true, attempt=2** 后仍失败 → fallback |
| PROVIDER_QUOTA_FAILURE | 0 | — |
| JSON / Schema / VALIDATION_FAILURE | 0 | — |

Fallback **不算** openai_success。Gate 硬安全仍为 0（fabricated 在 live_hard_errors 拦截后走 grounded，最终 acceptable）。

---

## 5. 裁决

### **Strict GO**

- openai_success **94% ≥ 90%**
- acceptable **100% ≥ 80%**
- information_loss / unsupported_external_fact (gate) / contract_violation = **0**
- debate_state / primary_axis / JudgmentFrame drift = **0**
- 未排除 402 抬分（本轮 402=0）
- 未放宽 Gate / repair rounding / 90% 定义

残留风险：E06 模型仍会写无 source 的 `100%`；偶发 fabricated eid；偶发 timeout（retry 未救回 1 次）。均 fail-closed。

R8 历史 84% 仍为锁定基线档案，不因本轮 94% 而改写。
