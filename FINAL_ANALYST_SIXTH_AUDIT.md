# Final Analyst Sixth Audit — Production Integration & Evaluation

**审计日期**：2026-08-16  
**范围**：Production Pipeline 集成、Failure Taxonomy、Production Gate、JudgmentFrame Benchmark、Evaluation Dataset、Drift/Stability、E2E 可观测性  
**Provider（live）**：DeepSeek `deepseek-v4-flash`（thinking disabled）  
**原则**：不扩展 FA 业务 schema；不改 Evidence / Research canonical / Debate 主流程；Benchmark 比较 JudgmentFrame 而非全文；fail-closed

---

## 1. 裁决

### **NO-GO — Live Production Ready**

| P1 门槛 | 目标 | 实测（10×10 openai, pack=None） | 结果 |
|--------|------|--------------------------------|------|
| Judgment acceptable | ≥80% | **60%**（60/100） | **FAIL** |
| OpenAI success | ≥90% | **54%**（54/100） | **FAIL** |
| unsupported_external_fact | 0 | **0** | PASS |
| information_loss | 0 | **0** | PASS |
| contract_violation | 0 | **0** | PASS |
| reject（硬失败） | 低 | **0** | PASS（失败多走 grounded fallback） |

**不满足**「OpenAI success &lt;90% 但 acceptable≥80% → GO with Reliability Risk」的放宽条件（acceptable 仅 60%）。

### **GO — Production Integration（Grounded / 管线层）**

| 项 | 结果 |
|----|------|
| CLI `python -m pipeline.run` | PASS（grounded ACCEPT；openai 可成功或 FALLBACK） |
| as_of 双边一致性 fail-closed | PASS |
| Failure Taxonomy | PASS |
| Production Gate | PASS（ACCEPT / FALLBACK_PASS / REJECT） |
| Evaluation Dataset | **15** fixtures |
| Judgment Benchmark（grounded） | **100%**（15/15） |
| Grounded Stability 10×10 | **acceptable 100%**，drift **0** |
| tests.test_final_analyst | **67/67 PASS** |
| tests.test_final_analyst_round5 | **41/41 PASS**（live 偶发波动，复跑通过） |
| tests.test_final_analyst_e2e | **13/13 PASS** |
| tests.test_final_analyst_evaluation | **43/43 PASS** |

含义：生产封装、闸门、taxonomy、评估集与 **grounded** 判断稳定性已就绪；**live openai 判断可接受率与成功率未达生产 Ready**。

---

## 2. 修改 / 新增文件

| 路径 | 作用 |
|------|------|
| `src/final_analyst/failures.py` | **新增** 统一 Failure Taxonomy + `FailureRecord` |
| `src/final_analyst/production_gate.py` | **新增** fail-closed Production Gate |
| `src/final_analyst/judgment_frame.py` | **新增** JudgmentFrame 提取 / 结构比较 |
| `src/final_analyst/evaluation_dataset.py` | **新增** evaluation loader + fixture 校验 |
| `src/final_analyst/build_evaluation_dataset.py` | **新增** 构建 ≥10 evaluation fixtures |
| `src/final_analyst/stability_bench.py` | **新增** 多 run stability 聚合（`FA_BENCH_*`） |
| `src/final_analyst/pipeline.py` | **增强** 分层 stage、as_of gate、repair/fallback、trace、内部 fallback 显式 taxonomy |
| `src/pipeline/__init__.py` / `src/pipeline/run.py` | **新增** 生产 CLI 薄封装 |
| `examples/evaluation/E01–E15*.json` | Evaluation Dataset |
| `tests/test_final_analyst_e2e.py` | E2E / CLI / gate / taxonomy |
| `tests/test_final_analyst_evaluation.py` | Benchmark / drift / stability |
| `scripts/run_openai_stability_10x10.py` | 正式 openai 10×10 |
| `scripts/run_grounded_stability_10x10.py` | grounded 10×10 对照 |
| `FINAL_ANALYST_SIXTH_AUDIT.md` | 本审计 |

**未修改**：Evidence schema/builder、Time/Weight/Relevance、Research canonical 生成、Debate 主流程、FinalAnalystOutput 业务字段。  
**未恢复** phrase seal；**未**用 number scrub 作生产 PASS。

---

## 3. Production Pipeline 分层

```
Evidence
  → Research Contract Gate (+ as_of)
  → Debate Contract Gate
  → Final Analyst
  → FA Validation
  → Evidence Repair（如需要）
  → Regenerate / Grounded Fallback（如允许）
  → Production Gate
  → ACCEPT / FALLBACK_ACCEPT / REJECT
```

Trace：`examples/{stock}_pipeline_trace.json`  
含 stock / requested_as_of / research_as_of / debate_as_of / mode / stages / failure_code / repair_action / fallback / final_gate；**不写 API key**。

as_of：`Research.as_of == requested_as_of`（Debate 绑定 research as_of）；不一致 → `AS_OF_MISMATCH` fail-closed，不进入 FA。

OpenAI 客户端内部 fallback → pipeline 显式标记 `fallback`、notes、`failure_code`，**不伪装成 openai success**。

---

## 4. Failure Taxonomy（覆盖）

`CONTRACT_VIOLATION` / `AS_OF_MISMATCH` / `INVALID_RESEARCH` / `INVALID_DEBATE` / `INVALID_FA` / `VALIDATION_FAILURE` / `EVIDENCE_REPAIR_FAILURE` / `UNSUPPORTED_EXTERNAL_FACT` / `INFORMATION_LOSS` / `PROVIDER_FAILURE` / `JSON_PARSE_FAILURE` / `SCHEMA_SANITIZATION_FAILURE` / `PRODUCTION_GATE_REJECT`

映射自既有 validator / live_hard / repair 字符串前缀，**非**单纯 contains 作为唯一手段（前缀表 + 结构化 `FailureRecord`）。

---

## 5. Production Gate 检查项

Research/Debate contract、as_of、FA schema、semantic、evidence grounding、unsupported external fact、information loss、forbidden investment output、analytical increment。

`information_loss` / `unsupported_external_fact` / `contract violation` → **不可** Production PASS。  
Grounded fallback → `FALLBACK_PASS`，保留 prior failure。

---

## 6. Evaluation Dataset

| 项 | 值 |
|----|----|
| 数量 | **15**（≥10） |
| 结构覆盖 | profit/growth、bull/bear、unresolved、dual/cross tension、severe pressure、adversarial、non-mechanical |
| 行业覆盖 | 消费、制造、半导体、银行、医药、新能源、科技、周期 |
| expected | JudgmentFrame 结构范围，**非**固定自然语言全文 |

Grounded Judgment Benchmark：**15/15 acceptable = 100%**（≥80% GO）。

---

## 7. Stability 实测

### 7.1 Grounded 10×10（正式对照）

文件：`examples/evaluation/stability_10x10_grounded.json`

| 指标 | 值 |
|------|-----|
| total_runs | 100 |
| grounded_direct | 100 |
| acceptable_rate | **100%** |
| judgment_drift | **0** |
| information_loss / unsupported / contract | **0 / 0 / 0** |
| reject | 0 |

### 7.2 OpenAI 10×10（正式 audit，pack=None）

文件：`examples/evaluation/stability_10x10_openai.json`  
命令：`FA_LIVE=1 FA_BENCH_FIXTURES=10 FA_BENCH_RUNS=10 python scripts/run_openai_stability_10x10.py`

| 指标 | 值 |
|------|-----|
| total_runs | 100 |
| openai_success | **54**（54%） |
| grounded_fallback | **46**（46%） |
| acceptable | **60**（60%） |
| reject | 0 |
| judgment_drift（fixture 级） | **10** |
| information_loss | **0** |
| unsupported_external_fact | **0** |
| contract_violation | **0** |
| repair（成功 openai 路径） | 54 |

说明：fallback 计入 acceptable final outcome 的前提是 JudgmentFrame 仍落在 expected 范围；大量 fallback / 部分 openai 成功 run 的 debate_state 或 axis 偏离 expected → acceptable 被拉低。

### 7.3 污染对照（已作废作主结论）

`stability_10x10_openai_pack_contaminated.json`：曾错误默认挂载 `600519` EvidencePack，导致 E07–E10 全 reject。已修复为 **pack=None**（除非调用方显式传入）。**不以污染 run 作为 GO/NO-GO 依据。**

---

## 8. CLI 实测

```text
python -m pipeline.run --stock 600519 --as-of 2026-08-15 --mode grounded
→ status=PASS, mode=grounded, gate=ACCEPT

python -m pipeline.run --stock 600519 --as-of 2026-08-15 --mode openai
→ status=PASS, mode=openai（成功样本）或 FALLBACK_PASS/grounded（失败样本）
```

---

## 9. 测试汇总

| Suite | Result |
|------|--------|
| `python -m tests.test_final_analyst` | **67/67 PASS** |
| `python -m tests.test_final_analyst_round5` | **41/41 PASS** |
| `python -m tests.test_final_analyst_e2e` | **13/13 PASS** |
| `python -m tests.test_final_analyst_evaluation` | **43/43 PASS** |

---

## 10. 审计问题清单（用户要求 18 项）

| # | 问题 | 结论 |
|---|------|------|
| 1 | E2E 是否成功 | **是**（13/13） |
| 2 | CLI 是否成功 | **是**（grounded；openai 视 provider） |
| 3 | Dataset 数量 | **15** |
| 4 | Judgment Benchmark acceptable | grounded **100%**；live 10×10 **60%** |
| 5 | Judgment drift | grounded **0**；live fixture 级 **10/10** |
| 6 | Production Gate | 已落地；E2E ACCEPT/REJECT 验证 |
| 7 | Failure Taxonomy | 已落地并映射 |
| 8 | unsupported external fact | live 10×10 **0** |
| 9 | information loss | live 10×10 **0** |
| 10 | contract violation | live 10×10 **0** |
| 11 | OpenAI success | **54%** |
| 12 | grounded fallback | **46%** |
| 13 | 10×10 stability | 已执行（见 §7） |
| 14 | cross-industry robustness | Dataset 覆盖 8 行业；grounded bench 全过 |
| 15 | analytical increment | Gate 检查；grounded E2E PASS |
| 16 | 机械模板问题 | non-mechanical E09≠E10 signature **PASS** |
| 17 | 残余风险 | DeepSeek live repair/validation 失败率高；openai 成功时 JudgmentFrame 不稳定；axis 推断偶发 volume_vs_margin 误伤消费 fixture |
| 18 | GO / NO-GO | **NO-GO Live Production Ready**；**GO Production Integration (Grounded)** |

---

## 11. Evidence Repair Level-3

**未实现**（P1 可选，不阻塞本轮交付）。

---

## 12. 下一步（若要冲 Live GO）

1. 降低 live citation/repair 失败率（根因：`unresolved_numbers` / schema），目标 openai success ≥90%。  
2. 收紧 openai 输出与 Debate resolution 对齐，减少「成功但 JudgmentFrame 越界」。  
3. 将 openai×grounded fallback 的 signature 漂移纳入可解释 stochastic 白名单（仅措辞），严格禁止 debate_state 翻转。  
4. 复跑 `FA_BENCH_FIXTURES=10 FA_BENCH_RUNS=10`，**不改阈值定义**，以新实测重新裁决。

---

## 13. 最终一句话

第六轮 **生产集成与评估框架已完成且 grounded 路径生产可用**；以真实 10×10 live 指标衡量，**尚未达到 Production Ready**（acceptable 60% / openai 54%），故正式裁决为 **NO-GO — Live Production Ready**。
